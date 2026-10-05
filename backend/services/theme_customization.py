"""Bounded installation preferences; immutable theme packages remain untouched."""

import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.module import ModulePackage, ThemeExtensionInstallation
from backend.db.settings import Settings
from backend.db.user import User
from three_mm_protocol.theme_extension import ThemeColor
from three_mm_protocol.theme_extension_v2 import contrast_ratio, validate_design


UiColorKey = Literal[
    "canvas", "content", "surface", "surface_alt", "text", "text_secondary", "text_muted",
    "border", "accent", "accent_text", "secondary", "secondary_text", "danger", "danger_text",
    "success", "warning", "focus",
]
LEGACY_COLOR_KEYS = frozenset((
    "canvas", "content", "surface", "surface_alt", "text", "text_secondary", "text_muted",
    "border", "accent", "secondary", "danger",
))


class ThemeColorOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    light: dict[UiColorKey, ThemeColor] | None = None
    dark: dict[UiColorKey, ThemeColor] | None = None

    @model_validator(mode="after")
    def nonempty_palette(self):
        if not self.light and not self.dark:
            raise ValueError("Color overrides must contain at least one color")
        return self


class ThemePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    navigation: Literal["sidebar", "top"]
    density: Literal["compact", "comfortable"]
    button: Literal["solid", "outline"]
    card: Literal["bordered", "raised"]
    header_style: Literal["saved", "theme"]
    header_background_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    header_text_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    colors: ThemeColorOverrides | None = None

    @model_validator(mode="after")
    def readable_header(self):
        if self.header_style == "saved" and contrast_ratio(
            self.header_background_color, self.header_text_color
        ) < 4.5:
            raise ValueError("Header text contrast must be at least 4.5:1")
        return self


class ThemeCustomizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sha256: str | None = Field(..., pattern=r"^[0-9a-f]{64}$")
    preferences: ThemePreferences | None


def customization_key(sha256: str | None) -> str:
    return f"ui_theme_customization:{sha256 or 'builtin'}"


def validate_color_overrides(preferences: ThemePreferences, theme=None) -> None:
    if preferences.colors is None:
        return
    if theme is None:
        raise ValueError("Use the existing built-in color settings for the built-in theme")
    colors = preferences.colors.model_dump(exclude_none=True)
    if theme.theme_extension_version == 1:
        if any(palette.keys() - LEGACY_COLOR_KEYS for palette in colors.values()):
            raise ValueError("This color is not supported by Theme Design API 1")
        # Preserve v1's existing color contract; do not impose v2 on legacy ZIPs.
        return
    design = {**theme.design, **{
        mode: {**theme.design[mode], **palette} for mode, palette in colors.items()
    }}
    validate_design(design)  # Same bounded palette and contrast policy as v2 packages.


def read_customization(db: Session, sha256: str | None, theme=None) -> dict | None:
    row = db.scalar(select(Settings).where(
        Settings.key == customization_key(sha256),
        Settings.user_id.is_(None), Settings.language_code.is_(None),
    ).order_by(Settings.id.desc()))
    if row is None or not row.value or len(row.value) > 2048:
        return None
    try:
        preferences = ThemePreferences.model_validate_json(row.value)
        validate_color_overrides(preferences, theme)
        return preferences.model_dump(exclude_none=True)
    except (ValueError, ValidationError):
        # Corrupt restored/legacy settings must never prevent login or recovery.
        return None


def save_customization(db: Session, request: ThemeCustomizationRequest, actor: User) -> None:
    selected = db.scalar(select(ModulePackage).join(ThemeExtensionInstallation).where(
        ThemeExtensionInstallation.is_selected.is_(True),
        ThemeExtensionInstallation.enabled.is_(True),
    ))
    if (selected.sha256 if selected else None) != request.sha256:
        raise HTTPException(409, "Theme selection changed; refresh before saving")
    if request.preferences is not None and request.preferences.colors is not None:
        from backend.services.theme_extensions import validate_stored_theme

        theme = validate_stored_theme(selected).theme_extension if selected else None
        try:
            validate_color_overrides(request.preferences, theme)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    rows = list(db.scalars(select(Settings).where(
        Settings.key == customization_key(request.sha256),
        Settings.user_id.is_(None), Settings.language_code.is_(None),
    )))
    # The existing settings table has no unique key. Reconcile old duplicates.
    for row in rows:
        db.delete(row)
    if request.preferences is not None:
        db.add(Settings(
            key=customization_key(request.sha256),
            value=json.dumps(request.preferences.model_dump(exclude_none=True), separators=(",", ":")),
            description="Theme appearance preferences", user_id=None, language_code=None,
        ))
    db.add(AuditLog(
        user_id=actor.id, action="UPDATE", entity_type="theme_customization",
        entity_name=request.sha256 or "builtin.default",
        changes={"sha256": request.sha256, "reset": request.preferences is None},
    ))
    db.commit()
