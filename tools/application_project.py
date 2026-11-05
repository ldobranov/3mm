"""Local application authoring checks. Executes trusted project tests, never installs."""
from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
import zipfile

REPOSITORY = Path(__file__).resolve().parents[1]
SCENARIOS = {'missing_permission', 'revoked_access', 'provider_unavailable'}
IGNORED = {'node_modules', '__pycache__', '.pytest_cache', '.git', 'dist', '.checks', '.runtime'}
SUFFIXES = {'.py', '.json', '.vue', '.ts', '.mjs', '.md'}


class ProjectCheckError(ValueError):
    def __init__(self, stage, message):
        super().__init__(message)
        self.stage = stage


def local_path(root, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ProjectCheckError('project', 'Use a project-relative file path.')
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ProjectCheckError('project', 'Paths must stay inside the application project.')
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ProjectCheckError('project', 'Project inputs must not use symbolic links.')
    if root.resolve() not in path.resolve().parents or not path.is_file():
        raise ProjectCheckError('project', 'A declared project input is unavailable.')
    return path


def configuration(root):
    value = json.loads(local_path(root, 'development.json').read_text(encoding='utf-8-sig'))
    required = {'development_version', 'python_package', 'python_tests', 'ui_tests', 'scenarios'}
    if (type(value) is not dict or not required <= set(value) or set(value) - required - {'preview', 'generated_client', 'upgrade_fixture', 'type_tests'}
            or type(value['development_version']) is not int or value['development_version'] != 1
            or not isinstance(value['python_package'], str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', value['python_package'])
            or type(value['python_tests']) is not list or not 1 <= len(value['python_tests']) <= 16
            or type(value['scenarios']) is not dict or set(value['scenarios']) != SCENARIOS):
        raise ProjectCheckError('project', 'Invalid development.json or missing required denial scenarios.')
    for name in [*value['python_tests'], value['ui_tests']]:
        local_path(root, name)
        if not name.startswith('tests/'):
            raise ProjectCheckError('project', 'Checks must live in this project\'s tests directory.')
    for node in value['scenarios'].values():
        if not isinstance(node, str) or len(node.split('::')) != 2:
            raise ProjectCheckError('project', 'Each scenario needs a pytest file::test_function identity.')
        file, function = node.split('::')
        if file not in value['python_tests'] or not re.fullmatch('test_[a-z0-9_]+', function):
            raise ProjectCheckError('project', 'Scenarios must name tests in python_tests.')
    if 'preview' in value:
        preview = value['preview']
        if (type(preview) is not dict or set(preview) != {'entrypoint_id', 'host'}
                or not isinstance(preview['entrypoint_id'], str)
                or not re.fullmatch('[a-z][a-z0-9_-]{0,63}', preview['entrypoint_id'])
                or not isinstance(preview['host'], str) or not preview['host'].startswith('preview/')
                or not preview['host'].endswith('.ts')):
            raise ProjectCheckError('project', 'Preview needs an entrypoint ID and a local preview/*.ts host.')
        local_path(root, preview['host'])
    if 'generated_client' in value:
        generated = value['generated_client']
        if (not isinstance(generated, str) or not generated.startswith('source/frontend/')
                or not generated.endswith('.ts') or '\\' in generated or '..' in Path(generated).parts
                or Path(generated).is_absolute()):
            raise ProjectCheckError('project', 'generated_client must name a project-local source/frontend/*.ts file.')
        # A newly declared client may not exist until explicit generation.
        # check_project requires the actual file and its exact generated content.
    if 'upgrade_fixture' in value:
        fixture = value['upgrade_fixture']
        if not isinstance(fixture, str) or not fixture.startswith('tests/') or not fixture.endswith('.py'):
            raise ProjectCheckError('project', 'upgrade_fixture must name a local tests/*.py file.')
        local_path(root, fixture)
    if 'type_tests' in value:
        if type(value['type_tests']) is not list or not 1 <= len(value['type_tests']) <= 16:
            raise ProjectCheckError('project', 'type_tests must name one to sixteen local tests/*.ts files.')
        for name in value['type_tests']:
            if not isinstance(name, str) or not name.startswith('tests/') or not name.endswith('.ts'):
                raise ProjectCheckError('project', 'Type-only checks must be local tests/*.ts files.')
            local_path(root, name)
    return value


def inputs(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            if name not in IGNORED and (Path(directory)/name).is_symlink():
                raise ProjectCheckError('project', 'Project inputs must not use symbolic links.')
        dirs[:] = sorted(name for name in dirs if name not in IGNORED)
        for name in sorted(files):
            path = Path(directory)/name
            if path.suffix not in SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            data = local_path(root, relative).read_bytes().replace(b'\r\n', b'\n')
            if len(data) > 1024*1024 or len(result) >= 128:
                raise ProjectCheckError('project', 'Project source budget exceeded.')
            result[relative] = data
    return result


def fingerprint(source):
    return hashlib.sha256(json.dumps({n: hashlib.sha256(b).hexdigest() for n, b in sorted(source.items())},
                                     sort_keys=True).encode()).hexdigest()


def write_member(archive, name, data):
    info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def build_package(root):
    """Standard pure-Python wheel + manifest-v2 ZIP; no application code import."""
    project = configuration(root)
    source = inputs(root)
    manifest, application, ui = [json.loads(source[name]) for name in
        ('manifest.json', 'application-extension.json', 'compiled-ui.json')]
    package = project['python_package']
    version = manifest['version']
    prefix = 'service/' + package + '/'
    files = {name.removeprefix('service/'): data for name, data in source.items()
             if name.startswith(prefix) and name.endswith('.py')}
    if package + '/__init__.py' not in files:
        raise ProjectCheckError('build', 'The service needs a Python package with __init__.py.')
    for data in files.values():
        # This is an authoring lint, not a sandbox or a substitute for native review.
        for node in ast.walk(ast.parse(data)):
            imports = [item.name for item in node.names] if isinstance(node, ast.Import) else (
                [node.module or ''] if isinstance(node, ast.ImportFrom) and not node.level else [])
            if any(name.split('.')[0] in {'backend', 'agent', 'tools', 'deployment', 'three_mm_runtime', 'three_mm_platform_runtime'} for name in imports):
                raise ProjectCheckError('imports', 'Service code must use public SDK/protocol imports, not Core internals.')
    dist = f'{package}-{version}.dist-info'
    files[dist+'/METADATA'] = f'Metadata-Version: 2.1\nName: {package.replace("_", "-")}\nVersion: {version}\n'.encode()
    files[dist+'/WHEEL'] = b'Wheel-Version: 1.0\nGenerator: 3mm-authoring\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, data in sorted(files.items()):
        writer.writerow([name, 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(), len(data)])
    writer.writerow([dist+'/RECORD', '', ''])
    files[dist+'/RECORD'] = record.getvalue().encode()
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, data in sorted(files.items()):
            write_member(archive, name, data)
    expected_artifact = f'service/{package}-{version}-py3-none-any.whl'
    if application['service']['artifact'] != expected_artifact:
        raise ProjectCheckError('build', 'The service artifact must match the project package and version.')
    application['service']['artifact_sha256'] = hashlib.sha256(wheel.getvalue()).hexdigest()
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        for name, value in [('manifest.json', manifest), ('application-extension.json', application), ('compiled-ui.json', ui)]:
            write_member(archive, name, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode())
        write_member(archive, expected_artifact, wheel.getvalue())
        for name, data in sorted(source.items()):
            if name.startswith('source/frontend/'):
                write_member(archive, name, data)
    return result.getvalue()


def run_check(command, *, cwd, environment, stage, log, timeout=180):
    try:
        result = subprocess.run(command, cwd=cwd, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProjectCheckError(stage, 'Check could not complete; verify the existing local toolchain.') from error
    if result.returncode:
        raise ProjectCheckError(stage, 'Check failed. See the local check log; no package was published.')


def read_junit(path, stage):
    """Require executed, clean evidence, including suite-level collection errors."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ProjectCheckError(stage, 'Check result evidence is missing or invalid; no package was published.') from error
    cases = list(root.iter('testcase'))
    if root.tag not in {'testsuite', 'testsuites'} or not cases:
        raise ProjectCheckError(stage, 'Check evidence must contain executed tests, not an empty result.')
    if any(node.tag in {'skipped', 'failure', 'error'} for node in root.iter()):
        raise ProjectCheckError(stage, 'Required checks must execute without failures or skips.')
    for node in root.iter():
        if node.tag not in {'testsuite', 'testsuites'}:
            continue
        for name in ('failures', 'errors', 'skipped', 'disabled'):
            value = node.get(name, '0')
            if not value.isdecimal() or int(value) != 0:
                raise ProjectCheckError(stage, 'Check suite reports failed, skipped or invalid result evidence.')
        if 'tests' in node.attrib:
            value = node.get('tests')
            if not value.isdecimal() or int(value) != len(list(node.iter('testcase'))):
                raise ProjectCheckError(stage, 'Check suite test count does not match its executed result evidence.')
    return cases


def declaration_review(validated):
    """Describe authoritative validated declarations, never infer installed grants."""
    definition = validated.application_extension
    manifest = validated.manifest
    bindings = ('command_bindings', 'session_bindings', 'query_dependencies',
                'connectors', 'event_subscriptions', 'peer_bindings', 'checkpoints')
    return {
        'scope': 'validated package declarations; not code trust, current grants or provider readiness',
        'identity': {'module_id': manifest.module_id, 'version': manifest.version,
            'manifest_version': manifest.manifest_version,
            'application_extension_version': definition.application_extension_version,
            'compiled_ui_version': validated.compiled_ui.compiled_ui_version,
            'sdk_version': definition.service.sdk_version,
            'service_artifact_sha256': definition.service.artifact_sha256,
            'compatibility': manifest.compatibility.model_dump(mode='json')},
        'human_permissions': [item.permission_id for item in definition.permissions],
        'permission_definitions': [item.model_dump(mode='json') for item in definition.permissions],
        'manifest_permissions': list(manifest.permissions),
        'operations': [item.model_dump(mode='json') for item in definition.operations],
        'routes': [item.model_dump(mode='json') for item in definition.routes],
        'optional_resources': list(definition.optional_resources),
        'resource_bindings': {name: [item.model_dump(mode='json', exclude_none=True)
                                   for item in getattr(definition, name)] for name in bindings},
        'platform_requirements': [item.model_dump(mode='json') for item in definition.platform_requirements],
        'platform_permissions': list(definition.platform_permissions),
        'storage': definition.storage.model_dump(mode='json', exclude_none=True),
        'configuration_required': manifest.configuration_schema.get('required', []),
        'configuration_schema': manifest.configuration_schema,
    }


def write_report(path, summary):
    """Write only an owned private file, which may be linked to its final name."""
    with path.open('w', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def same_output(private, final):
    """Reject a replaced final name without opening, truncating or deleting it."""
    try:
        current = final.stat(follow_symlinks=False)
        return stat.S_ISREG(current.st_mode) and os.path.samestat(private.stat(), current)
    except OSError:
        return False


def publish_outputs(root, output, summary, blob):
    """Complete evidence precedes the exclusive ZIP publication. No final unlink."""
    report_path = output.with_suffix('.report.json')
    log_path = output.with_suffix('.checks.log')
    private_report = root/'report.json'
    summary['evidence'] = {'report': 'not_published', 'log': 'not_published'}
    try:
        os.link(root/'checks.log', log_path)
        summary.update(log=str(log_path))
        summary['evidence']['log'] = 'published'
        # A later update uses this same owned inode, never reopens a final path
        # which another process could have replaced with its own file.
        summary.update(report=str(report_path))
        summary['evidence']['report'] = 'prepared'
        write_report(private_report, summary)
        os.link(private_report, report_path)
        summary['evidence']['report'] = 'published'
        for private, final, name in ((root/'checks.log', log_path, 'log'), (private_report, report_path, 'report')):
            if not same_output(private, final):
                summary['evidence'][name] = 'unconfirmed'
                raise OSError('Evidence output changed before package publication')
        if summary['status'] == 'passed':
            private_zip = root/'candidate.zip'
            with private_zip.open('xb') as saved:
                saved.write(blob)
                saved.flush()
                os.fsync(saved.fileno())
            summary['package_publication'] = 'unconfirmed'
            try:
                os.link(private_zip, output)
            except FileExistsError:
                summary['package_publication'] = 'not_published'
                raise
            summary['package_publication'] = 'published'
        summary['evidence']['report'] = 'published'
        write_report(private_report, summary)
        for private, final, name in ((root/'checks.log', log_path, 'log'), (private_report, report_path, 'report')):
            if not same_output(private, final):
                summary['evidence'][name] = 'unconfirmed'
                raise OSError('Evidence output changed during publication')
        if summary['package_publication'] == 'published' and not same_output(private_zip, output):
            summary['package_publication'] = 'unconfirmed'
            raise OSError('Package output changed during publication')
    except OSError as error:
        summary.update(status='failed', stage='output', error_type=type(error).__name__,
            message=('The package was published, but final evidence could not be confirmed. Inspect its exact SHA256 before use.'
                     if summary['package_publication'] == 'published' else
                     'Output evidence or package publication failed. No file was overwritten; inspect the reported paths.'))
        # An existing report belongs to its owner: update our private inode only
        # when its link was created, never the colliding final path.
        if summary['evidence']['report'] in {'published', 'unconfirmed'}:
            try:
                write_report(private_report, summary)
            except OSError:
                summary['evidence']['report'] = 'unconfirmed'
        elif summary['evidence']['report'] == 'prepared':
            summary['evidence']['report'] = 'not_published'
            summary.pop('report', None)
    return summary


def check_project(project, output, *, frontend=None, previous_archive=None):
    """Check a frozen local source copy with existing tools. No installs or API calls."""
    from backend.services.module_packages import validate_module_package
    from backend.services.compiled_ui import compile_ui_package
    from tools.application_migrations import run_packaged_migrations

    project = Path(project).absolute()
    output = Path(output).absolute()
    report_path = output.with_suffix('.report.json')
    log_path = output.with_suffix('.checks.log')
    # Keeping results outside the project also prevents checks from hashing their own output.
    if project.resolve() in output.resolve().parents:
        raise ProjectCheckError('output', 'Put outputs outside the source project.')
    if any(path.exists() or path.is_symlink() for path in (output, report_path, log_path)):
        raise ProjectCheckError('output', 'Output already exists. Choose a new name; nothing was overwritten.')
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = {'check_version': 1, 'status': 'failed', 'package_publication': 'not_published',
               'environment': {'python': sys.version.split()[0]}, 'stages': [],
               'scope': 'local authoring checks; project tests execute trusted local code, not sandboxed',
               'installation': 'not_requested', 'grants': 'not_requested', 'physical_write': 'not_requested',
               'live_acceptance': 'not_performed'}
    with tempfile.TemporaryDirectory(prefix='.3mm-application-check-', dir=output.parent,
                                     ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        with (root/'checks.log').open('x', encoding='utf-8') as log:
            phase = 'project'
            blob = None
            try:
                if project.is_symlink() or not project.is_dir():
                    raise ProjectCheckError('project', 'Select a regular application project directory.')
                config = configuration(project)
                source = inputs(project)
                source_hash = fingerprint(source)
                summary['source_sha256'] = source_hash
                frontend = Path(frontend or REPOSITORY/'frontend').resolve()
                node = os.getenv('COMPILED_UI_NODE') or shutil.which('node')
                vitest = frontend/'node_modules/vitest/vitest.mjs'
                typescript = frontend/'node_modules/vue-tsc/bin/vue-tsc.js'
                phase = 'toolchain'
                if not node or not vitest.is_file() or not typescript.is_file():
                    raise ProjectCheckError('toolchain', 'Existing Node, Vitest and vue-tsc dependencies are required; nothing was installed.')
                snapshot = root/'source'
                for name, data in source.items():
                    target = snapshot/name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1',
                    'PYTHONPATH': os.pathsep.join([str(REPOSITORY), str(snapshot/'service')]),
                    'THREE_MM_FRONTEND_DIR': str(frontend)}
                phase = 'build'
                blob = build_package(snapshot)
                if blob != build_package(snapshot):
                    raise ProjectCheckError('build', 'The package is not reproducible.')
                phase = 'package_validation'
                validated = validate_module_package(blob)
                from backend.version import core_version
                summary['semantic_validation'] = {
                    'validator': 'backend.services.module_packages.validate_module_package',
                    'status': 'passed', 'core_version': core_version(),
                    'scope': 'package, model and cross-document rules; not installed authority'}
                summary['review'] = declaration_review(validated)
                summary['stages'].append('package_validation')
                if 'generated_client' in config:
                    phase = 'generated_client'
                    from tools.application_client import render_client
                    generated = source.get(config['generated_client'])
                    expected = render_client(validated.application_extension).encode('utf-8')
                    if generated != expected:
                        raise ProjectCheckError('generated_client',
                            'The declared generated client is missing or stale. Generate it explicitly before checking.')
                    summary['generated_client'] = {'status': 'passed', 'path': config['generated_client'],
                        'sha256': hashlib.sha256(expected).hexdigest()}
                    summary['stages'].append('generated_client')
                phase = 'migrations'
                summary['migrations'] = run_packaged_migrations(blob, validated,
                    root=root, environment=environment, log=log)
                summary['stages'].append('packaged_migrations')
                summary['upgrade'] = {'status': 'not_requested',
                    'scope': 'no previous package or real historical data was checked'}
                if previous_archive is not None:
                    phase = 'upgrade'
                    if 'upgrade_fixture' not in config:
                        raise ProjectCheckError('upgrade', 'Previous-package checks require an explicit tests/*.py upgrade_fixture.')
                    from three_mm_protocol.diagnostic_snapshot import read_regular
                    from backend.services.module_packages import MAX_PACKAGE_BYTES
                    from tools.application_upgrade import run_packaged_upgrade
                    previous_blob = read_regular(Path(previous_archive), MAX_PACKAGE_BYTES)
                    previous_validated = validate_module_package(previous_blob)
                    summary['previous_package'] = {'module_id': previous_validated.manifest.module_id,
                        'version': previous_validated.manifest.version, 'sha256': previous_validated.sha256,
                        'bytes': len(previous_blob)}
                    summary['upgrade'] = run_packaged_upgrade(previous_blob, previous_validated, blob, validated,
                        fixture=local_path(snapshot, config['upgrade_fixture']),
                        root=root, environment=environment, log=log)
                    summary['stages'].append('previous_package_upgrade')
                phase = 'python'
                run_check([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--strict-markers',
                           '--rootdir='+str(snapshot),
                           *config['python_tests'], '--basetemp='+str(root/'pytest'), '--junitxml='+str(root/'python.xml')],
                    cwd=snapshot, environment=environment, stage='python', log=log)
                cases = read_junit(root/'python.xml', 'python')
                phase = 'scenarios'
                for scenario, node_id in config['scenarios'].items():
                    file, function = node_id.split('::')
                    classname = file.removesuffix('.py').replace('/', '.')
                    if not any(c.get('classname') == classname and c.get('name') == function for c in cases):
                        raise ProjectCheckError('scenarios', 'A required denial scenario did not execute.')
                summary.update(python_passed=len(cases), scenarios={name: 'passed' for name in sorted(SCENARIOS)},
                               scenarios_level='project tests; not live Core authority conformance')
                summary['stages'].append('python_and_denial_scenarios')
                phase = 'ui'
                run_check([node, str(vitest), 'run', '--config', str(snapshot/config['ui_tests']), '--maxWorkers=1',
                           '--reporter=junit', '--outputFile='+str(root/'ui.xml')],
                    cwd=snapshot, environment=environment, stage='ui', log=log)
                ui_cases = read_junit(root/'ui.xml', 'ui')
                summary['ui_passed'] = len(ui_cases)
                summary['stages'].append('ui_tests')
                phase = 'typecheck'
                tsconfig = root/'tsconfig.json'
                tsconfig.write_text(json.dumps({'compilerOptions': {'strict': True, 'noEmit': True,
                    'target': 'ES2022', 'module': 'ESNext', 'moduleResolution': 'Bundler', 'skipLibCheck': True,
                    'lib': ['ES2022', 'DOM', 'DOM.Iterable'], 'resolveJsonModule': True, 'esModuleInterop': True,
                    'baseUrl': str(snapshot), 'paths': {
                        'vue': [str(frontend/'node_modules/vue')],
                        '@3mm/ui/v1': [str(frontend/'src/extension-ui/v1.ts')],
                        '@3mm/application-ui/v1': [str(frontend/'src/extension-ui/application-v1.ts')]}},
                    'include': [str(snapshot/'source/frontend/**/*.vue'), str(snapshot/'source/frontend/**/*.ts'),
                                *[str(snapshot/name) for name in config.get('type_tests', [])],
                                *([str(snapshot/config['preview']['host'])] if 'preview' in config else [])]}), encoding='utf-8')
                run_check([node, str(typescript), '--project', str(tsconfig)],
                    cwd=snapshot, environment=environment, stage='typecheck', log=log)
                summary['stages'].append('ui_typecheck')
                phase = 'ui_compilation'
                previous = os.environ.get('COMPILED_UI_ARTIFACTS_DIR')
                os.environ['COMPILED_UI_ARTIFACTS_DIR'] = str(root/'compiled')
                try:
                    artifact = compile_ui_package(blob, validated)
                    summary['built_ui_sha256'] = artifact.built_ui_sha256
                    summary['environment']['ui_toolchain'] = json.loads((artifact.path/'build-toolchain.json').read_text())
                finally:
                    if previous is None:
                        os.environ.pop('COMPILED_UI_ARTIFACTS_DIR', None)
                    else:
                        os.environ['COMPILED_UI_ARTIFACTS_DIR'] = previous
                summary['stages'].append('actual_ui_compilation')
                phase = 'source'
                if fingerprint(inputs(project)) != source_hash or fingerprint(inputs(snapshot)) != source_hash:
                    raise ProjectCheckError('source', 'Source changed during checks. Run a fresh check; no artifact was published.')
                summary.update(status='passed', package={'path': str(output), 'sha256': validated.sha256,
                    'module_id': validated.manifest.module_id, 'version': validated.manifest.version, 'bytes': len(blob)})
            except ProjectCheckError as error:
                summary.update(stage=error.stage, message=str(error))
            except Exception as error:
                # Keep project/response content and local environment out of terminal output.
                traceback.print_exc(file=log)
                summary.update(stage=phase, message='Package validation failed.' if phase == 'package_validation'
                               else 'Check could not complete. See the local check log.', error_type=type(error).__name__)
                from pydantic import ValidationError
                cause = error if isinstance(error, ValidationError) else error.__cause__
                if isinstance(cause, ValidationError):
                    summary['issues'] = [{'path': list(item['loc']), 'code': item['type']}
                        for item in cause.errors(include_input=False, include_context=False, include_url=False)[:12]]
        return publish_outputs(root, output, summary, blob)
