from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.schemas.ai_extension_builder import (
    ClarifyExtensionRequest,
    ClarifyExtensionResponse,
    GenerateExtensionRequest,
    GenerateExtensionResponse,
    PackageExtensionRequest,
    PlanExtensionIntentRequest,
    ExtensionIntentPlan,
    ClarifyQuestion,
)
from backend.utils.auth_dep import require_user
from backend.utils.ai_extension_builder.generator import (
    IncompleteAIGenerationError,
    build_extension_zip,
    package_extension_zip,
)
from backend.utils.ai_extension_builder.clarifier import clarify_extension_spec
from backend.utils.db_utils import get_db
from backend.db.settings import Settings
from backend.services.ai_capability_context import build_automation_capability_context
from backend.utils.secure_settings import decrypt_secret, SecureSettingsError
from three_mm_protocol import (
    AutomationCapabilityContextV1,
    BuilderSettingV1,
    CapabilityBindingV1,
    CapabilityPlanV1,
    CapabilityPresentationV1,
    PresentationStateV1,
)


router = APIRouter()


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _plan_extension_intent(payload: PlanExtensionIntentRequest) -> ExtensionIntentPlan:
    """Convert end-user intent into a conservative, provider-independent plan."""

    description = payload.description.casefold()
    dashboard_terms = ("dashboard", "widget", "уиджет", "табло", "начален екран")
    page_terms = ("page", "route", "страница", "меню", "екран")
    record_terms = (
        "crud", "database", "table", "records", "catalog", "list of", "база данни",
        "таблица", "записи", "каталог", "списък с", "създава", "редактира", "изтрива",
    )
    settings_terms = (
        "settings", "configuration", "configure", "option", "choose", "editor",
        "настройки", "конфигурация", "избор", "избира", "редактор",
    )

    questions: list[ClarifyQuestion] = []
    assumptions: list[str] = []
    if payload.placement == "dashboard":
        project_type = "widget"
    elif payload.placement == "page":
        project_type = "extension"
    elif _contains_any(description, dashboard_terms):
        project_type = "widget"
    elif _contains_any(description, page_terms):
        project_type = "extension"
    else:
        project_type = "widget"
        assumptions.append("It will appear as a dashboard widget.")
        questions.append(ClarifyQuestion(
            id="placement",
            question="Where should it appear?",
            suggestions=["On the dashboard", "As a separate page"],
        ))

    if payload.data_mode == "records":
        data_mode = "records"
    elif payload.data_mode in {"none", "settings"}:
        data_mode = payload.data_mode
    elif _contains_any(description, record_terms):
        data_mode = "records"
    elif _contains_any(description, settings_terms):
        data_mode = "settings"
    else:
        data_mode = "none"

    needs_database = data_mode == "records"
    template_key = "crud" if needs_database else "simple"
    package_kind = "compiled" if project_type == "widget" else "legacy"
    location = "a dashboard widget" if project_type == "widget" else "a separate application page"
    storage = (
        "with editable database records"
        if data_mode == "records"
        else "with per-instance settings" if data_mode == "settings" else "without a separate database"
    )
    if data_mode == "settings":
        assumptions.append("Options will be stored in each installed widget or page configuration.")

    # Common UI concepts become typed controls. This is intentionally based on
    # the requested capabilities, never on an extension/module name.
    config_properties: dict[str, dict] = {}
    if _contains_any(description, ("timezone", "time zone", "часова зона")):
        config_properties["timezone"] = {
            "type": "string", "title": "Timezone", "format": "timezone", "default": "UTC",
        }
    if _contains_any(description, ("analog", "digital", "аналогов", "дигитален")):
        config_properties["displayMode"] = {
            "type": "string", "title": "Display", "enum": ["digital", "analog"], "default": "digital",
        }
    if _contains_any(description, ("12/24", "12 hour", "24 hour", "12-часов", "24-часов")):
        config_properties["hourFormat"] = {
            "type": "string", "title": "Hour format", "enum": ["24", "12"], "default": "24",
        }
    config_schema = {"type": "object", "properties": config_properties} if config_properties else {}
    capability_plan = None
    if _contains_any(description, ("gpio", "pin", "пин", "digital input", "цифров вход")):
        capability_plan = CapabilityPlanV1(
            target="dashboard_widget" if project_type == "widget" else "application_page",
            settings=(
                BuilderSettingV1(key="deviceId", label="Device", kind="device", required=True),
                BuilderSettingV1(key="channel", label="Input pin", kind="capability_channel", required=True),
                BuilderSettingV1(key="activeHigh", label="Active high", kind="boolean", default=True),
                BuilderSettingV1(key="activeColor", label="Active color", kind="color", default="#22C55E"),
                BuilderSettingV1(key="inactiveColor", label="Inactive color", kind="color", default="#EF4444"),
            ),
            bindings=(CapabilityBindingV1(
                alias="inputState",
                capability_id="gpio.digital.input",
                operation="subscribe",
                device_setting="deviceId",
                channel_setting="channel",
                permissions=("hardware.gpio",),
            ),),
            presentations=(CapabilityPresentationV1(
                kind="indicator",
                source_binding="inputState",
                states=(
                    PresentationStateV1(value=True, label="Active", color="#22C55E"),
                    PresentationStateV1(value=False, label="Inactive", color="#EF4444"),
                    PresentationStateV1(state="stale", label="Stale", color="#F59E0B"),
                    PresentationStateV1(state="offline", label="Offline", color="#6B7280"),
                    PresentationStateV1(state="error", label="Error", color="#DC2626"),
                ),
            ),),
        )
    return ExtensionIntentPlan(
        project_type=project_type,
        template_key=template_key,
        package_kind=package_kind,
        needs_database=needs_database,
        config_schema=config_schema,
        capability_plan=capability_plan,
        summary=f"Create {location} {storage}.",
        assumptions=assumptions,
        questions=questions,
    )


def _require_admin(claims: dict) -> None:
    role = claims.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/api/ai/extensions/plan", response_model=ExtensionIntentPlan)
def plan_extension_intent(
    payload: PlanExtensionIntentRequest,
    claims: dict = Depends(require_user),
):
    _require_admin(claims)
    return _plan_extension_intent(payload)


@router.get("/api/ai/extensions/capabilities", response_model=AutomationCapabilityContextV1)
def list_extension_builder_capabilities(
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return the trusted device capabilities available to Builder plans."""

    _require_admin(claims)
    return build_automation_capability_context(db)


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

    try:
        report, zip_b64, files_text = build_extension_zip(
            payload.spec,
            instructions=payload.instructions,
            use_ai=payload.use_ai,
            model=payload.model,
            ai_provider=ai_provider,
            groq_api_key=groq_key,
            openrouter_api_key=openrouter_key,
        )
    except IncompleteAIGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
