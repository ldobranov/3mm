"""Administrator-only network recovery policy and setup activation API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services.network_recovery import (
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
    try:
        UpdateHelperClient(settings.helper_socket).request_network_setup(admin.id)
    except UpdateHelperError as exc:
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
    )
