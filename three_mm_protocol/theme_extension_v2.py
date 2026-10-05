"""Closed, non-executable Theme Design API 2 and local asset declarations."""

import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from three_mm_protocol.theme_extension import StrictThemeModel, ThemeExtensionV1
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.runtime_extension import LocalizedTextV1

DESIGN_DEFAULTS = json.loads(Path(__file__).with_name("theme_design_defaults.json").read_text())
MAX_THEME_ASSETS = 16
MAX_THEME_ASSET_BYTES = 4 * 1024 * 1024
MAX_FONT_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 1024 * 1024
MAX_IMAGE_DIMENSION = 2048


def contrast_ratio(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return sum((v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4) * w
                   for v, w in zip(channels, (.2126, .7152, .0722)))
    a, b = luminance(first), luminance(second)
    return (max(a, b) + .05) / (min(a, b) + .05)


def validate_design(value: dict) -> dict:
    if not isinstance(value, dict) or type(value.get("design_api_version")) is not int or value["design_api_version"] != 2:
        raise ValueError("unsupported design API version")
    result = copy.deepcopy(DESIGN_DEFAULTS)
    if value.keys() - result.keys():
        raise ValueError("unknown design fields")
    for group in ("light", "dark", "typography", "scale", "layout", "components"):
        if group not in value:
            continue
        source = value[group]
        if not isinstance(source, dict) or source.keys() - result[group].keys():
            raise ValueError("unknown or invalid design group")
        result[group].update({k: v for k, v in source.items() if v is not None})
    for mode in ("light", "dark"):
        colors = result[mode]
        if any(not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in colors.values()):
            raise ValueError("design colors must be #RRGGBB")
        for surface in ("canvas", "content", "surface", "surface_alt"):
            for foreground in ("text", "text_secondary", "text_muted", "success", "warning", "accent", "danger", "focus"):
                if contrast_ratio(colors[foreground], colors[surface]) < (3 if foreground == "focus" else 4.5):
                    raise ValueError("design contrast is too low")
        for background, foreground in (("accent", "accent_text"), ("secondary", "secondary_text"), ("danger", "danger_text")):
            if contrast_ratio(colors[background], colors[foreground]) < 4.5:
                raise ValueError("button contrast is too low")
    ranges = {
        "typography": {"base_size": (12, 18), "line_height": (1.35, 1.8)},
        "scale": {"unit": (2, 8), "radius_sm": (0, 50), "radius_md": (0, 50), "radius_lg": (0, 50)},
        "layout": {"content_width": (960, 1800), "sidebar_width": (216, 320)},
    }
    for group, fields in ranges.items():
        for key, (low, high) in fields.items():
            token = result[group][key]
            if type(token) not in (int, float) or not math.isfinite(token) or not low <= token <= high or (key != "line_height" and type(token) is not int):
                raise ValueError("design measurement exceeds its limits")
    enums = {"typography": {"font": ("system", "sans", "mono")},
             "layout": {"navigation": ("sidebar", "top"), "density": ("compact", "comfortable")},
             "components": {"button": ("solid", "outline"), "card": ("bordered", "raised")}}
    for group, fields in enums.items():
        if any(result[group][key] not in allowed for key, allowed in fields.items()):
            raise ValueError("unsupported design variant")
    if "header_style" in value:
        if value["header_style"] not in ("saved", "theme"):
            raise ValueError("unsupported header style")
        result["header_style"] = value["header_style"]
    return result


class ThemeAssetV2(StrictThemeModel):
    asset_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$", strict=True)
    path: str = Field(pattern=r"^assets/[a-zA-Z0-9_-]+\.(woff2|png|webp)$", max_length=160, strict=True)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", strict=True)
    media_type: Literal["font/woff2", "image/png", "image/webp"]
    role: Literal["font", "logo_light", "logo_dark"]
    license: str | None = Field(default=None, min_length=1, max_length=512, strict=True)

    @model_validator(mode="after")
    def type_and_role(self):
        extension = {"font/woff2": ".woff2", "image/png": ".png", "image/webp": ".webp"}[self.media_type]
        if not self.path.endswith(extension) or (self.role == "font") != (self.media_type == "font/woff2"):
            raise ValueError("asset role, path and media type must match")
        if self.role == "font" and not (self.license and self.license.strip()):
            raise ValueError("packaged fonts require a license attribution")
        if self.license is not None and not self.license.strip():
            raise ValueError("asset license attribution cannot be blank")
        return self


class ThemeExtensionV2(StrictThemeModel):
    theme_extension_version: Literal[2]
    design_api_version: Literal[2]
    module_id: str = Field(pattern=MODULE_ID_PATTERN, max_length=160, strict=True)
    version: str = Field(pattern=SEMVER_PATTERN, max_length=64, strict=True)
    name: LocalizedTextV1
    base_theme: Literal["builtin.default"] = "builtin.default"
    design: dict[str, Any]
    assets: tuple[ThemeAssetV2, ...] = Field(default=(), max_length=MAX_THEME_ASSETS)

    @field_validator("design", mode="before")
    @classmethod
    def checked_design(cls, value):
        return validate_design(value)

    @model_validator(mode="after")
    def bounded_identity_and_assets(self):
        # Reuse v1's localized identity contract, not its token format.
        ThemeExtensionV1.model_validate({
            "theme_extension_version": 1, "design_api_version": 1,
            "module_id": self.module_id, "version": self.version, "name": self.name,
            "light": {"radius_sm": 0}, "dark": {"radius_sm": 0},
        })
        for key in ("asset_id", "path", "role"):
            values = [getattr(asset, key) for asset in self.assets]
            if len(set(values)) != len(values):
                raise ValueError("theme asset ids, paths and roles must be unique")
        return self
