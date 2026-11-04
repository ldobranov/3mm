"""Inert packages for the installed character-display drivers.

Shared by the administrative template and the source CLI. No Agent/Core import,
device access, code generation or dependency installation is needed to prepare one.
The Agent independently validates the profile before activation and execution.
"""
import io
import json
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from three_mm_protocol import ModuleManifestV2
from three_mm_protocol.character_display import (
    CharacterDisplayProfileV1, DISPLAY_CAPABILITY, DISPLAY_ENTRYPOINT,
)


def validate_builtin_profile(profile: CharacterDisplayProfileV1) -> None:
    if profile.driver == 'mock':
        return
    if profile.driver != 'pcf8574':
        raise ValueError('This builder supports the installed mock/PCF8574 drivers')
    # Pure preflight for the native driver's single-controller DDRAM topology.
    if (profile.rows not in (2, 4)
            or profile.columns > (40 if profile.rows == 2 else 20)):
        raise ValueError('Unsupported single-controller HD44780 geometry')
    if (profile.controller != 'hd44780' or profile.pin_map != 'rs0_rw1_e2_bl3_d4_7'
            or not 0x20 <= profile.address <= 0x27):
        raise ValueError('Unsupported PCF8574T hardware profile')


def manifest(profile: CharacterDisplayProfileV1) -> dict:
    value = {
        'manifest_version': 2, 'module_id': 'org.3mm.character-display.' + profile.digest(),
        'name': 'Character display (' + profile.driver + ')', 'version': '1.0.0',
        'description': f'{profile.columns}x{profile.rows} character display with an exact, opt-in hardware profile.',
        'runtimes': ['agent'], 'entrypoints': {'agent': DISPLAY_ENTRYPOINT},
        'compatibility': {'protocol': '1.0', 'architectures': ['armv6l', 'aarch64', 'x86_64']},
        'permissions': ['hardware.display'],
        'capabilities': {'provides': [DISPLAY_CAPABILITY], 'consumes': []},
        'configuration_defaults': profile.model_dump(),
        'health_check': {'type': 'file_exists', 'path': 'health/ready'},
        'registrations': [{'kind': 'capability', 'registration_id': DISPLAY_CAPABILITY,
            'metadata': {'driver': profile.driver, 'simulated': profile.driver == 'mock',
                'controller': profile.controller, 'pin_map': profile.pin_map,
                'backlight_active_high': profile.backlight_active_high,
                'bus': profile.bus, 'address': profile.address,
                'columns': profile.columns, 'rows': profile.rows,
                'profile_sha256': profile.digest()},
            'contract': profile.contract().model_dump()}],
    }
    return ModuleManifestV2.model_validate(value).model_dump(exclude_defaults=False)


def build_package(profile: CharacterDisplayProfileV1 | None = None) -> bytes:
    profile = profile or CharacterDisplayProfileV1()
    validate_builtin_profile(profile)
    output = io.BytesIO()
    payloads = {'manifest.json': (json.dumps(manifest(profile), sort_keys=True, indent=2) + '\n').encode(),
                'health/ready': b'provider package; not a hardware health proof\n'}
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()
