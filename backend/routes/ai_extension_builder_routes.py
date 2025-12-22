from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.schemas.ai_extension_builder import (
    ClarifyExtensionRequest,
    ClarifyExtensionResponse,
    GenerateExtensionRequest,
    GenerateExtensionResponse,
    PackageExtensionRequest,
)
from backend.utils.auth_dep import require_user
from backend.utils.ai_extension_builder.generator import build_extension_zip, package_extension_zip
from backend.utils.ai_extension_builder.clarifier import clarify_extension_spec
from backend.utils.db_utils import get_db
from backend.db.settings import Settings
from backend.utils.secure_settings import decrypt_secret, SecureSettingsError


router = APIRouter()


def _require_admin(claims: dict) -> None:
    role = claims.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/api/ai/extensions/clarify", response_model=ClarifyExtensionResponse)
def clarify_extension(
    payload: ClarifyExtensionRequest,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Multi-step flow (step 1): ask AI to refine the spec and ask clarifying questions."""

    _require_admin(claims)

    # Load AI provider + keys from application settings (encrypted).
    def get_setting(key: str) -> str | None:
        row = (
            db.query(Settings)
            .filter(Settings.key == key, Settings.language_code.is_(None), Settings.user_id.is_(None))
            .first()
        )
        return row.value if row else None

    settings_ai_provider = (get_setting("ai_provider") or "").strip().lower() or None
    request_ai_provider = (payload.ai_provider or "").strip().lower() or None
    ai_provider = request_ai_provider if request_ai_provider and request_ai_provider != "auto" else settings_ai_provider

    groq_key_enc = get_setting("ai_groq_api_key")
    openrouter_key_enc = get_setting("ai_openrouter_api_key")

    try:
        groq_key = decrypt_secret(groq_key_enc) if groq_key_enc else None
        openrouter_key = decrypt_secret(openrouter_key_enc) if openrouter_key_enc else None
    except SecureSettingsError as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI settings decryption is not configured: {str(e)}",
        )

    return clarify_extension_spec(
        draft_spec=payload.draft_spec,
        goal=payload.goal,
        model=payload.model,
        ai_provider=ai_provider,
        groq_api_key=groq_key,
        openrouter_api_key=openrouter_key,
    )


@router.post("/api/ai/extensions/generate", response_model=GenerateExtensionResponse)
def generate_extension(
    payload: GenerateExtensionRequest,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Generate an extension ZIP (base64) from a structured spec.

    V1: template-based scaffolding (relationship-aware stubs + en/bg locales).
    """

    _require_admin(claims)

    # Load AI provider + keys from application settings (encrypted).
    def get_setting(key: str) -> str | None:
        row = (
            db.query(Settings)
            .filter(Settings.key == key, Settings.language_code.is_(None), Settings.user_id.is_(None))
            .first()
        )
        return row.value if row else None

    settings_ai_provider = (get_setting("ai_provider") or "").strip().lower() or None
    request_ai_provider = (payload.ai_provider or "").strip().lower() or None
    # Request can override settings; "auto" means no explicit provider.
    ai_provider = request_ai_provider if request_ai_provider and request_ai_provider != "auto" else settings_ai_provider
    groq_key_enc = get_setting("ai_groq_api_key")
    openrouter_key_enc = get_setting("ai_openrouter_api_key")

    try:
        groq_key = decrypt_secret(groq_key_enc) if groq_key_enc else None
        openrouter_key = decrypt_secret(openrouter_key_enc) if openrouter_key_enc else None
    except SecureSettingsError as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI settings decryption is not configured: {str(e)}",
        )

    report, zip_b64, files_text = build_extension_zip(
        payload.spec,
        instructions=payload.instructions,
        use_ai=payload.use_ai,
        model=payload.model,
        ai_provider=ai_provider,
        groq_api_key=groq_key,
        openrouter_api_key=openrouter_key,
    )
    return GenerateExtensionResponse(report=report, zip_base64=zip_b64, files_text=files_text)


@router.post("/api/ai/extensions/package", response_model=GenerateExtensionResponse)
def package_extension(
    payload: PackageExtensionRequest,
    claims: dict = Depends(require_user),
):
    """Package a ZIP from edited files (no AI call).

    Used by the AI Extension Builder UI for the "edit → rebuild" workflow.
    """

    _require_admin(claims)
    report, zip_b64, files_text = package_extension_zip(payload.spec, payload.files_text)
    return GenerateExtensionResponse(report=report, zip_base64=zip_b64, files_text=files_text)
