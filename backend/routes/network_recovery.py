"""Administrator-only network recovery policy and setup activation API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.network_recovery import (
    AccessPointRequest, AccessPointStopRequest,
    NetworkRecoveryPolicyRequest,
    NetworkRecoveryStatus,
    NetworkSetupQueued,
    NetworkSetupRequest,
    network_setup_details,
    read_network_recovery_status,
    save_network_recovery_policy,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_provisioning import NetworkRecoveryStoreError
from three_mm_provisioning.persistence import FileProvisioningStore, ProvisioningStoreError
from three_mm_provisioning.setup_access import FileSetupAccessStore
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

router = APIRouter(prefix="/api/v1/network-recovery", tags=["network-recovery"])


@router.get("/status", response_model=NetworkRecoveryStatus)
def network_recovery_status(
    _admin: User = Depends(require_admin),
) -> NetworkRecoveryStatus:
    try:
        return read_network_recovery_status(get_settings().network_recovery)
    except NetworkRecoveryStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/policy", response_model=NetworkRecoveryStatus)
def update_network_recovery_policy(
    payload: NetworkRecoveryPolicyRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NetworkRecoveryStatus:
    settings = get_settings().network_recovery
    previous_enabled: bool | None = None
    try:
        previous = read_network_recovery_status(settings)
        previous_enabled = previous.automatic_setup_enabled
    except NetworkRecoveryStoreError:
        pass
    try:
        saved = save_network_recovery_policy(settings, payload)
        result = read_network_recovery_status(settings)
    except NetworkRecoveryStoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="NETWORK_RECOVERY_POLICY_CHANGED",
            entity_type="network_recovery_policy",
            entity_name="standalone",
            changes={
                "before": {
                    "automatic_setup_enabled": previous_enabled,
                },
                "after": {
                    "automatic_setup_enabled": saved.automatic_setup_enabled,
                },
            },
        )
    )
    db.commit()
    return result


@router.post(
    "/setup",
    response_model=NetworkSetupQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_network_setup(
    payload: NetworkSetupRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NetworkSetupQueued:
    if payload.confirmation != "START SETUP":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    settings = get_settings().network_recovery
    setup_network, setup_url = network_setup_details(settings)
    access = FileSetupAccessStore(settings.marker_file.parent)
    try:
        access_code = access.issue(FileProvisioningStore(settings.marker_file.parent).load_runtime_snapshot())
    except (OSError, ProvisioningStoreError, ValueError):
        raise HTTPException(status_code=503, detail="setup_access_unavailable") from None
    try:
        UpdateHelperClient(settings.helper_socket).request_network_setup(admin.id)
    except UpdateHelperError as exc:
        access.revoke()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="NETWORK_SETUP_REQUESTED",
            entity_type="network_recovery",
            entity_name="standalone",
            changes={"automatic": False},
        )
    )
    db.commit()
    return NetworkSetupQueued(
        setup_network=setup_network,
        setup_url=setup_url,
        access_code=access_code,
    )


def _issue_access(settings):
    store = FileSetupAccessStore(settings.marker_file.parent)
    try:
        code = store.issue(FileProvisioningStore(settings.marker_file.parent).load_runtime_snapshot())
    except (OSError, ProvisioningStoreError, ValueError):
        raise HTTPException(status_code=503, detail="setup_access_unavailable") from None
    return store, code


@router.post("/access-point", status_code=status.HTTP_202_ACCEPTED)
def start_access_point(payload: AccessPointRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    settings = get_settings().network_recovery
    current = read_network_recovery_status(settings).access_point
    if payload.interface not in current["interfaces"]:
        raise HTTPException(status_code=409, detail="access_point_unavailable")
    if current["state"] in {"starting", "active", "restoring", "unavailable"}:
        raise HTTPException(status_code=409, detail="access_point_busy")
    from three_mm_provisioning.setup_access_point import setup_ssid
    try:
        network = setup_ssid(settings.machine_id_file)
    except OSError:
        raise HTTPException(status_code=503, detail="access_point_unavailable") from None
    access, code = _issue_access(settings)
    identifier = uuid.uuid4().hex
    try:
        UpdateHelperClient(settings.helper_socket).request_access_point(
            "start", admin.id, identifier, interface=payload.interface, duration=payload.duration_seconds)
    except UpdateHelperError:
        access.revoke()
        raise HTTPException(status_code=409, detail="access_point_schedule_failed") from None
    db.add(AuditLog(user_id=admin.id, action="ACCESS_POINT_REQUESTED", entity_type="network_recovery",
                   changes={"interface": payload.interface, "duration_seconds": payload.duration_seconds}))
    db.commit()
    return {"status": "queued", "id": identifier, "setup_network": network,
            "setup_url": "http://10.42.0.1:8895/setup", "access_code": code,
            "duration_seconds": payload.duration_seconds}


@router.post("/access-point/stop", status_code=status.HTTP_202_ACCEPTED)
def stop_access_point(payload: AccessPointStopRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    settings = get_settings().network_recovery
    try:
        UpdateHelperClient(settings.helper_socket).request_access_point("stop", admin.id, payload.id)
    except UpdateHelperError:
        raise HTTPException(status_code=409, detail="access_point_schedule_failed") from None
    db.add(AuditLog(user_id=admin.id, action="ACCESS_POINT_STOP_REQUESTED", entity_type="network_recovery"))
    db.commit()
    return {"status": "queued"}
