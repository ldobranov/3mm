"""Admin-only host telemetry: short Core admission, Runtime wait, current result."""
from dataclasses import dataclass
from pathlib import Path
import socket
import time
import uuid

from sqlalchemy import select, update
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services.application_response_relay import ResponseWaiter
from three_mm_platform_wire import remaining
from three_mm_runtime.application_transport import sign_message, send_message, verify_message, ApplicationTransportError


@dataclass(frozen=True)
class StatusProbe:
    installation_id: int
    snapshot: tuple
    secret: bytes
    request_id: str


def snapshot(installation, package):
    return (installation.instance_id, installation.authority_incarnation, installation.authority_epoch,
        installation.module_package_id, package.sha256, installation.enabled, installation.status)


def begin_status_probe(db, installation, package, settings):
    """The caller has already required admin and validated the package bytes."""
    if not installation.enabled or installation.status != "active":
        db.rollback(); return None, None
    original = snapshot(installation, package)
    secret = (settings.key_root / (installation.instance_id + ".key")).read_bytes()
    if len(secret) != 32: raise ValueError("Invalid application transport key")
    target = Path(installation.socket_path); identifier = installation.id
    db.rollback()  # No Core read transaction during reservation or remote I/O.
    import pwd
    uid = pwd.getpwnam(settings.runtime_user).pw_uid
    waiter = ResponseWaiter.reserve(settings.application_response_socket, uid)
    origin = None
    try:
        # Linearize this read-only host probe against disable/adoption/rotation.
        changed = db.execute(update(Installation).where(
            Installation.id == identifier, Installation.instance_id == original[0],
            Installation.authority_incarnation == original[1], Installation.authority_epoch == original[2],
            Installation.module_package_id.in_(select(ModulePackage.id).where(
                ModulePackage.id == original[3], ModulePackage.sha256 == original[4])), Installation.enabled.is_(True), Installation.status == "active",
        ).values(updated_at=Installation.updated_at)).rowcount
        if changed != 1: raise ValueError("Application changed before status admission")
        db.commit()
        request_id = uuid.uuid4().hex
        request = sign_message({"version": 1, "request_id": request_id, "timestamp": int(time.time()),
            "operation_id": "three_mm.platform.status", "payload": {},
            "context": {"audience": "internal", "correlation_id": "status:" + original[0]}}, secret)
        origin = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = waiter.handoff_deadline
        origin.settimeout(remaining(deadline)); origin.connect(str(target))
        origin.settimeout(remaining(deadline)); send_message(origin, request)
        waiter.handoff(origin)
        return StatusProbe(identifier, original, secret, request_id), waiter
    except BaseException:
        waiter.close(); db.rollback(); raise
    finally:
        if origin is not None: origin.close()


def finish_status_probe(probe, response, installation, package, settings):
    if probe is None or response is None: return None
    if installation.id != probe.installation_id or snapshot(installation, package) != probe.snapshot: return None
    try:
        current = (settings.key_root / (installation.instance_id + ".key")).read_bytes()
        if current != probe.secret: return None
        verified = verify_message(response, current, expected_request_id=probe.request_id)
    except (OSError, ValueError, TypeError, RecursionError, ApplicationTransportError): return None
    result = verified.get("result")
    if verified.get("ok") is not True or not isinstance(result, dict): return None
    revision = result.get("revision"); outbox = result.get("outbox")
    if (revision is not None and (not isinstance(revision, str) or len(revision) > 128)
            or not isinstance(outbox, dict) or len(outbox) > 32
            or any(not isinstance(k, str) or len(k) > 64 or type(v) is not int or not 0 <= v < 2**63 for k,v in outbox.items())
            or type(result.get("outbox_inspected", True)) is not bool): return None
    return {"revision": revision, "outbox": outbox, "outbox_inspected": result.get("outbox_inspected", True)}
