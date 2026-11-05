"""Compare two exact application archives without running either application."""
from pathlib import Path
import json
import zipfile
import zlib

from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from backend.version import core_version
from three_mm_protocol.diagnostic_snapshot import read_regular


class PackageReviewError(ValueError):
    """An input refusal with a safe, fixed message for the developer CLI."""


_NAMED = {
    'permissions': 'permission_id', 'operations': 'operation_id',
    'routes': 'route_id', 'public_http_routes': 'route_id',
    'command_bindings': 'binding_id', 'session_bindings': 'binding_id',
    'connectors': 'connector_id', 'event_subscriptions': 'subscription_id',
    'query_exports': 'export_id', 'query_dependencies': 'binding_id',
    'peer_bindings': 'binding_id', 'checkpoints': 'checkpoint_id',
    'platform_requirements': 'requirement_id', 'tasks': 'task_id',
    'entrypoints': 'entrypoint_id', 'publications': 'publication_id',
}


def _load(path, version, label):
    try:
        blob = read_regular(Path(path), MAX_PACKAGE_BYTES)
        package = validate_module_package(blob, core_version=version)
    except (OSError, ValueError, zipfile.BadZipFile, zlib.error, RuntimeError, KeyError) as error:
        raise PackageReviewError(f"{label} ZIP is unreadable or fails this checkout's package validation.") from error
    if package.application_extension is None:
        raise PackageReviewError(f'{label} ZIP must be an application package.')
    return package


def _fields(before, after):
    # JSON distinguishes e.g. true from 1, unlike Python equality.
    def canonical(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    return sorted((before.keys() ^ after.keys()) | {
        key for key in before.keys() & after.keys() if canonical(before[key]) != canonical(after[key])
    })


def _documents(package):
    def dump(model):
        return model.model_dump(mode='json') if model is not None else {}

    manifest = dump(package.manifest)
    application = dump(package.application_extension)
    ui = dump(package.compiled_ui)
    publications = dump(package.application_publications)
    for document in (manifest, application, ui, publications):
        document.pop('version', None)
        document.pop('module_id', None)
    application['service'].pop('artifact')
    application['service'].pop('artifact_sha256')
    publications.pop('service_artifact_sha256', None)
    return {'manifest': manifest, 'application': application, 'compiled_ui': ui, 'event_publications': publications}


def _identity(package):
    application = package.application_extension
    return {'version': package.manifest.version, 'sha256': package.sha256,
            'bytes': package.size_bytes, 'service_sha256': application.service.artifact_sha256,
            'schema_revision': application.storage.schema_revision}


def _named_changes(before, after, key):
    old = {item[key]: item for item in before}
    new = {item[key]: item for item in after}
    if len(old) != len(before) or len(new) != len(after):
        return None  # The enclosing field still reports a change; don't collapse ambiguous entries.
    changed = {identity: fields for identity in sorted(old.keys() & new.keys())
               if (fields := _fields(old[identity], new[identity]))}
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': changed}


def compare_application_packages(previous: Path, candidate: Path) -> dict:
    """Report declaration differences, not installability or a compatibility verdict."""
    try:
        version = core_version()
    except ValueError as error:
        raise PackageReviewError("This checkout's Core compatibility version is unavailable.") from error
    old = _load(previous, version, 'Previous')
    new = _load(candidate, version, 'Candidate')
    if old.manifest.module_id != new.manifest.module_id:
        raise PackageReviewError('Select two ZIPs for the same application identity.')
    if old.manifest.version == new.manifest.version and old.sha256 != new.sha256:
        raise PackageReviewError('Different ZIP bytes reuse the same application version. Choose a distinct candidate version.')

    before, after = _documents(old), _documents(new)
    changes = {}
    try:
        for name, document in before.items():
            fields = _fields(document, after[name])
            if not fields:
                continue
            details = {}
            for field in fields:
                left, right = document.get(field, []), after[name].get(field, [])
                if not isinstance(left, list) or not isinstance(right, list):
                    continue
                string_items = (field in {'permissions', 'platform_permissions', 'optional_resources'}
                                and all(isinstance(item, str) for item in left + right))
                if string_items:
                    details[field] = {'added': sorted(set(right) - set(left)), 'removed': sorted(set(left) - set(right))}
                elif field in _NAMED:
                    delta = _named_changes(left, right, _NAMED[field])
                    if delta is not None:
                        details[field] = delta
            changes[name] = {'fields': fields, 'items': details}
    except (ValueError, RecursionError) as error:
        raise PackageReviewError('Package declarations cannot be compared as bounded JSON.') from error
    return {'comparison_version': 1, 'status': 'compared', 'module_id': old.manifest.module_id,
            'validation_core_version': version, 'previous': _identity(old), 'candidate': _identity(new),
            'same_archive': old.sha256 == new.sha256,
            'service_artifact_changed': old.application_extension.service.artifact_sha256 != new.application_extension.service.artifact_sha256,
            'changes': changes, 'installation': 'not_requested', 'executed_checks': 'not_run'}
