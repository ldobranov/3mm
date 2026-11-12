"""Create a new application source project; no code execution or installation."""
from __future__ import annotations

import ast
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from packages.protocol.module_manifest import MODULE_ID_PATTERN
from packages.protocol.ui_metadata import ROUTE_PATTERN
from tools.application_project import ProjectCheckError, build_package, configuration, fingerprint, inputs, local_path

TEMPLATE = Path(__file__).resolve().parents[1]/'modules/application-starter'
INITIAL_VERSION = '1.0.0'


def _publish_new_directory(source: Path, destination: Path):
    """Rename atomically without replacing a directory created by another process.

    Ordinary POSIX rename can replace an existing empty directory, so it is not
    an adequate no-clobber guard. Supported development hosts are Windows/Linux;
    an unavailable atomic primitive refuses rather than weakening that promise.
    """
    if os.name == 'nt':
        os.rename(source, destination)  # Windows refuses an existing destination.
        return
    if sys.platform == 'linux':
        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, 'renameat2', None)
        if rename is not None:
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:  # RENAME_NOREPLACE
                return
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
    raise ProjectCheckError('create', 'Atomic no-replace project creation requires Windows or Linux renameat2.')


def _context_identity(source: bytes, old_id: str, old_version: str, module_id: str) -> bytes:
    """Change only literal ApplicationContext fixture identity/version arguments."""
    text = source.decode('utf-8')
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1]+len(line.encode('utf-8')))
    changes = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'ApplicationContext':
            continue
        for index, old, new in [(0, old_id, module_id), (1, old_version, INITIAL_VERSION)]:
            if len(node.args) <= index:
                continue
            value = node.args[index]
            if isinstance(value, ast.Constant) and value.value == old:
                changes.append((offsets[value.lineno-1]+value.col_offset,
                                offsets[value.end_lineno-1]+value.end_col_offset, repr(new).encode('utf-8')))
    for start, end, replacement in sorted(changes, reverse=True):
        source = source[:start]+replacement+source[end:]
    return source


def _guide(name: str, module_id: str, route: str) -> bytes:
    return f'''# {name}

New application source project generated from the official minimal Note template.

Read `AGENTS.md` before editing. It carries the application development rules
with this project; the platform checkout's `docs/APPLICATION_DEVELOPMENT.md`
is the main workflow guide. Existing projects are not updated automatically.

- Module ID: `{module_id}`
- Initial package version: `{INITIAL_VERSION}`
- Operator route: `{route}`
- Public application SDK: `1.3`; UI modules: `@platform/ui/v1` and `@platform/application-ui/v1`.
- Own SQLite migration `0001`; human permissions `note_read` and `note_write`.
- Optional resource `command:resource`, configured by `RESOURCE_DEVICE_ID`.

This is still the demonstration note, not a newly implemented product. Update the
service, UI messages and tests for your domain. The private Python package name
`starter_app` is internal to this application's independent service wheel; human
permissions and its data are scoped to this application's installation.

## Created → preview → check

`init` has already created this directory with the identity above. Do not rerun
it over an existing project. Work on these sources, preview the UI locally, then
check/build a new candidate before considering installation.

From the 3mm developer checkout and its existing Python/Node dependencies, replace
these path placeholders (quote paths containing spaces):

```text
python -m tools.extension_dev preview PATH_TO_PROJECT --frontend PATH_TO_CORE_FRONTEND
```

Open the printed loopback address, normally `http://127.0.0.1:5178`, on the same
computer. The tool does not open a browser automatically and does not bind to the
LAN. Press **Ctrl+C** in the terminal to stop the preview and its owned server.
No dependency installation or running Core is required when the existing local
developer toolchain is available.

The project-owned `preview/host.ts` offers six named mock scenarios:

- `normal`: normal access;
- `read_only`: no edit permission / revoked access;
- `provider_unavailable`: provider unavailable, while the note remains usable;
- `access_required`: resource approval missing;
- `unconfirmed`: save completed, acknowledgement lost;
- `conflict`: another simulated editor changed the saved revision.

Scenario changes affect the next application request. Use the note's explicit
Reload control when checking new permissions or resource status; a scenario
change never repeats a save. For a conflict, first edit a draft, choose the
conflict scenario, then explicitly submit once. The shell also offers EN/BG,
light/dark and a narrow preview. Reset affects only simulated data in this tab.

This is an **in-memory browser simulation**, not the real Python service, Core
authorization, a provider health proof or physical execution. Mock data and
receipts are temporary; browser reload/reset starts fresh simulated state. No
login, tokens, installation, grants or hardware are involved. Preview executes
trusted project UI/mock code; it is not a security sandbox or deployment gate.

After reviewing the UI, stop preview and run the common check/build command:

```text
python -m tools.extension_dev check PATH_TO_PROJECT --frontend PATH_TO_CORE_FRONTEND --output OUTPUT_OUTSIDE_PROJECT/app-1.zip
```

The UI uses the configured generated client. After changing declarations/version,
run `python -m tools.extension_dev generate-client PATH_TO_PROJECT --replace`.
It replaces only an unedited generator-owned file for this module, never arbitrary
source, and reports a retained `.runtime/client-recovery` backup. A competing
writer is never overwritten; inspect the reported recovery file on refusal.
Queries need payload only; commands also need the caller-owned original
idempotency key. The client invokes once, propagates errors and grants no access.
TypeScript is structural; actual JSON/bounds/permissions remain runtime checks.
Missing/stale generated content stops `check` before migration/test execution.
Declared `type_tests` add positive and expected-negative compile-only cases.

For a newer candidate, preserve the exact checked previous ZIP and use
`check PATH_TO_PROJECT --previous-archive OLD_ZIP --output NEW_ZIP`.
The standalone `upgrade_fixture` seeds old-package disposable data and verifies
it with the candidate in a separate process. Adapt its domain assertions; the
example proves note/actor-scoped receipt retention, not all business histories.
New-migration rollback probes, integrity and reopen are checked before publishing.
No installed data/device/rights are touched. No previous ZIP means the report
explicitly says upgrade `not_requested`, not upgrade passed.

Before executing project code, `python -m tools.extension_dev catalog` exports
the current checkout's public contracts and authoring limits as JSON. Add
`PATH_TO_PROJECT` to inspect the exact candidate declarations and source/package
hashes using the real package validator, without importing application code,
running tests/migrations/compiler or contacting Core. Catalog output is not a
check pass, code trust, granted access or installed provider readiness.

The check command validates the actual package and probes its packaged migrations
with disposable public-SDK SQLite data (clean creation, reopen, current-plan
prefix upgrades and per-revision rollback). It executes this project's trusted
tests, checks required denial scenarios, UI types and compilation, then writes
a new ZIP/report/log. It installs nothing and never downloads dependencies. Missing
rights, revocation and provider unavailability must not be skipped to get green.
Tests run native developer code, not a hostile-code sandbox. Results are local
evidence, not a live Core/device acceptance or permission to execute native code.
Migration checks do not prove upgrades of old installed business data. Scoped
relational storage is outside this profile and refuses before ZIP publication;
do not skip a required migration check or replace it with a simulated success.
The declared migration target must be the final revision. This local profile has
32-revision/16-MiB-per-database/60-second-worker limits; timeout is not process-tree isolation.

`development.json` selects project tests. Its optional preview profile uses only
project-owned mock data/bindings; it is not a Core authorization authority.
Do not share Windows and Linux native Node dependencies. Existing result files
are never overwritten; choose a new output name for each fresh check.

## Before making this a real application

Review all three descriptors, operations/input/output schemas, migration and data
policy; add domain checks rather than just renaming the example. Choose independent
package versions and a nonconflicting route. Keep service imports limited to the
public SDK/protocol and supported standard library in this minimal profile.

The optional GPIO resource is observed only: no route load, note save or resource
observation sends hardware commands. Keep this separation explicit in your app.
Lost save acknowledgements are not retried. Fresh read-only saved-state reads and
current permissions determine whether another edit is possible. Own data remains
available when a provider is unavailable. Do not enter personal data into the
demonstration note; privacy, retention/export/erasure and quotas need a real policy.

An administrator must separately upload, configure, review exact native code and
approve current resource/human permissions before activation. None of those
actions, API login, grants, deployment, version publication or hardware writes was
performed by project creation.
'''.encode('utf-8')


def create_project(destination, *, module_id, name, route):
    """Freeze the official template, customize identity, validate, then publish new source."""
    if (not isinstance(module_id, str) or len(module_id) > 160 or not re.fullmatch(MODULE_ID_PATTERN, module_id)
            or not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 120
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or not isinstance(route, str) or len(route) > 160 or not re.fullmatch(ROUTE_PATTERN, route)):
        raise ProjectCheckError('create', 'Use a valid module ID, one-line name (1–120 characters), and absolute application route.')
    destination = Path(os.path.abspath(destination))
    if os.path.lexists(destination):
        raise ProjectCheckError('create', 'Destination already exists. Choose a new project directory; nothing was overwritten.')
    if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)() for path in destination.parents):
        raise ProjectCheckError('create', 'Project destination parents must not be symbolic links or junctions.')
    if not destination.parent.is_dir():
        raise ProjectCheckError('create', 'The destination parent directory must already exist.')

    source = inputs(TEMPLATE)
    original_hash = fingerprint(source)
    marker = local_path(TEMPLATE, '.3mm-source-only').read_bytes()
    if marker:
        raise ProjectCheckError('create', 'The source-only template marker must be empty.')
    descriptors = {filename: json.loads(source[filename]) for filename in
                   ('manifest.json', 'application-extension.json', 'compiled-ui.json')}
    old_id = descriptors['manifest.json']['module_id']
    old_version = descriptors['manifest.json']['version']
    if module_id == old_id:
        raise ProjectCheckError('create', 'Choose a new module ID, not the official starter identity.')
    for descriptor in descriptors.values():
        descriptor['module_id'] = module_id
        descriptor['version'] = INITIAL_VERSION
    descriptors['manifest.json']['name'] = name
    service = descriptors['application-extension.json']['service']
    package = json.loads(source['development.json'])['python_package']
    service['artifact'] = f'service/{package}-{INITIAL_VERSION}-py3-none-any.whl'
    service['artifact_sha256'] = '0'*64
    for entry in descriptors['compiled-ui.json']['entrypoints']:
        if entry['kind'] == 'route':
            entry['route'] = route
            entry['label'] = {'en': name}
    for filename, descriptor in descriptors.items():
        source[filename] = (json.dumps(descriptor, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    for filename in source:
        if filename.startswith('tests/') and filename.endswith('.py'):
            source[filename] = _context_identity(source[filename], old_id, old_version, module_id)
    source['README.md'] = _guide(name, module_id, route)

    try:
        with tempfile.TemporaryDirectory(prefix='.3mm-new-', dir=destination.parent) as temporary:
            staged = Path(temporary)/'project'
            for filename, data in {**source, '.3mm-source-only': marker}.items():
                target = staged/filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            from backend.artifacts.packages import validate_module_package
            checked = validate_module_package(build_package(staged))
            generated = configuration(staged).get('generated_client')
            if generated:
                from tools.application_client import render_client
                source[generated] = render_client(checked.application_extension).encode('utf-8')
                local_path(staged, generated).write_bytes(source[generated])
                checked = validate_module_package(build_package(staged))
            if (checked.manifest.module_id != module_id or checked.manifest.version != INITIAL_VERSION
                    or checked.compiled_ui.entrypoints[0].route != route):
                raise ProjectCheckError('create', 'Generated application identity does not match the requested project.')
            if fingerprint(inputs(TEMPLATE)) != original_hash or local_path(TEMPLATE, '.3mm-source-only').read_bytes() != marker:
                raise ProjectCheckError('create', 'Template changed during creation. Run creation again with a fresh destination.')
            _publish_new_directory(staged, destination)
    except ProjectCheckError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ProjectCheckError('create', 'Project creation did not complete; inspect the destination before another action.') from error
    return {'status': 'created', 'project': str(destination), 'module_id': module_id,
            'name': name, 'version': INITIAL_VERSION, 'route': route, 'files_created': len(source)+1,
            'package_semantics': 'passed', 'checks': 'not_run', 'installation': 'not_requested',
            'grants': 'not_requested', 'physical_write': 'not_requested'}
