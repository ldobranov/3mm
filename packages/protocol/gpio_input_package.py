"""Deterministic, inert profile package for the generic digital input handler."""
import io
import json
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from packages.protocol import ModuleManifestV2
from packages.protocol.gpio_input import GpioInputProfileV1, INPUT_CAPABILITY, INPUT_ENTRYPOINT


def manifest(profile):
    return ModuleManifestV2.model_validate({
        'manifest_version': 2, 'module_id': 'org.3mm.gpio-input.' + profile.digest(),
        'name': 'Digital inputs (' + profile.driver + ')', 'version': '1.0.0',
        'description': 'Profile-bound digital input edges. Application packages interpret their meaning.',
        'runtimes': ['agent'], 'entrypoints': {'agent': INPUT_ENTRYPOINT},
        'compatibility': {'protocol': '1.0', 'architectures': ['armv6l', 'aarch64', 'x86_64']},
        'permissions': ['hardware.gpio', 'events.publish'],
        'capabilities': {'provides': [INPUT_CAPABILITY], 'consumes': []},
        'configuration_defaults': profile.model_dump(),
        'health_check': {'type': 'file_exists', 'path': 'health/ready'},
        'registrations': [{'kind': 'capability', 'registration_id': INPUT_CAPABILITY,
            'metadata': {'profile_sha256': profile.digest(), 'simulated': profile.driver == 'mock'},
            'contract': profile.contract().model_dump()}],
    }).model_dump()


def build_package(profile=None):
    profile = profile or GpioInputProfileV1()
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, value in sorted({'manifest.json': (json.dumps(manifest(profile), sort_keys=True, indent=2)+'\n').encode(),
                                  'health/ready': b'inert package; not input readiness\n'}.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system, info.external_attr = 3, 0o100644 << 16
            archive.writestr(info, value)
    return output.getvalue()
