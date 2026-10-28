# --- AI Provider Settings (admin-only) ---

class AiSettingsResponse(BaseModel):
    provider: str | None = None
    has_groq_key: bool = False
    has_openrouter_key: bool = False


class AiSettingsUpdateRequest(BaseModel):
    provider: str | None = None  # 'groq' | 'openrouter' | ''
    groq_api_key: str | None = None
    openrouter_api_key: str | None = None


@router.get(
    "/api/admin/ai-settings/debug",
    dependencies=[Depends(admin_required)],
)
def debug_ai_settings_env():
    """Debug endpoint to verify encryption prerequisites on the running backend.

    Returns only metadata (never returns the key itself).
    """

    import os

    master_key = os.getenv("AI_SETTINGS_MASTER_KEY")
    crypto_ok = True
    crypto_error = None
    try:
        import cryptography  # noqa: F401
    except Exception as e:
        crypto_ok = False
        crypto_error = str(e)

    return {
        "has_master_key": bool(master_key),
        "master_key_length": len(master_key) if master_key else 0,
        "crypto_available": crypto_ok,
        "crypto_error": crypto_error,
    }


@router.get("/api/admin/ai-settings", response_model=AiSettingsResponse, dependencies=[Depends(admin_required)])
def get_ai_settings(db: Session = Depends(get_db)):
    """Return AI provider configuration status.

    Does NOT return raw keys.
    """

    def get_value(key: str) -> str | None:
        row = (
            db.query(Settings)
            .filter(Settings.key == key, Settings.language_code.is_(None), Settings.user_id.is_(None))
            .first()
        )
        return row.value if row else None

    provider = (get_value("ai_provider") or "").strip().lower() or None
    has_groq_key = bool(get_value("ai_groq_api_key"))
    has_openrouter_key = bool(get_value("ai_openrouter_api_key"))
    return AiSettingsResponse(
        provider=provider,
        has_groq_key=has_groq_key,
        has_openrouter_key=has_openrouter_key,
    )


@router.post("/api/admin/ai-settings", response_model=AiSettingsResponse, dependencies=[Depends(admin_required)])
def update_ai_settings(payload: AiSettingsUpdateRequest, db: Session = Depends(get_db)):
    """Upsert AI provider settings.

    Keys are encrypted using Fernet + `AI_SETTINGS_MASTER_KEY`.
    """

    def upsert(key: str, value: str | None, description: str):
        row = (
            db.query(Settings)
            .filter(Settings.key == key, Settings.language_code.is_(None), Settings.user_id.is_(None))
            .first()
        )
        if row:
            row.value = value
            row.description = description
            return
        db.add(
            Settings(
                key=key,
                value=value,
                description=description,
                language_code=None,
                user_id=None,
            )
        )

    # Normalize provider
    provider = (payload.provider or "").strip().lower()
    if provider not in {"", "groq", "openrouter"}:
        raise HTTPException(status_code=400, detail="provider must be 'groq', 'openrouter', or empty")

    upsert("ai_provider", provider or None, "AI provider for extension generation")

    # Only update key fields when provided (allow partial updates)
    try:
        if payload.groq_api_key is not None:
            encrypted = encrypt_secret(payload.groq_api_key) if payload.groq_api_key else None
            upsert("ai_groq_api_key", encrypted, "Encrypted Groq API key")

        if payload.openrouter_api_key is not None:
            encrypted = encrypt_secret(payload.openrouter_api_key) if payload.openrouter_api_key else None
            upsert("ai_openrouter_api_key", encrypted, "Encrypted OpenRouter API key")
    except SecureSettingsError as e:
        # Make this actionable for the UI.
        raise HTTPException(
            status_code=500,
            detail=f"AI settings encryption is not configured: {str(e)}",
        )

    db.commit()

    # Return status (not raw keys)
    return get_ai_settings(db)

