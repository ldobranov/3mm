"""Declared admin health: short Core admission/completion, response-only Runtime wait."""
from datetime import UTC, datetime
import json
import socket
import time
import uuid

from sqlalchemy import update
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services.application_extensions import (
    ApplicationGatewayError, load_application_definition, prepare_application_invocation,
    validate_operation_payload,
)
from backend.services.application_response_relay import ResponseWaiter
from three_mm_platform_wire import remaining
from three_mm_runtime.application_transport import sign_message, send_message, verify_message


from backend.services.application_response_relay import (
    ApplicationResponseBinding as HealthProbe, application_snapshot as _snapshot,
    application_fence as _fence,
)


def _prepare(installation, package, settings, operation_id, request_id):
    prepared = prepare_application_invocation(installation, package, settings, operation_id, {},
        {"audience": "internal", "correlation_id": "health:" + request_id}, required_audience="internal")
    # A health query must never acquire relational SQL authority or host metadata.
    if prepared.relational_invocation is not None:
        raise ApplicationGatewayError("Health cannot acquire relational SQL authority")
    return prepared


def begin_health_probe(db, installation, package, settings):
    """Caller requires admin and a consistent active package; no DB transaction spans IPC."""
    waiter = origin = None
    try:
        operation_id = load_application_definition(package).service.health_operation_id
        request_id = uuid.uuid4().hex
        prepared = _prepare(installation, package, settings, operation_id, request_id)
        probe = HealthProbe(installation.id, _snapshot(installation, package), prepared.secret, request_id, operation_id)
        db.rollback()
        import pwd
        waiter = ResponseWaiter.reserve(settings.application_response_socket, pwd.getpwnam(settings.runtime_user).pw_uid)
        # Reservation can race with lifecycle, key or native UI trust changes.
        db.expire_all()
        current = db.get(Installation, probe.installation_id)
        active = db.get(ModulePackage, current.module_package_id) if current is not None else None
        if active is None or _snapshot(current, active) != probe.snapshot:
            raise ApplicationGatewayError("Application changed before health admission")
        prepared = _prepare(current, active, settings, operation_id, request_id)
        if prepared.secret != probe.secret:
            raise ApplicationGatewayError("Application transport key changed")
        changed = db.execute(update(Installation).where(*_fence(probe)).values(updated_at=Installation.updated_at)).rowcount
        if changed != 1:
            raise ApplicationGatewayError("Application changed before health admission")
        db.commit()
        waiter.timeout_seconds = int(prepared.timeout_seconds)
        request = sign_message({"version": 1, "request_id": request_id, "timestamp": int(time.time()),
            "operation_id": prepared.operation_id, "payload": prepared.payload, "context": prepared.context}, prepared.secret)
        origin = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = waiter.handoff_deadline
        origin.settimeout(remaining(deadline)); origin.connect(str(prepared.socket_path))
        origin.settimeout(remaining(deadline)); send_message(origin, request)
        waiter.handoff(origin)
        return probe, waiter
    except BaseException:
        if waiter is not None: waiter.close()
        db.rollback()
        raise
    finally:
        if origin is not None: origin.close()


def finish_health_probe(db, probe, response, settings):
    """Verify current admission and the original app signature, then fence the health stamp."""
    db.expire_all()
    current = db.get(Installation, probe.installation_id)
    package = db.get(ModulePackage, current.module_package_id) if current is not None else None
    if package is None or _snapshot(current, package) != probe.snapshot:
        raise ApplicationGatewayError("Application changed during health check")
    prepared = _prepare(current, package, settings, probe.operation_id, probe.request_id)
    if prepared.secret != probe.secret:
        raise ApplicationGatewayError("Application transport key changed")
    verified = verify_message(response, prepared.secret, expected_request_id=probe.request_id)
    if verified.get("ok") is not True:
        raise ApplicationGatewayError("Application health check failed")
    result = verified.get("result")
    if not isinstance(result, dict):
        raise ApplicationGatewayError("Application health response is invalid")
    validate_operation_payload(result, prepared.output_schema)
    if len(json.dumps(result, ensure_ascii=False)) > 1024 * 1024:
        raise ApplicationGatewayError("Application health response is too large")
    changed = db.execute(update(Installation).where(*_fence(probe)).values(health_checked_at=datetime.now(UTC))).rowcount
    if changed != 1:
        raise ApplicationGatewayError("Application changed during health check")
    db.commit()
    return result
