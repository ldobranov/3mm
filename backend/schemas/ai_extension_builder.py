from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


class LocaleConfig(BaseModel):
    supported: List[str] = Field(default_factory=lambda: ["en", "bg"])
    default: str = "en"
    directory: str = "locales/"


class FrontendRouteConfig(BaseModel):
    path: str
    component: str
    name: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    props: Optional[bool] = None


class ContentEmbedderConfig(BaseModel):
    label: str
    component: str
    format_api: Optional[str] = None
    ui_translations_api: Optional[str] = None
    description: Optional[str] = None


class ProvidesConfig(BaseModel):
    # Mirrors the manifest structure described in EXTENSION_DEVELOPMENT_GUIDE.md
    content_embedders: Optional[Dict[str, ContentEmbedderConfig]] = None


class ConsumesConfig(BaseModel):
    # Minimal v1: declare what we want to consume; generator can add glue code stubs.
    content_embedders: Optional[Dict[str, List[str]]] = None


class ExtensionSpec(BaseModel):
    name: str
    version: str
    type: Literal["extension", "widget"] = "extension"
    description: str = "AI generated extension"
    author: str = "AI"

    # Routing
    api_prefix: str = Field(
        description="Backend API prefix (e.g. /api/store). Should be stable across versions."
    )
    frontend_routes: List[FrontendRouteConfig] = Field(default_factory=list)

    # Files
    backend_entry: str
    frontend_entry: str
    frontend_components: List[str] = Field(default_factory=list)

    # i18n
    locales: LocaleConfig = Field(default_factory=LocaleConfig)

    # Relationships
    provides: Optional[ProvidesConfig] = None
    consumes: Optional[ConsumesConfig] = None

    # Permissions
    permissions: List[str] = Field(default_factory=list)
    public_endpoints: List[str] = Field(default_factory=list)
    dependencies: Dict[str, Any] = Field(default_factory=dict)

    # Free-form description to guide the AI
    goal: Optional[str] = None


class GenerateExtensionRequest(BaseModel):
    spec: ExtensionSpec
    # Optional: allow the UI to provide extra instructions.
    instructions: Optional[str] = None
    use_ai: bool = True
    # Optional model override (OpenRouter model id), for testing.
    model: Optional[str] = None
    # Optional: override which AI provider to use for this generation.
    # When omitted or set to "auto", the backend will use Application Settings or auto-detect.
    ai_provider: Optional[Literal["auto", "groq", "openrouter"]] = None


class BuildWarning(BaseModel):
    code: str
    message: str


class BuildReport(BaseModel):
    extension_id: str
    files: List[str]
    warnings: List[BuildWarning] = Field(default_factory=list)


class GenerateExtensionResponse(BaseModel):
    report: BuildReport
    zip_base64: str
    # Optional: expose generated text files for in-app editing.
    files_text: Dict[str, str] | None = None


class PackageExtensionRequest(BaseModel):
    spec: ExtensionSpec
    # Full set of files to package (text only). The backend will encode and zip them.
    files_text: Dict[str, str]


class ClarifyQuestion(BaseModel):
    id: str
    question: str
    suggestions: List[str] = Field(default_factory=list)


class ClarifyExtensionRequest(BaseModel):
    draft_spec: ExtensionSpec
    goal: str
    # Optional provider/model overrides
    ai_provider: Optional[Literal["auto", "groq", "openrouter"]] = None
    model: Optional[str] = None


class ClarifyExtensionResponse(BaseModel):
    suggested_spec: ExtensionSpec
    questions: List[ClarifyQuestion] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
