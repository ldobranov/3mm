"""Durable Core broker for device events consumed by application services."""

from __future__ import annotations

from datetime import UTC, datetime
import threading
import re
import socket
import time
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.device import Device, DeviceEvent
from backend.db.module import (
    ApplicationEventCursor,
    ApplicationEventDelivery,
    ApplicationExtensionInstallation,
    ModulePackage,
)
from backend.services.application_extensions import (
    ApplicationGatewayError,
    prepare_application_invocation,
    find_operation, validate_operation_payload,
    load_application_definition,
)
from backend.services.passage import passage_delivery_allowed


MAX_DELIVERY_ATTEMPTS = 5
MAX_DRAIN_BATCH = 100
MAX_STORED_DEAD_LETTERS = 1000
_worker_lock = threading.Lock()
_claim_lock = threading.Lock()
EVENT_DELIVERY_CONTRACT = 1
CLAIM_LEASE_MS = 40_000
RETRY_DELAY_MS = 30_000


def _clock():
    from backend.services.application_authority_management import _clock as authority_clock
    return authority_clock()



def _manifest_section(package: ModulePackage, key: str) -> dict:
    value = (package.manifest or {}).get(key)
    return dict(value) if isinstance(value, dict) else {}


def _subscription_allowed(installation, package, subscription, event, device) -> bool:
    """Match current declarations; enforced mode ALSO needs a live sealed grant.

    Compatibility keeps its existing declared subscription contract, but every
    attempt must match today's source/binding, not only the original enqueue.
    """
    configuration = _manifest_section(package, "configuration_defaults")
    configuration.update(installation.configuration or {})
    return (
        installation.authority_mode in {"compatibility", "enforced"}
        and installation.enabled
        and installation.status == "active"
        and installation.module_package_id == package.id
        and installation.module_id == package.module_id
        and installation.active_version == package.version
        and device.revoked_at is None
        and device.approved_at is not None
        and subscription.event_type == event.event_type
        and subscription.capability_id == event.payload.get("capability_id")
        and subscription.capability_id
        in (_manifest_section(package, "capabilities").get("consumes") or [])
        and "events.consume" in ((package.manifest or {}).get("permissions") or [])
        and configuration.get(subscription.device_scope_config_key) == device.device_id
    )


def _granted_definition(subscription, admission):
    if not admission.compatibility and not any(
            current == subscription for current in admission.definition.event_subscriptions):
        raise ValueError("Event subscription changed")


def _event_granted(db, installation, subscription):
    if installation.authority_mode == "compatibility":
        return True
    from backend.services.application_authority_management import effect_admission
    try:
        with effect_admission(db, installation.id, f"event:{subscription.subscription_id}") as admission:
            if admission.compatibility:
                raise ValueError("Event authority mode changed")
            _granted_definition(subscription, admission)
            db.commit()
            admission()
        return True
    except ValueError:
        db.rollback()
        return False


def _delivery_epoch_current(installation, delivery):
    return delivery.authority_epoch == (
        installation.authority_epoch if installation.authority_mode == "enforced" else None)


def _cursor(
    db: Session,
    installation_id: int,
    subscription_id: str,
) -> ApplicationEventCursor:
    cursor = db.scalar(
        select(ApplicationEventCursor).where(
            ApplicationEventCursor.application_installation_id == installation_id,
            ApplicationEventCursor.subscription_id == subscription_id,
        )
    )
    if cursor is None:
        cursor = ApplicationEventCursor(
            application_installation_id=installation_id,
            subscription_id=subscription_id,
        )
        db.add(cursor)
        db.flush()
    return cursor


def _record_terminal_delivery(
    cursor: ApplicationEventCursor,
    event: DeviceEvent,
    *,
    acknowledged: bool,
) -> None:
    if (
        cursor.last_device_event_id is None
        or event.id >= cursor.last_device_event_id
    ):
        cursor.last_device_event_id = event.id
        cursor.last_event_id = event.event_id
    if acknowledged:
        cursor.acknowledged_count += 1
    else:
        cursor.dead_letter_count += 1


def _prune_dead_letters(
    db: Session,
    installation_id: int,
    subscription_id: str,
    cursor: ApplicationEventCursor,
) -> None:
    overflow = db.scalar(
        select(ApplicationEventDelivery)
        .where(
            ApplicationEventDelivery.application_installation_id == installation_id,
            ApplicationEventDelivery.subscription_id == subscription_id,
            ApplicationEventDelivery.status == "dead_letter",
        )
        .order_by(ApplicationEventDelivery.device_event_id.desc())
        .offset(MAX_STORED_DEAD_LETTERS)
        .limit(1)
    )
    if overflow is not None:
        db.delete(overflow)
        cursor.dropped_dead_letter_count += 1


def _event_payload(event: DeviceEvent, device: Device) -> dict[str, object]:
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return {
        "event_id": event.event_id,
        "device_id": device.device_id,
        "event_type": event.event_type,
        "occurred_at": occurred_at.isoformat(),
        "payload": event.payload,
    }


def _deny_delivery(db, installation, delivery, event, *, error="Event subscription authority is unavailable or changed") -> None:
    delivery.status = "dead_letter"
    delivery.last_error = error
    cursor = _cursor(db, installation.id, delivery.subscription_id)
    _record_terminal_delivery(cursor, event, acknowledged=False)
    _prune_dead_letters(db, installation.id, delivery.subscription_id, cursor)
    db.commit()


def enqueue_application_event(
    db: Session,
    event: DeviceEvent,
    settings: ApplicationRuntimeSettings,
) -> None:
    """Match/persist only. The independent Runtime pulls admitted deliveries."""
    # V1 subscriptions select managed devices, never an application's stream.
    if event.producer_kind != "device":
        return
    device = db.get(Device, event.device_id, populate_existing=True)
    if device is None:
        return
    rows = db.execute(
        select(ApplicationExtensionInstallation, ModulePackage)
        .join(
            ModulePackage,
            ModulePackage.id == ApplicationExtensionInstallation.module_package_id,
        )
        .where(
            ApplicationExtensionInstallation.enabled.is_(True),
            ApplicationExtensionInstallation.status == "active",
        )
        .execution_options(populate_existing=True)
    ).all()
    for installation, package in rows:
        if installation.authority_mode not in {"compatibility", "enforced"}:
            continue
        if not passage_delivery_allowed(db, installation, event):
            continue
        try:
            definition = load_application_definition(package)
        except ApplicationGatewayError:
            continue
        for subscription in definition.event_subscriptions:
            if (not _subscription_allowed(installation, package, subscription, event, device)
                    or not _event_granted(db, installation, subscription)):
                continue
            delivery = db.scalar(
                select(ApplicationEventDelivery).where(
                    ApplicationEventDelivery.application_installation_id
                    == installation.id,
                    ApplicationEventDelivery.subscription_id
                    == subscription.subscription_id,
                    ApplicationEventDelivery.device_event_id == event.id,
                )
            )
            if delivery is None:
                cursor = _cursor(
                    db,
                    installation.id,
                    subscription.subscription_id,
                )
                backlog = db.scalar(
                    select(func.count())
                    .select_from(ApplicationEventDelivery)
                    .where(
                        ApplicationEventDelivery.application_installation_id
                        == installation.id,
                        ApplicationEventDelivery.subscription_id
                        == subscription.subscription_id,
                        ApplicationEventDelivery.status.in_({"pending", "delivering"}),
                    )
                ) or 0
                delivery = ApplicationEventDelivery(
                    application_installation_id=installation.id,
                    subscription_id=subscription.subscription_id,
                    device_event_id=event.id,
                    authority_epoch=installation.authority_epoch if installation.authority_mode == "enforced" else None,
                    status=(
                        "dead_letter"
                        if backlog >= subscription.max_backlog
                        else "pending"
                    ),
                    last_error=(
                        "Subscription backlog limit was reached"
                        if backlog >= subscription.max_backlog
                        else None
                    ),
                )
                db.add(delivery)
                if delivery.status == "dead_letter":
                    _record_terminal_delivery(cursor, event, acknowledged=False)
                    _prune_dead_letters(
                        db,
                        installation.id,
                        subscription.subscription_id,
                        cursor,
                    )
                db.commit()


def request_application_event_retry(db):
    """Admin wakeup for pending work; never renew an active lease or execute code."""
    db.execute(update(ApplicationEventDelivery).where(ApplicationEventDelivery.status == "pending")
               .values(retry_not_before_ms=None, retry_boot_id=None))
    db.commit()




def process_application_event(
    event_id: int,
    settings: ApplicationRuntimeSettings,
) -> None:
    """Run durable broker matching outside the Agent ingestion request."""
    from backend.database import SessionLocal

    with _worker_lock:
        db = SessionLocal()
        try:
            event = db.get(DeviceEvent, event_id)
            if event is not None:
                enqueue_application_event(db, event, settings)
        finally:
            db.close()


def application_event_status(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(ApplicationEventCursor, ApplicationExtensionInstallation)
        .join(
            ApplicationExtensionInstallation,
            ApplicationExtensionInstallation.id
            == ApplicationEventCursor.application_installation_id,
        )
        .order_by(
            ApplicationExtensionInstallation.module_id,
            ApplicationEventCursor.subscription_id,
        )
    ).all()
    result: list[dict[str, object]] = []
    for cursor, installation in rows:
        counts = {
            status: count
            for status, count in db.execute(
                select(
                    ApplicationEventDelivery.status,
                    func.count(ApplicationEventDelivery.id),
                )
                .where(
                    ApplicationEventDelivery.application_installation_id
                    == installation.id,
                    ApplicationEventDelivery.subscription_id
                    == cursor.subscription_id,
                )
                .group_by(ApplicationEventDelivery.status)
            )
        }
        result.append(
            {
                "module_id": installation.module_id,
                "subscription_id": cursor.subscription_id,
                "last_event_id": cursor.last_event_id,
                "acknowledged_total": cursor.acknowledged_count,
                "dead_letter_total": cursor.dead_letter_count,
                "dropped_dead_letters_total": cursor.dropped_dead_letter_count,
                "backlog": counts.get("pending", 0) + counts.get("delivering", 0),
                "stored_dead_letters": counts.get("dead_letter", 0),
            }
        )
    return result


# Runtime is an I/O worker. All queue selection, current admission and durable
# transitions stay here; an opaque dispatch ID grants no application operation.
def _heads(db):
    from sqlalchemy.orm import aliased
    older = aliased(ApplicationEventDelivery)
    row = ApplicationEventDelivery
    queued = {"pending", "delivering"}
    previous = select(older.id).where(
        older.application_installation_id == row.application_installation_id,
        older.subscription_id == row.subscription_id,
        older.status.in_(queued), older.device_event_id < row.device_event_id).exists()
    installation=ApplicationExtensionInstallation
    eligible=(row.status=="delivering") | (installation.enabled.is_(True) & (installation.status=="active"))
    return list(db.scalars(select(row).join(installation,
        installation.id==row.application_installation_id).where(row.status.in_(queued), ~previous, eligible)
        .order_by(func.coalesce(row.retry_not_before_ms, 0), row.id).limit(MAX_DRAIN_BATCH)))


def _settle(db, delivery, event, *, error=None, delay_ms=RETRY_DELAY_MS):
    """CAS one latest attempt; cursor/counters commit with the outcome exactly once."""
    metadata = dict(delivery.dispatch_metadata or {})
    terminal = error is None or delivery.attempts >= MAX_DELIVERY_ATTEMPTS
    status = "acknowledged" if error is None else "dead_letter" if terminal else "pending"
    boot, now = _clock()
    changed = db.execute(update(ApplicationEventDelivery).where(
        ApplicationEventDelivery.id == delivery.id,
        ApplicationEventDelivery.status == "delivering",
        ApplicationEventDelivery.dispatch_id == delivery.dispatch_id)
        .values(status=status, last_error=error, retry_boot_id=boot,
            retry_not_before_ms=now+delay_ms if not terminal else None,
            dispatch_metadata={**metadata, "finished": True},
            acknowledged_at=datetime.now(UTC) if error is None else None)
        .execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        db.rollback(); return False
    if terminal and event is not None:
        cursor = _cursor(db, delivery.application_installation_id, delivery.subscription_id)
        _record_terminal_delivery(cursor, event, acknowledged=error is None)
        if error is not None:
            _prune_dead_letters(db, delivery.application_installation_id, delivery.subscription_id, cursor)
    identifier=delivery.id
    db.commit()
    # Bounded dead-letter retention can prune this old terminal attempt itself.
    # Its cursor transition is already committed; never refresh a deleted row.
    current=db.get(ApplicationEventDelivery,identifier,populate_existing=True)
    if current is None:delivery.status=status
    return True


def _send_event_invocation(prepared, request_id):
    from three_mm_runtime.application_transport import sign_message, send_message
    from three_mm_platform_wire import remaining
    message = sign_message({"version": 1, "request_id": request_id, "timestamp": int(time.time()),
        "operation_id": prepared.operation_id, "payload": prepared.payload, "context": prepared.context,
        **({"relational_invocation": prepared.relational_invocation}
           if prepared.relational_invocation is not None else {})}, prepared.secret)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        deadline = time.monotonic()+3
        connection.settimeout(remaining(deadline)); connection.connect(str(prepared.socket_path))
        connection.settimeout(remaining(deadline)); send_message(connection, message)
        return connection  # Never read a service response inside Core.
    except BaseException:
        connection.close(); raise


def _current_event(db, installation, package, subscription, delivery, event, device):
    db.refresh(installation); db.refresh(package); db.refresh(event); db.refresh(device)
    return (_subscription_allowed(installation, package, subscription, event, device)
        and _delivery_epoch_current(installation, delivery)
        and passage_delivery_allowed(db, installation, event))


def _admit_event_attempt(db, delivery, installation, package, subscription, event, device,
                         prepared, metadata, dispatch_id, snapshot):
    from backend.services.application_authority_management import effect_admission, lock_compatibility_admission
    with effect_admission(db, installation.id, f"event:{subscription.subscription_id}") as admission, db.no_autoflush:
        if admission.compatibility:
            lock_compatibility_admission(db, installation, required=True)
        _granted_definition(subscription, admission)
        changed = db.execute(update(Device).where(
            Device.id == device.id, Device.device_id == device.device_id,
            Device.revoked_at.is_(None), Device.approved_at.is_not(None))
            .values(updated_at=Device.updated_at).execution_options(synchronize_session=False)).rowcount
        if changed != 1 or not _current_event(db, installation, package, subscription, delivery, event, device):
            raise ValueError("Event authority changed")
        if snapshot != (package.sha256, installation.authority_mode, installation.authority_epoch,
                        installation.instance_id, installation.socket_path, _event_payload(event, device)):
            raise ValueError("Event dispatch target changed")
        changed = db.execute(update(ApplicationEventDelivery).where(
            ApplicationEventDelivery.id == delivery.id,
            ApplicationEventDelivery.status == "pending",
            ApplicationEventDelivery.attempts == delivery.attempts,
            ApplicationEventDelivery.attempts < MAX_DELIVERY_ATTEMPTS)
            .values(status="delivering", attempts=delivery.attempts+1, dispatch_id=dispatch_id,
                    dispatch_metadata=metadata, retry_not_before_ms=None)
            .execution_options(synchronize_session=False)).rowcount
        if changed != 1: raise ValueError("Event attempt was already claimed")
        db.commit()  # Durable before any send; neither DB nor key lease spans service I/O.
        admission()
    db.refresh(delivery)
    db.rollback()  # The refresh read must not span service I/O either.


def claim_event_delivery(db, settings, *, runtime_generation):
    """Return at most one already-sent service connection and result-only receipt."""
    idle = {"event_delivery_contract": EVENT_DELIVERY_CONTRACT, "ok": True, "idle": True}
    if not _claim_lock.acquire(blocking=False): return idle, None
    try:
        boot, now = _clock()
        for delivery in _heads(db):
            event = db.get(DeviceEvent, delivery.device_event_id)
            if delivery.status == "delivering":
                metadata = delivery.dispatch_metadata or {}
                if metadata.get("boot_id") == boot and metadata.get("deadline_ms", 0) > now:
                    continue
                _settle(db, delivery, event, error="delivery_unconfirmed", delay_ms=0)
                if delivery.status != "pending": continue
            if delivery.retry_boot_id == boot and (delivery.retry_not_before_ms or 0) > now:
                continue
            installation = db.get(ApplicationExtensionInstallation, delivery.application_installation_id,
                                  populate_existing=True)
            # A disabled installation pauses pending work, as before. A new
            # enforced epoch can never adopt old backlog when it becomes active.
            if installation is None or not installation.enabled or installation.status != "active": continue
            if delivery.attempts>=MAX_DELIVERY_ATTEMPTS and event is not None:
                _deny_delivery(db,installation,delivery,event,error="attempt_limit_exhausted")
                continue
            package = db.get(ModulePackage, installation.module_package_id, populate_existing=True)
            device = db.get(Device, event.device_id, populate_existing=True) if event is not None else None
            try:
                definition = load_application_definition(package) if package is not None else None
                subscription = next((s for s in definition.event_subscriptions
                    if s.subscription_id == delivery.subscription_id), None) if definition else None
            except ApplicationGatewayError:
                subscription = None
            if (event is None or device is None or subscription is None
                    or not _current_event(db, installation, package, subscription, delivery, event, device)
                    or not _event_granted(db, installation, subscription)):
                if event is not None:
                    _deny_delivery(db, installation, delivery, event)
                else:
                    delivery.status="dead_letter";delivery.last_error="Device event is unavailable";db.commit()
                continue
            snapshot = (package.sha256, installation.authority_mode, installation.authority_epoch,
                        installation.instance_id, installation.socket_path, _event_payload(event, device))
            try:
                prepared = prepare_application_invocation(installation, package, settings,
                    subscription.handler_operation_id, snapshot[-1],
                    {"audience":"internal", "correlation_id":event.event_id, "idempotency_key":event.event_id},
                    required_audience="internal")
            except ApplicationGatewayError:
                db.rollback()
                if (not _current_event(db, installation, package, subscription, delivery, event, device)
                        or not _event_granted(db, installation, subscription)):
                    _deny_delivery(db, installation, delivery, event); continue
                # Count bounded pre-dispatch failures too; an unavailable key or
                # malformed service descriptor cannot spin the broker forever.
                delivery.status="delivering";delivery.attempts+=1
                delivery.dispatch_id=uuid.uuid4().hex;delivery.dispatch_metadata={}
                db.commit()
                _settle(db, delivery, event, error="dispatch_unavailable")
                continue
            dispatch_id=uuid.uuid4().hex;request_id=uuid.uuid4().hex
            boot, now = _clock()
            metadata = {"version":1, "boot_id":boot, "deadline_ms":now+CLAIM_LEASE_MS,
                "runtime_generation":runtime_generation, "request_id":request_id,
                "instance_id":installation.instance_id, "package_id":package.id,
                "package_sha256":package.sha256, "operation_id":prepared.operation_id, "finished":False}
            try:
                _admit_event_attempt(db, delivery, installation, package, subscription, event, device,
                                     prepared, metadata, dispatch_id, snapshot)
            except ValueError:
                db.rollback();db.refresh(delivery)
                if delivery.status=="pending":_deny_delivery(db, installation, delivery, event)
                continue
            try:
                origin = _send_event_invocation(prepared, request_id)
            except (OSError, ValueError, RuntimeError):
                _settle(db, delivery, event, error="dispatch_unconfirmed");continue
            return {"event_delivery_contract":EVENT_DELIVERY_CONTRACT,"ok":True,"idle":False,
                    "receipt":{"delivery_id":delivery.id,"dispatch_id":dispatch_id},
                    "timeout_seconds":prepared.timeout_seconds}, origin
        db.rollback()
        return idle, None
    finally:
        _claim_lock.release()


def complete_event_delivery(db, settings, receipt, *, runtime_generation, response=None, failure=None):
    from three_mm_runtime.application_transport import verify_message
    if (not isinstance(receipt,dict) or set(receipt)!={"delivery_id","dispatch_id"}
            or type(receipt["delivery_id"]) is not int or receipt["delivery_id"]<=0
            or not isinstance(receipt["dispatch_id"],str)
            or re.fullmatch(r"[0-9a-f]{32}",receipt["dispatch_id"]) is None):
        raise ValueError("Invalid event result receipt")
    delivery=db.get(ApplicationEventDelivery,receipt["delivery_id"],populate_existing=True)
    metadata=dict(delivery.dispatch_metadata or {}) if delivery is not None else {}
    if (delivery is None or delivery.dispatch_id!=receipt["dispatch_id"]
            or metadata.get("runtime_generation")!=runtime_generation):
        raise ValueError("Event attempt owner changed")
    if metadata.get("finished") is True:
        return {"event_delivery_contract":EVENT_DELIVERY_CONTRACT,"ok":True,"status":delivery.status}
    boot, now=_clock()
    if delivery.status!="delivering" or metadata.get("boot_id")!=boot or metadata.get("deadline_ms",0)<=now:
        raise ValueError("Event attempt expired")
    error = None
    if failure is not None:
        if failure not in {"handler_unavailable","deadline_exceeded","response_invalid"} or response is not None:
            raise ValueError("Invalid event failure")
        error=failure
    else:
        try:
            instance=metadata["instance_id"]
            if re.fullmatch(r"[0-9a-f]{24}",instance) is None:raise ValueError("Invalid event instance")
            secret=(settings.key_root/(instance+".key")).read_bytes()
            if len(secret)!=32:raise ValueError("Invalid event key")
            verified=verify_message(response,secret,expected_request_id=metadata["request_id"])
            if verified.get("ok") is not True or not isinstance(verified.get("result"),dict):
                raise ValueError("Invalid event response")
            package=db.get(ModulePackage,metadata["package_id"])
            if package is None or package.sha256!=metadata["package_sha256"]:raise ValueError("Event artifact changed")
            validate_operation_payload(verified["result"],
                find_operation(load_application_definition(package),metadata["operation_id"]).output_schema)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            error="response_invalid"
    event=db.get(DeviceEvent,delivery.device_event_id)
    _settle(db,delivery,event,error=error)
    return {"event_delivery_contract":EVENT_DELIVERY_CONTRACT,"ok":True,"status":delivery.status}


def handle_event_delivery(connection, request, *, key_root, runtime_generation):
    from backend.database import SessionLocal
    from three_mm_platform_wire import send_authority_frame
    origin=None
    try:
        with SessionLocal() as db:
            settings=ApplicationRuntimeSettings(key_root=key_root)
            if set(request)=={"event_delivery_contract","claim"} and request["claim"] is True:
                result,origin=claim_event_delivery(db,settings,runtime_generation=runtime_generation)
            elif set(request)=={"event_delivery_contract","receipt","response"}:
                result=complete_event_delivery(db,settings,request["receipt"],response=request["response"],
                                               runtime_generation=runtime_generation)
            elif set(request)=={"event_delivery_contract","receipt","failure"}:
                result=complete_event_delivery(db,settings,request["receipt"],failure=request["failure"],
                                               runtime_generation=runtime_generation)
            else:raise ValueError("Invalid event authority request")
    except Exception:
        result={"event_delivery_contract":EVENT_DELIVERY_CONTRACT,"ok":False}
    try:
        connection.settimeout(3);send_authority_frame(connection,result,origin=origin)
    finally:
        if origin is not None:origin.close()
