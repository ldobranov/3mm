"""Administrator-only, read-only system update catalog API."""

from fastapi import APIRouter, Depends

from backend.config import get_settings
from backend.db.user import User
from backend.services.system_updates import (
    UpdateCheckResponse,
    check_update_catalog,
    read_local_update_status,
)
from backend.utils.auth_dep import require_admin

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
