"""Administrator-only catalog, staging and explicit system update approval API."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.system_updates import (
    UpdateCatalogError,
    UpdateChannel,
    UpdateCheckResponse,
    check_update_catalog,
    read_local_update_status,
)
from backend.services.update_policy import (
    UpdatePolicyError,
    UpdatePolicyRequest,
    UpdatePolicyStatus,
    check_and_cache_update_catalog,
    ensure_apply_is_allowed,
    read_update_policy,
    read_update_policy_status,
    save_update_policy,
)
from backend.services.update_staging import (
    StagedUpdateResponse,
    UpdateApplyRequest,
    UpdateOperationStatus,
    UpdateStagingError,
    approve_staged_update,
    read_operation_status,
    stage_latest_update,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError
from backend.services.platform_runtime_updates import (
    RuntimeUpdateStatus, RuntimePrepareRequest, RuntimeApplyRequest, RuntimeAccepted,
)

router = APIRouter(prefix="/api/v1/system-updates", tags=["system-updates"])

@router.get('/runtime', response_model=RuntimeUpdateStatus)
def platform_runtime_status(response: Response, _admin: User = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        value = UpdateHelperClient(get_settings().updates.helper_socket).platform_runtime_status()
        return RuntimeUpdateStatus.model_validate(value)
    except (UpdateHelperError, ValueError, KeyError):
        raise HTTPException(409, 'Runtime status is unavailable; Core administration remains available.') from None


def _runtime_operation(action, payload, admin, db):
    data = payload.model_dump(exclude={'maintenance_override'})
    data.update(action=action, requested_by_user_id=admin.id)
    try:
        identifier = UpdateHelperClient(get_settings().updates.helper_socket).platform_runtime_operation(data)
    except (UpdateHelperError, ValueError, KeyError):
        raise HTTPException(409, 'Runtime operation could not be confirmed. Refresh its status; do not resend.') from None
    db.add(AuditLog(user_id=admin.id, action='PLATFORM_RUNTIME_OPERATION_ACCEPTED',
        entity_type='platform_runtime', entity_name=identifier,
        changes={'operation': action, 'request_id': identifier}))
    db.commit()
    return RuntimeAccepted(request_id=identifier)


@router.post('/runtime/prepare', response_model=RuntimeAccepted, status_code=202)
def prepare_platform_runtime(payload: RuntimePrepareRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _runtime_operation('platform_runtime_prepare', payload, admin, db)


@router.post('/runtime/apply', response_model=RuntimeAccepted, status_code=202)
def apply_platform_runtime(payload: RuntimeApplyRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.confirmation != 'UPDATE RUNTIME ' + payload.build_id:
        raise HTTPException(422, 'Confirm the exact Runtime build.')
    try:
        ensure_apply_is_allowed(get_settings().updates, maintenance_override=payload.maintenance_override)
    except UpdatePolicyError as exc:
        raise HTTPException(409, str(exc)) from None
    return _runtime_operation('platform_runtime_apply', payload, admin, db)


@router.post('/runtime/recover', response_model=RuntimeAccepted, status_code=202)
def recover_platform_runtime(payload: RuntimePrepareRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _runtime_operation('platform_runtime_recover', payload, admin, db)


class UpdateChannelRequest(BaseModel):
    channel: UpdateChannel = "stable"

    model_config = ConfigDict(extra="forbid")


@router.get("/status", response_model=UpdateCheckResponse)
def update_status(
    _admin: User = Depends(require_admin),
) -> UpdateCheckResponse:
    return read_local_update_status(get_settings().updates)


@router.post("/check", response_model=UpdateCheckResponse)
def check_for_updates(
    payload: UpdateChannelRequest | None = None,
    _admin: User = Depends(require_admin),
) -> UpdateCheckResponse:
    """Read GitHub release metadata without downloading or installing code."""
    try:
        return check_and_cache_update_catalog(
            get_settings().updates,
            channel=(payload or UpdateChannelRequest()).channel,
            checker=check_update_catalog,
        )
    except (UpdateCatalogError, UpdatePolicyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/policy", response_model=UpdatePolicyStatus)
def update_policy_status(
    _admin: User = Depends(require_admin),
) -> UpdatePolicyStatus:
    try:
        return read_update_policy_status(get_settings().updates)
    except UpdatePolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/policy", response_model=UpdatePolicyStatus)
def update_policy(
    payload: UpdatePolicyRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UpdatePolicyStatus:
    settings = get_settings().updates
    try:
        previous = read_update_policy(settings)
        saved = save_update_policy(settings, payload)
        result = read_update_policy_status(settings)
    except UpdatePolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="SYSTEM_UPDATE_POLICY_CHANGED",
            entity_type="system_update_policy",
            entity_name="standalone",
            changes={
                "before": previous.model_dump(mode="json"),
                "after": saved.model_dump(mode="json"),
            },
        )
    )
    db.commit()
    return result


@router.get("/operation", response_model=UpdateOperationStatus)
def update_operation_status(
    _admin: User = Depends(require_admin),
) -> UpdateOperationStatus:
    try:
        return read_operation_status(get_settings().updates)
    except UpdateStagingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/stage",
    response_model=StagedUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
def stage_update(
    payload: UpdateChannelRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StagedUpdateResponse:
    settings = get_settings()
    channel = (payload or UpdateChannelRequest()).channel
    try:
        result = stage_latest_update(
            settings.updates,
            settings.backend,
            settings.frontend,
            channel=channel,
        )
    except (UpdateCatalogError, UpdateStagingError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="SYSTEM_UPDATE_STAGED",
            entity_type="system_update",
            entity_name=result.staged.release_id,
            changes={
                "version": result.staged.version,
                "commit": result.staged.commit,
                "channel": result.staged.channel,
                "architecture": result.staged.architecture,
                "dependencies": result.staged.dependencies,
            },
        )
    )
    db.commit()
    return result


@router.post(
    "/apply",
    response_model=UpdateOperationStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_update(
    payload: UpdateApplyRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UpdateOperationStatus:
    settings = get_settings()
    client = UpdateHelperClient(settings.updates.helper_socket)
    try:
        policy_status = ensure_apply_is_allowed(
            settings.updates,
            maintenance_override=payload.maintenance_override,
        )
        result = approve_staged_update(
            settings.updates,
            payload,
            requested_by_user_id=admin.id,
            scheduler=client.schedule,
        )
    except (UpdateHelperError, UpdatePolicyError, UpdateStagingError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="SYSTEM_UPDATE_APPROVED",
            entity_type="system_update",
            entity_name=result.release_id,
            changes={
                "version": result.version,
                "commit": result.commit,
                "state": result.state,
                "maintenance_window_enabled": (
                    policy_status.policy.maintenance_window_enabled
                ),
                "within_maintenance_window": (policy_status.within_maintenance_window),
                "maintenance_override": payload.maintenance_override,
            },
        )
    )
    db.commit()
    return result
