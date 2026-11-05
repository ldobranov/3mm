"""Source-derived application authoring catalog, never installed authority.

Only public models/SDK sources and developer tooling are loaded. Application
packages, migration callbacks and tests are inspected as bytes, never imported.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
import re
import tempfile
from typing import get_args

from pydantic import BaseModel
from tools import application_migrations, application_project
from tools.application_project import ProjectCheckError, REPOSITORY

SCOPE = 'local pure-Python SQLite application authoring; not runtime support, readiness or authority'
_UI_SOURCE = 'frontend/src/extension-ui/application-v1.ts'
_SDK_SOURCE = 'three_mm_application_sdk/__init__.py'


def _read_source(relative):
    path = REPOSITORY / relative
    if path.is_symlink() or not path.is_file() or REPOSITORY not in path.resolve().parents:
        raise ProjectCheckError('catalog', 'An authoritative catalog source is unavailable.')
    return path.read_bytes()


def _ui_contract(data):
    source = data.decode('utf-8-sig')
    version = re.search(r'^export const APPLICATION_HOST_VERSION\s*=\s*([1-9][0-9]*) as const\s*$', source, re.MULTILINE)
    union = re.search(r'^export type ApplicationHostErrorCode\s*=\s*(.*?)\n(?=export )', source, re.MULTILINE | re.DOTALL)
    invocation = re.search(r'/\*\*\s*([^*]+?)\s*\*/\s*invoke\(operationId:\s*string', source)
    body = union.group(1).strip().removesuffix(';').strip() if union else ''
    if (not version or not invocation or len(body) > 4096
            or not re.fullmatch(r"'[a-z_]+'(?:\s*\|\s*'[a-z_]+')*", body)):
        raise ProjectCheckError('catalog', 'The public UI host contract format changed; update the catalog reader.')
    codes = re.findall(r"'([a-z_]+)'", body)
    if len(set(codes)) != len(codes):
        raise ProjectCheckError('catalog', 'The public UI error union contains duplicate codes.')
    return {'version': int(version.group(1)), 'error_codes': sorted(codes),
            'invoke_semantics': ' '.join(invocation.group(1).split()), 'source': _UI_SOURCE}


def _sdk_errors(data):
    tree = ast.parse(data)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    try:
        error = next(node for node in classes['ApplicationPlatformError'].body
                     if isinstance(node, ast.FunctionDef) and node.name == '__init__')
        exchange = next(node for node in classes['ApplicationPlatformClient'].body
                        if isinstance(node, ast.FunctionDef) and node.name == '_exchange')
        defaults = {argument.arg: default for argument, default in zip(error.args.kwonlyargs, error.args.kw_defaults)}
        phase = defaults['phase']
        retry = next(node.value for node in ast.walk(error) if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id == 'self' and target.attr == 'retryable' for target in node.targets))
        if not isinstance(phase, ast.Constant) or not isinstance(phase.value, str) or not isinstance(retry, ast.Constant) or retry.value is not False:
            raise ValueError('Public error contract changed')
    except (KeyError, StopIteration, ValueError) as failure:
        raise ProjectCheckError('catalog', 'The public SDK error contract format changed; update the catalog reader.') from failure
    phases = {phase.value}
    reasons = set()
    for node in ast.walk(exchange):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if any(isinstance(target, ast.Name) and target.id == 'phase' for target in node.targets):
                phases.add(node.value.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'ApplicationPlatformError':
            for keyword in node.keywords:
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    if keyword.arg == 'reason': reasons.add(keyword.value.value)
                    if keyword.arg == 'phase': phases.add(keyword.value.value)
    return {'phase_literals': sorted(phases), 'local_transport_reasons': sorted(reasons),
            'automatic_retry': retry.value, 'source': _SDK_SOURCE,
            'semantics': 'phase and reason are reported separately; no inferred retry permission'}


def _model_sources(model, capture, visited):
    if model in visited:
        return []
    visited.add(model)
    path = Path(inspect.getsourcefile(model)).resolve()
    if REPOSITORY not in path.parents:
        return []
    relative = path.relative_to(REPOSITORY).as_posix()
    tree = ast.parse(capture(relative))
    declaration = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == model.__name__)
    validators = []
    for node in declaration.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
            and decorator.func.id in {'field_validator', 'model_validator'} for decorator in node.decorator_list):
            validators.append(f'{model.__module__}.{model.__name__}.{node.name}')
    def descend(annotation):
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            validators.extend(_model_sources(annotation, capture, visited))
        for argument in get_args(annotation):
            descend(argument)
    for field in model.model_fields.values():
        descend(field.annotation)
    for base in model.__bases__:
        if inspect.isclass(base) and issubclass(base, BaseModel):
            validators.extend(_model_sources(base, capture, visited))
    return validators


def _project_catalog(project, source_core_version):
    from backend.services.module_packages import validate_module_package
    from backend.version import core_version

    actual_core_version = core_version()
    if source_core_version != actual_core_version:
        raise ProjectCheckError('catalog', 'Core compatibility sources changed during catalog inspection; read a fresh snapshot.')
    project = Path(project).absolute()
    if project.is_symlink() or not project.is_dir():
        raise ProjectCheckError('catalog', 'Select a regular application source directory.')
    source = application_project.inputs(project)
    source_hash = application_project.fingerprint(source)
    with tempfile.TemporaryDirectory(prefix='3mm-application-catalog-') as temporary:
        snapshot = Path(temporary)
        for relative, data in source.items():
            path = snapshot / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        blob = application_project.build_package(snapshot)
        validated = validate_module_package(blob, core_version=actual_core_version)
        definition = validated.application_extension
        if definition is None:
            raise ProjectCheckError('catalog', 'This catalog requires an application-extension package, not another module type.')
        result = {'source_sha256': source_hash, 'package_sha256': validated.sha256,
            'package_bytes': len(blob),
            'semantic_validation': {'status': 'passed', 'validator': 'backend.services.module_packages.validate_module_package',
                'core_version': actual_core_version,
                'scope': 'package/model/cross-document rules only; no tests, migration execution or installed authority'},
            'review': application_project.declaration_review(validated),
            'application_declarations': definition.model_dump(mode='json', exclude_none=True),
            'lifecycle': definition.lifecycle.model_dump(mode='json'),
            'authoring_check_support': {'profile': 'pure_python_sqlite', 'check': 'not_run',
                'migration_probe': 'unsupported' if definition.storage.relational is not None else 'not_run',
                'reason': 'scoped_relational' if definition.storage.relational is not None else None}}
        if (application_project.fingerprint(application_project.inputs(project)) != source_hash
                or application_project.fingerprint(application_project.inputs(snapshot)) != source_hash):
            raise ProjectCheckError('catalog', 'Project source changed during catalog inspection; read a fresh snapshot.')
        return result


def application_catalog(project: Path | None = None) -> dict:
    """Describe current public declarations and local authoring boundaries only."""
    from three_mm_application_sdk import SDK_VERSION
    import three_mm_platform_wire as wire
    from three_mm_protocol.extension_schemas import extension_schema_catalog
    from three_mm_protocol.module_manifest import ModuleManifestV2
    from three_mm_protocol.compiled_extension import CompiledUiExtensionV1
    from three_mm_protocol.application_extension import ApplicationExtensionV1, ApplicationOperationV1, ApplicationLifecycleV1
    from three_mm_protocol.application_resources import ResourceObservationV1, ResourceDiscoveryV1

    frozen = {}
    def capture(relative):
        if relative not in frozen: frozen[relative] = _read_source(relative)
        return frozen[relative]
    try:
        for relative in ('tools/application_catalog.py', 'tools/application_project.py',
                'tools/application_migrations.py', 'tools/application_client.py', 'tools/application_upgrade.py',
                'three_mm_protocol/extension_schemas.py',
                'three_mm_platform_wire/__init__.py', _SDK_SOURCE, _UI_SOURCE,
                'backend/services/module_packages.py', 'backend/version.py', 'VERSION'):
            capture(relative)
        catalog = extension_schema_catalog()['contracts']
        names = ('module-manifest.v2', 'application-extension.v1', 'compiled-ui.v1')
        contracts = {name: {key: catalog[name][key] for key in
            ('document', 'version_field', 'contract_version', 'source_model', 'schema')} for name in names}
        selected = (ModuleManifestV2, ApplicationExtensionV1, CompiledUiExtensionV1,
                    ApplicationOperationV1, ApplicationLifecycleV1, ResourceObservationV1, ResourceDiscoveryV1)
        validators, visited = [], set()
        for model in selected: validators.extend(_model_sources(model, capture, visited))
        result = {'catalog_version': 1, 'scope': SCOPE,
            'profile': {'name': 'pure_python_sqlite', 'project_validator': 'tools.application_project.configuration',
                'package_builder': 'tools.application_project.build_package', 'check': 'tools.application_project.check_project',
                'code_execution': 'check executes trusted local tests/migrations; catalog does not import application code',
                'preview': 'loopback mock only; not Core authorization or provider readiness',
                'generated_client': 'tools.application_client.render_client; declared file must match before check',
                'previous_package_upgrade': 'tools.application_upgrade.run_packaged_upgrade; explicit previous ZIP and trusted project fixture only',
                'migration_limits': {name: getattr(application_migrations, name) for name in
                    ('TIMEOUT_SECONDS', 'MAX_MIGRATIONS', 'MAX_DATABASE_BYTES', 'MAX_DUMP_BYTES')},
                'migration_scope': 'disposable current declared prefixes; scoped relational unsupported; not historical-data compatibility'},
            'contracts': contracts,
            'models': {f'{model.__module__}.{model.__name__}': model.model_json_schema(mode='validation') for model in selected[3:]},
            'validation': {'package_validator': 'backend.services.module_packages.validate_module_package',
                'semantic_validator_sources': sorted(set(validators)),
                'validator_scope': 'model decorator references, not a copied or exhaustive semantic rule set',
                'meaning': 'schemas are structural; use actual validators/check; no code-trust, grants or installed readiness evaluation'},
            'sdk': {'version': SDK_VERSION, 'platform_error_reasons': sorted(wire.ERROR_REASONS),
                'transport_limits': {name: getattr(wire, name) for name in
                    ('MAX_MESSAGE_BYTES', 'MAX_CONNECTIONS', 'READ_TIMEOUT_SECONDS', 'REQUEST_TIMEOUT_SECONDS', 'MAX_CLOCK_SKEW_SECONDS')},
                'error_contract': _sdk_errors(capture(_SDK_SOURCE))},
            'ui_host': _ui_contract(capture(_UI_SOURCE))}
        if project is not None: result['project'] = _project_catalog(project, capture('VERSION').decode('utf-8-sig').strip())
        if any(_read_source(relative) != data for relative, data in frozen.items()):
            raise ProjectCheckError('catalog', 'Authoritative sources changed during catalog inspection; read a fresh snapshot.')
        result['sources'] = [{'path': relative, 'sha256': hashlib.sha256(data).hexdigest()}
            for relative, data in sorted(frozen.items())]
        return result
    except ProjectCheckError:
        raise
    except (OSError, ValueError, KeyError, StopIteration, TypeError, SyntaxError) as failure:
        raise ProjectCheckError('catalog', 'Catalog source or project declarations could not be validated; inspect the current source.') from failure
