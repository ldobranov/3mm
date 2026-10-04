"""Declarative, non-executable theme-extension v1 contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.runtime_extension import LocalizedTextV1


ThemeColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$", strict=True)]
ThemeRadius = Annotated[int, Field(ge=0, le=50, strict=True)]


class StrictThemeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ThemeTokensV1(StrictThemeModel):
    """An allowlisted override of the existing light/dark design tokens.

    Missing values inherit the built-in theme. No CSS expressions, selectors,
    URLs, HTML, script or Core component imports are accepted.
    """

    body_bg: ThemeColor | None = None
    content_bg: ThemeColor | None = None
    card_bg: ThemeColor | None = None
    panel_bg: ThemeColor | None = None
    button_primary_bg: ThemeColor | None = None
    button_secondary_bg: ThemeColor | None = None
    button_danger_bg: ThemeColor | None = None
    card_border: ThemeColor | None = None
    text_primary: ThemeColor | None = None
    text_secondary: ThemeColor | None = None
    text_muted: ThemeColor | None = None
    radius_sm: ThemeRadius | None = None
    radius_md: ThemeRadius | None = None
    radius_lg: ThemeRadius | None = None

    @model_validator(mode="after")
    def has_overrides(self):
        if not any(getattr(self, key) is not None for key in type(self).model_fields):
            raise ValueError("a theme mode must override at least one design token")
        return self


class ThemeExtensionV1(StrictThemeModel):
    theme_extension_version: Literal[1]
    design_api_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160)
    version: str = Field(pattern=SEMVER_PATTERN, max_length=64)
    name: LocalizedTextV1
    base_theme: Literal["builtin.default"] = "builtin.default"
    light: ThemeTokensV1
    dark: ThemeTokensV1

    @model_validator(mode="after")
    def bounded_translations(self):
        if len(self.name.translations) > 32:
            raise ValueError("theme names support at most 32 translations")
        for locale, value in self.name.translations.items():
            if not 1 <= len(locale) <= 24 or not 1 <= len(value) <= 160:
                raise ValueError("theme name translations exceed their limits")
        return self
