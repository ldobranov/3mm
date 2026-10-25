"""Short Core admission/finalization; application response I/O lives in Runtime."""
from __future__ import annotations

import re
import socket
import time
import uuid

from sqlalchemy import select

from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_authority_management import lock_compatibility_admission
from backend.services.application_extensions import (
    prepare_application_invocation, load_application_definition, find_operation,
    validate_operation_payload,
)
from backend.services.application_public_web import (
    ApplicationPublicWebError, prepare_public_http, validate_public_http_response,
)
from three_mm_platform_wire import remaining
from three_mm_runtime.application_transport import sign_message, verify_message, send_message

PUBLIC_WEB_CONTRACT = 1
PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024


def _public_request(value):
    if (not isinstance(value, dict)
            or set(value) != {"version", "request_id", "method", "path", "query", "headers"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["request_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", value["request_id"]) is None
            or value["method"] not in {"GET", "HEAD"}
            or not isinstance(value["path"], str)
            or not isinstance(value["query"], dict) or not isinstance(value["headers"], dict)
            or not all(isinstance(k, str) and isinstance(v, list)
                       and all(isinstance(item, str) for item in v) for k, v in value["query"].items())
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in value["headers"].items())):
        raise ValueError("Invalid public request")
    return {k: value[k] for k in ("method", "path", "query", "headers")}


def begin_public_http(db, settings, request, *, core_generation, runtime_generation):
    """Admit/send exactly once, then transfer this already connected socket.

    No response read, authority transaction or cached dispatch ticket survives
    this call. A received receipt authorizes validation only, never execution.
    """
    binding, installation, package, payload = prepare_public_http(db, settings, **_public_request(request))
    prepared = prepare_application_invocation(installation, package, settings,
        binding.route.handler_operation_id, payload.model_dump(mode="json"),
        {"audience": "public", "correlation_id": request["request_id"]}, required_audience="public")
    lock_compatibility_admission(db, installation, required=True)
    message = sign_message({"version": 1, "request_id": uuid.uuid4().hex,
        "timestamp": int(time.time()), "operation_id": prepared.operation_id,
        "payload": prepared.payload, "context": prepared.context,
        **({"relational_invocation": prepared.relational_invocation}
           if prepared.relational_invocation is not None else {})}, prepared.secret)
    receipt = sign_message({"version": 1, "request_id": message["request_id"],
        "timestamp": message["timestamp"], "kind": "public-web-result-only",
        "instance_id": installation.instance_id, "package_sha256": package.sha256,
        "authority_epoch": installation.authority_epoch, "route_id": binding.route.route_id,
        "core_generation": core_generation, "runtime_generation": runtime_generation}, prepared.secret)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        # Bound connect/send as one short Core operation, including a full buffer.
        deadline = time.monotonic() + 3
        connection.settimeout(remaining(deadline)); connection.connect(str(prepared.socket_path))
        connection.settimeout(remaining(deadline)); send_message(connection, message)
        db.commit()  # Compatibility admission linearizes before disable/adoption.
        return {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": True,
                "receipt": receipt, "timeout_seconds": prepared.timeout_seconds}, connection
    except BaseException:
        connection.close(); db.rollback(); raise


def finish_public_http(db, settings, receipt, response, *, core_generation, runtime_generation):
    if (not isinstance(receipt, dict)
            or set(receipt) != {"version", "request_id", "timestamp", "signature", "kind",
                "instance_id", "package_sha256", "authority_epoch", "route_id",
                "core_generation", "runtime_generation"}
            or receipt["kind"] != "public-web-result-only"
            or receipt["core_generation"] != core_generation
            or receipt["runtime_generation"] != runtime_generation
            or not isinstance(receipt["instance_id"], str)
            or re.fullmatch(r"[0-9a-f]{24}", receipt["instance_id"]) is None):
        raise ValueError("Invalid public result receipt")
    secret = (settings.key_root / (receipt["instance_id"] + ".key")).read_bytes()
    if len(secret) != 32: raise ValueError("Invalid transport key")
    verify_message(receipt, secret)
    installation = db.scalar(select(ApplicationExtensionInstallation).where(
        ApplicationExtensionInstallation.instance_id == receipt["instance_id"]))
    if (installation is None or not installation.enabled or installation.status != "active"
            or installation.authority_mode != "compatibility"
            or installation.authority_epoch != receipt["authority_epoch"]):
        raise ValueError("Public application authority changed")
    package = db.get(ModulePackage, installation.module_package_id)
    if (package is None or package.module_id != installation.module_id
            or package.version != installation.active_version or package.sha256 != receipt["package_sha256"]):
        raise ValueError("Public application package changed")
    definition = load_application_definition(package)
    route = next((r for r in definition.public_http_routes if r.route_id == receipt["route_id"]), None)
    if route is None: raise ValueError("Public route is unavailable")
    verified = verify_message(response, secret, expected_request_id=receipt["request_id"])
    if verified.get("ok") is not True or not isinstance(verified.get("result"), dict):
        raise ValueError("Invalid application result")
    result = verified["result"]
    validate_operation_payload(result, find_operation(definition, route.handler_operation_id).output_schema)
    from backend.services.application_public_web import PublicRouteBinding
    validated = validate_public_http_response(
        PublicRouteBinding(package.module_id, package.id, installation.id, route), result)
    return {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": True,
            "response": validated.model_dump(mode="json", exclude_none=True)}


def handle_public_http(connection, request, *, key_root, core_generation, runtime_generation):
    from backend.database import SessionLocal
    from three_mm_platform_wire import send_authority_frame
    origin = None
    try:
        settings = ApplicationRuntimeSettings(key_root=key_root)
        with SessionLocal() as db:
            if set(request) == {"public_web_contract", "begin"}:
                result, origin = begin_public_http(db, settings, request["begin"],
                    core_generation=core_generation, runtime_generation=runtime_generation)
            elif set(request) == {"public_web_contract", "receipt", "response"}:
                result = finish_public_http(db, settings, request["receipt"], request["response"],
                    core_generation=core_generation, runtime_generation=runtime_generation)
            else: raise ValueError("Invalid public authority request")
    except ApplicationPublicWebError as exc:
        result = {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": False,
                  "status": exc.status_code if exc.status_code in {400,404,405} else 503}
    except Exception:
        result = {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": False, "status": 503}
    try:
        connection.settimeout(3)
        send_authority_frame(connection, result, origin=origin)
    finally:
        if origin is not None: origin.close()
