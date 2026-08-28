"""Administrator-only redacted diagnostics API."""

from fastapi import APIRouter, Depends, Response

from backend.config import get_settings
from backend.db.user import User
from backend.services.diagnostics import (
    DiagnosticPreview,
    build_diagnostic_bundle,
    build_diagnostic_preview,
    serialize_diagnostic_bundle,
)
from backend.utils.auth_dep import require_admin


router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])


@router.get("/preview", response_model=DiagnosticPreview)
def diagnostics_preview(_admin: User = Depends(require_admin)) -> DiagnosticPreview:
    return build_diagnostic_preview(get_settings())


@router.get("/bundle")
def diagnostics_bundle(_admin: User = Depends(require_admin)) -> Response:
    bundle = build_diagnostic_bundle(get_settings())
    filename = f"3mm-diagnostics-{bundle.generated_at:%Y%m%dT%H%M%SZ}.json"
    return Response(
        content=serialize_diagnostic_bundle(bundle),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
