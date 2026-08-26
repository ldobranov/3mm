"""Administrator-only catalog, staging and explicit system update approval API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.update_staging import (
    StagedUpdateResponse,
    UpdateApplyRequest,
    UpdateOperationStatus,
    UpdateStagingError,
    approve_staged_update,
    read_operation_status,
    stage_latest_update,
)
from backend.services.system_updates import (
    UpdateCatalogError,
    UpdateCheckResponse,
    check_update_catalog,
    read_local_update_status,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

router = APIRouter(prefix="/api/v1/system-updates", tags=["system-updates"])


@router.get("/status", response_model=UpdateCheckResponse)
def update_status(
    _admin: User = Depends(require_admin),
) -> UpdateCheckResponse:
    return read_local_update_status(get_settings().updates)


@router.post("/check", response_model=UpdateCheckResponse)
def check_for_updates(
    _admin: User = Depends(require_admin),
) -> UpdateCheckResponse:
    """Read GitHub release metadata without downloading or installing code."""
    return check_update_catalog(get_settings().updates)


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
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StagedUpdateResponse:
    settings = get_settings()
    try:
        result = stage_latest_update(
            settings.updates,
            settings.backend,
            settings.frontend,
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
        result = approve_staged_update(
            settings.updates,
            payload,
            requested_by_user_id=admin.id,
            scheduler=client.schedule,
        )
    except (UpdateHelperError, UpdateStagingError) as exc:
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
            },
        )
    )
    db.commit()
    return result
