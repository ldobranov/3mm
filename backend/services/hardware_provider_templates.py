"""Allowlisted, inert profile preparation for drivers already shipped with Agent.

Templates are presentation/configuration data, not uploaded scripts or raw bus
commands. Adding a supported driver does not require an application-specific API.
Installation and exact-profile consent remain in the normal module lifecycle.
"""
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from three_mm_protocol.character_display import CharacterDisplayProfileV1
from three_mm_protocol.character_display_package import build_package


class DisplaySettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    display_id: str = Field(default='display.main', pattern=r'^[a-z][a-z0-9_.-]{0,63}$')
    bus: int = Field(default=1, ge=0, le=255)
    address: int = Field(default=0x27, ge=0x08, le=0x77)
    columns: int = Field(default=16, ge=1, le=80)
    rows: int = Field(default=2, ge=1, le=4)
    backlight_active_high: bool = True


@dataclass(frozen=True)
class DisplayTemplate:
    template_id: str
    name: str
    driver: str

    def describe(self) -> dict:
        native = self.driver == 'pcf8574'
        return {'template_id': self.template_id, 'name': self.name, 'simulated': not native,
            'fields': [
                {'key': 'display_id', 'label': 'Display ID', 'type': 'text', 'default': 'display.main',
                 'pattern': r'^[a-z][a-z0-9_.-]{0,63}$', 'maxlength': 64},
                {'key': 'columns', 'label': 'Columns', 'type': 'number', 'default': 16, 'min': 1,
                 'max': 40 if native else 80},
                {'key': 'rows', 'label': 'Rows', 'type': 'select', 'default': 2,
                 'options': [{'value': str(n), 'label': str(n)} for n in ((2, 4) if native else (1, 2, 3, 4))]},
                {'key': 'bus', 'label': 'I²C bus', 'type': 'number', 'default': 1, 'min': 0, 'max': 255},
                {'key': 'address', 'label': 'I²C address', 'type': 'select', 'default': 0x27,
                 'options': [{'value': str(n), 'label': f'0x{n:02X}'} for n in range(0x20, 0x28)]},
                {'key': 'backlight_active_high', 'label': 'Backlight active high', 'type': 'checkbox', 'default': True},
            ]}

    def build(self, configuration: dict) -> bytes:
        settings = DisplaySettings.model_validate(configuration)
        return build_package(CharacterDisplayProfileV1(driver=self.driver, **settings.model_dump()))


# Only installed trusted drivers. No caller-supplied module ID, code, entrypoint,
# manifest, permission, filesystem path or command is accepted by preparation.
_TEMPLATES = {item.template_id: item for item in (
    DisplayTemplate('character-display.pcf8574', 'HD44780 / PCF8574T', 'pcf8574'),
    DisplayTemplate('character-display.mock', 'Character display (simulation)', 'mock'),
)}


def provider_templates() -> list[dict]:
    return [item.describe() for item in _TEMPLATES.values()]


def prepare_provider(template_id: str, configuration: dict) -> bytes:
    template = _TEMPLATES.get(template_id)
    if template is None:
        raise ValueError('Unsupported hardware provider template')
    return template.build(configuration)
