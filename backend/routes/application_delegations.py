"""Current route actor/access and exact operation delegation; no client actor input."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from backend.services import application_delegations as service
from backend.services.application_access import (ANONYMOUS_PRINCIPAL, application_permission_ids,
    resolve_application_principal, can_access_application_operation)
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.authority_metadata import AuthorityMetadataError
from backend.utils.db_utils import get_db
from three_mm_protocol.application_delegation import ActorAccessV1, DelegationCreateV1

router = APIRouter(tags=["application-access"])


class CreateBody(DelegationCreateV1):
    ui_context: dict


def _view(db, module_id, entrypoint_id, binding, authorization):
    from backend.routes.application_extensions import ApplicationUiBinding, _installation, _active_package, _definition, _ui_route
    try: binding = ApplicationUiBinding.model_validate(binding)
    except ValidationError:
        raise HTTPException(422, "Exact application route binding is required") from None
    if binding.entrypoint_id != entrypoint_id: raise HTTPException(403, "Route binding changed")
    app = _installation(db, module_id); package = _active_package(db, app)
    definition = _definition(package)
    route = next((r for r in definition.routes if r.entrypoint_id == entrypoint_id), None)
    if route is None: raise HTTPException(404, "Application route was not found")
    principal = ANONYMOUS_PRINCIPAL if route.audience == "public" else resolve_application_principal(authorization, db)
    permissions = (application_permission_ids(db, app.id, principal.user_id)
        & frozenset(p.permission_id for p in definition.permissions)) if principal.kind == "user" else frozenset()
    _, route = _ui_route(package, binding, principal, permissions, db=db, installation=app)
    operations = sorted(op.operation_id for op in definition.operations if (
        route.audience == "kiosk" and "kiosk" in op.audiences
        or can_access_application_operation(op, principal, audience=route.audience, permission_ids=permissions)))
    value = ActorAccessV1(entrypoint_id=entrypoint_id, audience=route.audience,
        built_ui_sha256=binding.built_ui_sha256,
        actor={"kind": principal.kind, "user_id": principal.user_id, "subject_id": principal.subject_id, "terminal_id": principal.terminal_id,
            "platform_administrator": principal.is_admin},
        executor={"module_id": module_id, "instance_id": app.instance_id, "artifact_sha256": package.sha256},
        permission_ids=sorted(permissions), allowed_operation_ids=operations,
        delegated_operation_ids=sorted(set(route.delegated_operations) & set(operations)))
    return app.id, value


@router.get("/{module_id}/ui-host/{entrypoint_id}/access")
def actor_access(module_id: str, entrypoint_id: str, response: Response,
    artifact_sha256: str = Query(pattern=r"^[0-9a-f]{64}$"),
    built_ui_sha256: str | None = Query(default=None, pattern=r"^[0-9a-f]{64}$"),
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    _, value = _view(db, module_id, entrypoint_id, dict(host_version=1, entrypoint_id=entrypoint_id,
        artifact_sha256=artifact_sha256, built_ui_sha256=built_ui_sha256), authorization)
    return value.model_dump(mode="json")


async def _run(response, operation):
    response.headers["Cache-Control"] = "no-store"
    try: return await run_in_threadpool(operation)
    except HTTPException: raise
    except (ValueError, SQLAlchemyError, AuthorityReviewKeyError, AuthorityMetadataError, service.authority.AuthorityManagementError, OSError):
        raise HTTPException(409, {"code": "delegation_unavailable"}) from None


@router.post("/{module_id}/ui-host/{entrypoint_id}/delegations")
async def create(module_id: str, entrypoint_id: str, request: CreateBody, response: Response,
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    identifier, access = _view(db, module_id, entrypoint_id, request.ui_context, authorization)
    if access.audience != "operator" or request.operation_id not in access.delegated_operation_ids:
        raise HTTPException(403, "Operation delegation is not allowed on this route")
    engine = db.get_bind().engine; db.rollback()
    return await _run(response, lambda: service.create_delegation(engine, identifier, request.ui_context,
        authorization, request.model_dump(exclude={"ui_context"})))


@router.get("/{module_id}/delegations/{delegation_id}")
async def lookup(module_id: str, delegation_id: str, response: Response,
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    from backend.routes.application_extensions import _installation
    service.login_actor(db, authorization)
    identifier = _installation(db, module_id).id; engine = db.get_bind().engine; db.rollback()
    return await _run(response, lambda: service.inspect_delegation(engine, identifier, delegation_id, authorization=authorization))


@router.post("/{module_id}/delegations/{delegation_id}/cancel")
async def cancel(module_id: str, delegation_id: str, response: Response,
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    from backend.routes.application_extensions import _installation
    service.login_actor(db, authorization)
    identifier = _installation(db, module_id).id; engine = db.get_bind().engine; db.rollback()
    return await _run(response, lambda: service.inspect_delegation(engine, identifier, delegation_id, authorization=authorization, cancel=True))
