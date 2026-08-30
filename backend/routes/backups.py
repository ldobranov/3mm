"""Administrator-only Standalone backup and disaster recovery API."""

import os
import re
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.backups import (
    BackupCatalogResponse,
    BackupOperationStatus,
    BackupPreviewResponse,
    build_backup_preview,
    list_backup_catalog,
    read_backup_operation_status,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError
from deployment.portable_backup import PORTABLE_MAGIC, remove_export


router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


class BackupCreateRequest(BaseModel):
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class BackupQueued(BaseModel):
    status: Literal["queued"] = "queued"


class BackupRestoreRequest(BaseModel):
    backup_id: str
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class PortableExportRequest(BaseModel):
    passphrase: SecretStr = Field(min_length=8, max_length=256)
    confirmation: str

    model_config = ConfigDict(extra="forbid")


class PortableExportReady(BaseModel):
    status: Literal["ready"] = "ready"
    export_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    backup_id: str
    filename: str


class PortableRestoreQueued(BackupQueued):
    backup_id: str


@router.get("", response_model=BackupCatalogResponse)
def backup_catalog(
    _admin: User = Depends(require_admin),
) -> BackupCatalogResponse:
    return list_backup_catalog(get_settings().backups.storage_dir)


@router.get("/preview", response_model=BackupPreviewResponse)
def backup_preview(
    admin: User = Depends(require_admin),
) -> BackupPreviewResponse:
    settings = get_settings()
    if not settings.updates.helper_socket.exists():
        return build_backup_preview(settings)
    try:
        preview = UpdateHelperClient(
            settings.updates.helper_socket,
            timeout_seconds=30,
        ).request_backup_preview(admin.id)
    except UpdateHelperError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return BackupPreviewResponse.model_validate(preview)


@router.get("/operation", response_model=BackupOperationStatus)
def backup_operation(
    _admin: User = Depends(require_admin),
) -> BackupOperationStatus:
    return read_backup_operation_status(
        get_settings().backups.storage_dir / "status.json"
    )


@router.post("", response_model=BackupQueued, status_code=status.HTTP_202_ACCEPTED)
def create_backup(
    payload: BackupCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BackupQueued:
    if payload.confirmation != "CREATE BACKUP":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    settings = get_settings()
    try:
        UpdateHelperClient(settings.updates.helper_socket).request_backup(admin.id)
    except UpdateHelperError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="BACKUP_REQUESTED",
            entity_type="backup",
            entity_name="standalone",
            changes={"protection": "device-bound", "export_policy": "local-only"},
        )
    )
    db.commit()
    return BackupQueued()


@router.post(
    "/restore",
    response_model=BackupQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def restore_backup(
    payload: BackupRestoreRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BackupQueued:
    if payload.confirmation != f"RESTORE {payload.backup_id}":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    settings = get_settings()
    try:
        UpdateHelperClient(settings.updates.helper_socket).request_restore(
            payload.backup_id,
            admin.id,
        )
    except UpdateHelperError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="RESTORE_REQUESTED",
            entity_type="backup",
            entity_name=payload.backup_id,
            changes={"scope": "standalone-full"},
        )
    )
    db.commit()
    return BackupQueued()


@router.post(
    "/{backup_id}/export",
    response_model=PortableExportReady,
)
def export_portable_backup(
    backup_id: str,
    payload: PortableExportRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortableExportReady:
    if re.fullmatch(r"bkp_\d{8}T\d{6}Z_[0-9a-f]{8}", backup_id) is None:
        raise HTTPException(status_code=404, detail="Backup not found")
    if payload.confirmation != f"DOWNLOAD {backup_id}":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    settings = get_settings()
    try:
        result = UpdateHelperClient(
            settings.updates.helper_socket,
            timeout_seconds=180,
        ).request_portable_export(
            backup_id,
            payload.passphrase.get_secret_value(),
            admin.id,
        )
    except UpdateHelperError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="BACKUP_EXPORTED",
            entity_type="backup",
            entity_name=backup_id,
            changes={"protection": "password", "format": "3mmrecovery-v1"},
        )
    )
    db.commit()
    return PortableExportReady.model_validate(result)


@router.get("/exports/{export_id}", response_class=FileResponse)
def download_portable_backup(
    export_id: str,
    background_tasks: BackgroundTasks,
    _admin: User = Depends(require_admin),
) -> FileResponse:
    if re.fullmatch(r"[0-9a-f]{32}", export_id) is None:
        raise HTTPException(status_code=404, detail="Recovery export not found")
    path = get_settings().backups.storage_dir / "exports" / (
        f"{export_id}.3mmrecovery"
    )
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=404, detail="Recovery export not found")
    background_tasks.add_task(remove_export, path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"3mm-recovery-{export_id}.3mmrecovery",
    )


@router.post(
    "/restore-file",
    response_model=PortableRestoreQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def restore_portable_backup(
    file: UploadFile = File(...),
    passphrase: str = Form(..., min_length=8, max_length=256),
    confirmation: str = Form(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PortableRestoreQueued:
    if confirmation != "RESTORE FILE":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    if not file.filename or not file.filename.lower().endswith(".3mmrecovery"):
        raise HTTPException(status_code=415, detail="Select a .3mmrecovery file")
    settings = get_settings()
    upload_id = uuid.uuid4().hex
    upload_dir = settings.backups.import_dir
    upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if upload_dir.is_symlink() or not upload_dir.is_dir():
        raise HTTPException(status_code=500, detail="Recovery upload storage is unsafe")
    upload_path = upload_dir / f"{upload_id}.3mmrecovery"
    written = 0
    try:
        with upload_path.open("xb") as target:
            os.chmod(upload_path, 0o600)
            while block := await file.read(1024 * 1024):
                written += len(block)
                if written > settings.backups.max_import_bytes:
                    raise HTTPException(status_code=413, detail="Recovery file is too large")
                target.write(block)
        with upload_path.open("rb") as source:
            if source.read(len(PORTABLE_MAGIC)) != PORTABLE_MAGIC:
                raise HTTPException(status_code=422, detail="Recovery file header is invalid")
        backup_id = UpdateHelperClient(
            settings.updates.helper_socket,
            timeout_seconds=180,
        ).request_portable_restore(upload_id, passphrase, admin.id)
    except HTTPException:
        upload_path.unlink(missing_ok=True)
        raise
    except UpdateHelperError as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        await file.close()
    db.add(
        AuditLog(
            user_id=admin.id,
            action="PORTABLE_RESTORE_REQUESTED",
            entity_type="backup",
            entity_name=backup_id,
            changes={"scope": "standalone-full", "source": "uploaded-file"},
        )
    )
    db.commit()
    return PortableRestoreQueued(backup_id=backup_id)
