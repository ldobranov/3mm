"""Durable Core broker for device events consumed by application services."""

from __future__ import annotations

from datetime import UTC, datetime
import threading

from sqlalchemy import func, select
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
    invoke_application,
    load_application_definition,
)


MAX_DELIVERY_ATTEMPTS = 5
MAX_DRAIN_BATCH = 100
MAX_STORED_DEAD_LETTERS = 1000
_worker_lock = threading.Lock()


def _manifest_section(package: ModulePackage, key: str) -> dict:
    value = (package.manifest or {}).get(key)
    return value if isinstance(value, dict) else {}


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


def _drain_subscription(
    db: Session,
    settings: ApplicationRuntimeSettings,
    installation: ApplicationExtensionInstallation,
    package: ModulePackage,
    subscription,
) -> None:
    deliveries = list(
        db.scalars(
            select(ApplicationEventDelivery)
            .where(
                ApplicationEventDelivery.application_installation_id == installation.id,
                ApplicationEventDelivery.subscription_id == subscription.subscription_id,
                ApplicationEventDelivery.status == "pending",
            )
            .order_by(ApplicationEventDelivery.device_event_id)
            .limit(MAX_DRAIN_BATCH)
        )
    )
    for delivery in deliveries:
        event = db.get(DeviceEvent, delivery.device_event_id)
        if event is None:
            delivery.status = "dead_letter"
            delivery.last_error = "Device event is unavailable"
            db.commit()
            continue
        device = db.get(Device, event.device_id)
        if device is None:
            delivery.status = "dead_letter"
            delivery.last_error = "Source device is unavailable"
            cursor = _cursor(db, installation.id, subscription.subscription_id)
            _record_terminal_delivery(cursor, event, acknowledged=False)
            _prune_dead_letters(db, installation.id, subscription.subscription_id, cursor)
            db.commit()
            continue
        delivery.attempts += 1
        try:
            invoke_application(
                installation,
                package,
                settings,
                subscription.handler_operation_id,
                _event_payload(event, device),
                {
                    "audience": "internal",
                    "correlation_id": event.event_id,
                    "idempotency_key": event.event_id,
                },
                required_audience="internal",
            )
        except ApplicationGatewayError as exc:
            delivery.last_error = str(exc)[:500]
            if delivery.attempts < MAX_DELIVERY_ATTEMPTS:
                db.commit()
                break
            delivery.status = "dead_letter"
            cursor = _cursor(db, installation.id, subscription.subscription_id)
            _record_terminal_delivery(cursor, event, acknowledged=False)
            _prune_dead_letters(db, installation.id, subscription.subscription_id, cursor)
            db.commit()
            continue
        delivery.status = "acknowledged"
        delivery.last_error = None
        delivery.acknowledged_at = datetime.now(UTC)
        cursor = _cursor(db, installation.id, subscription.subscription_id)
        _record_terminal_delivery(cursor, event, acknowledged=True)
        db.commit()


def enqueue_application_event(
    db: Session,
    event: DeviceEvent,
    settings: ApplicationRuntimeSettings,
) -> None:
    """Match, persist and deliver one event without delaying Agent acceptance."""
    device = db.get(Device, event.device_id)
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
    ).all()
    for installation, package in rows:
        try:
            definition = load_application_definition(package)
        except ApplicationGatewayError:
            continue
        permissions = set((package.manifest or {}).get("permissions") or [])
        capabilities = set(_manifest_section(package, "capabilities").get("consumes") or [])
        configuration = _manifest_section(package, "configuration_defaults")
        configuration.update(installation.configuration or {})
        for subscription in definition.event_subscriptions:
            if (
                subscription.event_type != event.event_type
                or subscription.capability_id != event.payload.get("capability_id")
                or subscription.capability_id not in capabilities
                or "events.consume" not in permissions
                or configuration.get(subscription.device_scope_config_key)
                != device.device_id
            ):
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
                        ApplicationEventDelivery.status == "pending",
                    )
                ) or 0
                delivery = ApplicationEventDelivery(
                    application_installation_id=installation.id,
                    subscription_id=subscription.subscription_id,
                    device_event_id=event.id,
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
            _drain_subscription(
                db,
                settings,
                installation,
                package,
                subscription,
            )


def retry_application_events(
    db: Session,
    settings: ApplicationRuntimeSettings,
) -> None:
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
    ).all()
    for installation, package in rows:
        try:
            definition = load_application_definition(package)
        except ApplicationGatewayError:
            continue
        for subscription in definition.event_subscriptions:
            _drain_subscription(
                db,
                settings,
                installation,
                package,
                subscription,
            )


def process_application_event(
    event_id: int,
    settings: ApplicationRuntimeSettings,
) -> None:
    """Run broker matching/delivery outside the Agent ingestion request."""
    from backend.database import SessionLocal

    with _worker_lock:
        db = SessionLocal()
        try:
            event = db.get(DeviceEvent, event_id)
            if event is not None:
                enqueue_application_event(db, event, settings)
        finally:
            db.close()


def retry_application_events_once(settings: ApplicationRuntimeSettings) -> None:
    """Retry persisted backlog with a fresh session and one process-wide worker."""
    from backend.database import SessionLocal

    with _worker_lock:
        db = SessionLocal()
        try:
            retry_application_events(db, settings)
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
                "backlog": counts.get("pending", 0),
                "stored_dead_letters": counts.get("dead_letter", 0),
            }
        )
    return result
