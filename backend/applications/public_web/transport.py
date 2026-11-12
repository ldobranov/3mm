"""Short Core admission/finalization; application response I/O lives in Runtime."""
from __future__ import annotations

from dataclasses import asdict
import hmac
import re
import socket
import time
import uuid

from sqlalchemy import select

from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.applications.authority.management import lock_compatibility_admission, public_form_authority
from backend.applications.public_web import guests as public_form_guests
from backend.applications.runtime.gateway import (
    prepare_application_invocation, load_application_definition, find_operation,
    validate_operation_payload,
)
from backend.applications.public_web.routes import (
    ApplicationPublicWebError, prepare_public_form, prepare_public_http, resolve_public_route,
    validate_public_http_response,
)
from packages.platform_wire import remaining
from packages.protocol import ApplicationPublicHttpResponseV1
from packages.protocol.public_forms import FORM_ID, GUEST_COOKIE, GUEST_PROOF_FIELD, public_form_origin_host, public_form_result_schema
from components.system_runtime.application_transport import sign_message, verify_message, send_message

PUBLIC_WEB_CONTRACT = 1
PUBLIC_WEB_MESSAGE_BYTES = 1024 * 1024


def _public_request(value):
    fields = {"version", "request_id", "method", "path", "query", "headers"}
    if isinstance(value, dict) and value.get('method') == 'POST':
        fields.add('form')
    if isinstance(value, dict) and 'guest' in value:
        fields.add('guest')
    if (not isinstance(value, dict)
            or set(value) != fields
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["request_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", value["request_id"]) is None
            or value["method"] not in ("GET", "HEAD", "POST")
            or not isinstance(value["path"], str)
            or not isinstance(value["query"], dict) or not isinstance(value["headers"], dict)
            or not all(isinstance(k, str) and isinstance(v, list)
                       and all(isinstance(item, str) for item in v) for k, v in value["query"].items())
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in value["headers"].items())):
        raise ValueError("Invalid public request")
    if value['method'] == 'POST' and (value['query'] or value['headers'] or not isinstance(value['form'], dict)):
        raise ValueError('Invalid public form transport')
    if 'guest' in value:
        guest = value['guest']
        if (value['method'] not in ('GET', 'POST') or value['query']
                or not isinstance(guest, dict) or set(guest) != {'origin', 'cookie'}
                or not isinstance(guest['origin'], str) or len(guest['origin']) > 270
                or (guest['cookie'] is not None and (not isinstance(guest['cookie'], str)
                    or GUEST_COOKIE.fullmatch(guest['cookie']) is None))):
            raise ValueError('Invalid public guest transport')
        public_form_origin_host(guest['origin'])
    return {k: value[k] for k in ("method", "path", "query", "headers")}


def begin_public_http(db, settings, request, *, core_generation, runtime_generation):
    """Admit/send exactly once, then transfer this already connected socket.

    No response read, authority transaction or cached dispatch ticket survives
    this call. A received receipt authorizes validation only, never execution.
    """
    incoming = _public_request(request)
    resolved = resolve_public_route(db, incoming['method'], incoming['path'])
    route, _ = resolved
    reviewed = route.route.form_operation_id is not None
    if reviewed:
        with public_form_authority(db, route.installation_id) as pin:
            prepared, message, receipt = _prepare_dispatch(db, settings, request, incoming,
                core_generation, runtime_generation, pin=pin, installation_id=route.installation_id)
        # Reviewed admission linearizes before connect/send. A concurrent later
        # revocation cannot recall it, but completion must verify authority again.
    else:
        prepared, message, receipt = _prepare_dispatch(db, settings, request, incoming,
            core_generation, runtime_generation, resolved=resolved)
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        deadline = time.monotonic() + 3
        connection.settimeout(remaining(deadline)); connection.connect(str(prepared.socket_path))
        connection.settimeout(remaining(deadline)); send_message(connection, message)
        if not reviewed:
            db.commit()  # Preserve compatibility read admission ordering.
        return {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": True,
                "receipt": receipt, "timeout_seconds": prepared.timeout_seconds}, connection
    except BaseException:
        connection.close(); db.rollback(); raise


def _prepare_dispatch(db, settings, request, incoming, core_generation, runtime_generation,
                      *, pin=None, installation_id=None, resolved=None):
    reviewed = pin is not None
    is_form = incoming['method'] == 'POST'
    context = {"audience": "public", "correlation_id": request["request_id"]}
    if is_form:
        binding, installation, package, form_id, payload = prepare_public_form(db, incoming['path'], request['form'])
        context['idempotency_key'] = form_id
        operation_id = binding.route.form_operation_id
    else:
        binding, installation, package, http = prepare_public_http(db, settings, **incoming, _resolved=resolved)
        payload = http.model_dump(mode='json')
        operation_id = binding.route.handler_operation_id
    if reviewed and (installation.id != installation_id or package.sha256 != pin.sha256):
        raise ValueError('Public form route changed during admission')
    guest_result = None
    if binding.route.guest_session:
        guest_result = _prepare_guest(request, context, binding, installation, package, core_generation, is_form)
    prepared = prepare_application_invocation(installation, package, settings,
        operation_id, payload, context, required_audience="public", reviewed_public_http=reviewed)
    if not reviewed:
        lock_compatibility_admission(db, installation, required=True)
    message = sign_message({"version": 1, "request_id": uuid.uuid4().hex,
        "timestamp": int(time.time()), "operation_id": prepared.operation_id,
        "payload": prepared.payload, "context": prepared.context,
        **({"relational_invocation": prepared.relational_invocation}
           if prepared.relational_invocation is not None else {})}, prepared.secret)
    receipt = sign_message({"version": 1, "request_id": message["request_id"],
        "timestamp": message["timestamp"],
        "kind": ('public-form-result-only' if is_form else 'public-form-page-result-only')
        if reviewed else 'public-web-result-only',
        "instance_id": installation.instance_id, "package_sha256": package.sha256,
        "authority_epoch": installation.authority_epoch, "route_id": binding.route.route_id,
        "core_generation": core_generation, "runtime_generation": runtime_generation,
        **({'guest': guest_result} if guest_result is not None else {})}, prepared.secret)
    return prepared, message, receipt


def _prepare_guest(request, context, binding, installation, package, core_generation, is_form):
    incoming = request.get('guest')
    if incoming is None:
        raise ApplicationPublicWebError('Public guest access is unavailable', status_code=403)
    scope = (core_generation, installation.instance_id, installation.authority_incarnation,
             installation.authority_epoch, package.sha256, binding.route.route_id,
             binding.route.path, incoming['origin'])
    guest = public_form_guests.resolve(scope, incoming['cookie'])
    new_cookie = None
    if is_form:
        proof = request['form'].get(GUEST_PROOF_FIELD)
        if (guest is None or not isinstance(proof, str) or FORM_ID.fullmatch(proof) is None
                or not hmac.compare_digest(proof, guest.guest_id)):
            raise ApplicationPublicWebError('Public guest session is not current', status_code=403)
    elif guest is None:
        guest, new_cookie = public_form_guests.issue(scope)
    context['public_guest'] = asdict(guest)
    return {'expires_at': guest.expires_at, 'cookie': new_cookie}


def finish_public_http(db, settings, receipt, response, *, core_generation, runtime_generation):
    fields = {"version", "request_id", "timestamp", "signature", "kind", "instance_id", "package_sha256",
              "authority_epoch", "route_id", "core_generation", "runtime_generation"}
    if isinstance(receipt, dict) and 'guest' in receipt:
        fields.add('guest')
    if (not isinstance(receipt, dict)
            or set(receipt) != fields
            or receipt["kind"] not in ("public-web-result-only", "public-form-result-only", "public-form-page-result-only")
            or receipt["core_generation"] != core_generation
            or receipt["runtime_generation"] != runtime_generation
            or not isinstance(receipt["instance_id"], str)
            or re.fullmatch(r"[0-9a-f]{24}", receipt["instance_id"]) is None):
        raise ValueError("Invalid public result receipt")
    secret = (settings.key_root / (receipt["instance_id"] + ".key")).read_bytes()
    if len(secret) != 32: raise ValueError("Invalid transport key")
    verify_message(receipt, secret)
    if receipt['kind'] == 'public-web-result-only':
        return _finish_dispatch(db, settings, receipt, response)
    installation_id = db.scalar(select(ApplicationExtensionInstallation.id).where(
        ApplicationExtensionInstallation.instance_id == receipt['instance_id']))
    if installation_id is None:
        raise ValueError('Public form installation is unavailable')
    with public_form_authority(db, installation_id) as pin:
        if pin.sha256 != receipt['package_sha256']:
            raise ValueError('Public form package changed')
        return _finish_dispatch(db, settings, receipt, response, installation_id=installation_id)


def _finish_dispatch(db, settings, receipt, response, *, installation_id=None):
    reviewed = installation_id is not None
    installation = db.scalar(select(ApplicationExtensionInstallation).where(
        ApplicationExtensionInstallation.instance_id == receipt["instance_id"]))
    if (installation is None or not installation.enabled or installation.status != "active"
            or installation.authority_mode != ('enforced' if reviewed else 'compatibility')
            or reviewed and installation.id != installation_id
            or installation.authority_epoch != receipt["authority_epoch"]):
        raise ValueError("Public application authority changed")
    package = db.get(ModulePackage, installation.module_package_id)
    if (package is None or package.module_id != installation.module_id
            or package.version != installation.active_version or package.sha256 != receipt["package_sha256"]):
        raise ValueError("Public application package changed")
    definition = load_application_definition(package)
    route = next((r for r in definition.public_http_routes if r.route_id == receipt["route_id"]), None)
    if route is None or reviewed != (route.form_operation_id is not None):
        raise ValueError("Public route is unavailable")
    secret = (settings.key_root / (installation.instance_id + '.key')).read_bytes()
    if len(secret) != 32: raise ValueError('Invalid transport key')
    verify_message(receipt, secret)
    guest_cookie = _completion_guest(receipt, route)
    verified = verify_message(response, secret, expected_request_id=receipt["request_id"])
    if verified.get("ok") is not True or not isinstance(verified.get("result"), dict):
        raise ValueError("Invalid application result")
    result = verified["result"]
    if receipt['kind'] == 'public-form-result-only':
        validate_operation_payload(result, public_form_result_schema())
        status, body = {'accepted': (200, 'Form received.\n'),
                        'conflict': (400, 'Form request ID already used for different data.\n'),
                        'capacity_reached': (429, 'Form is currently not accepting new submissions.\n')}[result['status']]
        validated = ApplicationPublicHttpResponseV1(status=status, content_type='text/plain; charset=utf-8',
                                                   headers={'Cache-Control': 'no-store'}, body=body)
    else:
        validate_operation_payload(result, find_operation(definition, route.handler_operation_id).output_schema)
        from backend.applications.public_web.routes import PublicRouteBinding
        validated = validate_public_http_response(
            PublicRouteBinding(package.module_id, package.id, installation.id, route), result)
        if reviewed:
            if validated.status not in (200, 400, 404, 503):
                raise ValueError('Public form page cannot redirect or serve cached content')
            validated = validated.model_copy(update={'headers': {'cache-control': 'no-store'}})
    return {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": True,
            "response": validated.model_dump(mode="json", exclude_none=True),
            **({'guest_cookie': guest_cookie} if guest_cookie is not None and validated.status == 200 else {})}


def _completion_guest(receipt, route):
    if ('guest' in receipt) != bool(route.guest_session):
        raise ValueError('Public guest declaration changed')
    if not route.guest_session:
        return None
    guest = receipt['guest']
    if (not isinstance(guest, dict) or set(guest) != {'expires_at', 'cookie'}
            or type(guest['expires_at']) is not int or guest['expires_at'] <= time.time()):
        raise ValueError('Public guest session expired before result confirmation')
    token = guest['cookie']
    if token is not None:
        match = GUEST_COOKIE.fullmatch(token) if isinstance(token, str) else None
        if (receipt['kind'] != 'public-form-page-result-only' or match is None
                or int(match[2]) != guest['expires_at']):
            raise ValueError('Invalid public guest result')
    return token


def handle_public_http(connection, request, *, key_root, core_generation, runtime_generation):
    from backend.database import SessionLocal
    from packages.platform_wire import send_authority_frame
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
                  "status": exc.status_code if exc.status_code in {400,403,404,405} else 503}
    except Exception:
        result = {"public_web_contract": PUBLIC_WEB_CONTRACT, "ok": False, "status": 503}
    try:
        connection.settimeout(3)
        send_authority_frame(connection, result, origin=origin)
    finally:
        if origin is not None: origin.close()
