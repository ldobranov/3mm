"""Data-only profile forms from exact provider packages, never driver imports."""
from dataclasses import dataclass
import hashlib
import io
import json
import zlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED, BadZipFile

from packages.protocol.hardware_templates import (
    TEMPLATE_FILENAME, MAX_TEMPLATE_BYTES, describe_template, instantiate_template, validate_template,
)
from backend.artifacts.packages import MAX_PACKAGE_BYTES, validate_module_package

BUNDLED_TEMPLATES = Path(__file__).with_name('template_data')
TEMPLATE_MARKER = 'profile_template'


def package_bytes(manifest, files):
    """Canonical inert ZIP. Never import or activate a provider."""
    entries = {**files, 'manifest.json': (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode()}
    out = io.BytesIO()
    with ZipFile(out, 'w', compression=ZIP_STORED) as archive:
        for name, value in sorted(entries.items()):
            entry = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system, entry.external_attr = 3, 0o100644 << 16
            archive.writestr(entry, value)
    return out.getvalue()


@dataclass(frozen=True)
class TemplateSource:
    manifest: dict
    descriptor: object
    files: dict
    sha256: str

    @property
    def identity(self):
        return 'tpl-' + self.sha256

    def describe(self):
        return {**describe_template(self.manifest, self.descriptor), 'template_id': self.identity}

    def prepare(self, configuration):
        values = {field.key: field.default for field in self.descriptor.fields}
        values.update(configuration)
        manifest = instantiate_template(self.manifest, self.descriptor, values)
        # A template ZIP and its default configured instance have different
        # bytes. They cannot occupy the same immutable module/version tuple.
        prefix, digest = manifest['module_id'].rsplit('.', 1)
        manifest['module_id'] = prefix + '.instance.' + digest
        for registration in manifest['registrations']:
            registration.get('metadata', {}).pop(TEMPLATE_MARKER, None)
        blob = package_bytes(manifest, self.files)
        validate_module_package(blob)
        return blob


def template_source(blob, *, expected_sha256=None):
    try:
        return _read_template_source(blob, expected_sha256=expected_sha256)
    except (BadZipFile, zlib.error, RuntimeError, NotImplementedError) as error:
        raise ValueError('Hardware template ZIP cannot be read') from error


def _read_template_source(blob, *, expected_sha256=None):
    if expected_sha256 is not None and hashlib.sha256(blob).hexdigest() != expected_sha256:
        raise ValueError('Hardware template package changed')
    validated = validate_module_package(blob)
    with ZipFile(io.BytesIO(blob)) as archive:
        health = validated.manifest.health_check
        if (health.type != 'file_exists' or set(archive.namelist()) != {'manifest.json', TEMPLATE_FILENAME, health.path}
                or archive.getinfo(TEMPLATE_FILENAME).file_size > MAX_TEMPLATE_BYTES
                or archive.getinfo(health.path).file_size > 4096):
            raise ValueError('Hardware template must contain only manifest, descriptor and health marker')
        descriptor = validate_template(validated.manifest, json.loads(archive.read(TEMPLATE_FILENAME)))
        return TemplateSource(validated.manifest.model_dump(mode='json'), descriptor,
                              {health.path: archive.read(health.path)}, validated.sha256)


def sources(packages=()):
    """Built-in starter data plus uploaded sources. No catalog writes on read."""
    result = {}
    for path in sorted(BUNDLED_TEMPLATES.glob('*.json'))[:33]:
        if len(result) >= 32 or path.is_symlink() or path.stat().st_size > 192 * 1024:
            raise ValueError('Bundled hardware template catalog exceeds limits')
        data = json.loads(path.read_text(encoding='utf-8'))
        if set(data) != {'manifest', 'template', 'health'} or type(data['health']) is not str:
            raise ValueError('Invalid bundled hardware template data')
        health = data['manifest']['health_check']['path']
        source = template_source(package_bytes(data['manifest'], {
            health: data['health'].encode(),
            TEMPLATE_FILENAME: (json.dumps(data['template'], sort_keys=True, indent=2)+'\n').encode()}))
        result[source.identity] = source
    for package in packages:
        if not any(item.get('metadata', {}).get(TEMPLATE_MARKER) is True
                   for item in package.manifest.get('registrations', [])):
            continue
        path = Path(package.file_path)
        try:
            if path.is_symlink() or path.stat().st_size > MAX_PACKAGE_BYTES:
                continue
            source = template_source(path.read_bytes(), expected_sha256=package.sha256)
        except (OSError, ValueError, KeyError):
            continue  # Broken source stays visible in the ordinary package catalog.
        if source.identity not in result and len(result) >= 32:
            continue
        result[source.identity] = source
    return result


def provider_templates(features=(), *, packages=()):
    return [source.describe() for source in sources(packages).values()
            if set(source.descriptor.required_features) <= set(features)]


def prepare_provider(template_id, configuration, *, features=(), packages=()):
    source = sources(packages).get(template_id)
    if source is None:
        raise ValueError('Hardware template package changed or is unavailable; refresh the catalog')
    if not set(source.descriptor.required_features) <= set(features):
        raise ValueError('Update Agent before preparing this hardware provider')
    return source.prepare(configuration)
