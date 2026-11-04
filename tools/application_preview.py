"""Explicit loopback UI simulation using existing tools; never an installed Core."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools.application_project import REPOSITORY, ProjectCheckError, build_package, configuration, local_path

ASSETS = Path(__file__).with_suffix('')


def preview_settings(project, *, frontend=None, port=5178):
    from backend.services.module_packages import validate_module_package

    if type(port) is not int or not 1024 <= port <= 65535:
        raise ProjectCheckError('preview', 'Choose a local port between 1024 and 65535.')
    project = Path(project).absolute()
    config = configuration(project)
    if 'preview' not in config:
        raise ProjectCheckError('preview', 'This project has no preview host in development.json.')
    validated = validate_module_package(build_package(project))
    ui = json.loads(local_path(project, 'compiled-ui.json').read_text(encoding='utf-8-sig'))
    entry = next((e for e in ui['entrypoints'] if e['entrypoint_id'] == config['preview']['entrypoint_id']), None)
    if entry is None or entry['kind'] != 'route' or not any(
        route.entrypoint_id == entry['entrypoint_id'] and route.audience == 'operator'
        for route in validated.application_extension.routes
    ):
        raise ProjectCheckError('preview', 'Choose an existing operator route entrypoint for local preview.')
    frontend = Path(frontend or REPOSITORY/'frontend').resolve()
    node = os.getenv('COMPILED_UI_NODE') or shutil.which('node')
    if not node or not (frontend/'node_modules/vite').is_dir() or not (frontend/'node_modules/@vitejs/plugin-vue').is_dir():
        raise ProjectCheckError('toolchain', 'Existing Node/Vite/Vue dependencies are required; nothing was installed.')
    definition = validated.application_extension
    operations = [{'operation_id': op.operation_id, 'kind': op.kind, 'idempotency': op.idempotency}
                  for op in definition.operations if 'operator' in op.audiences]
    return {'node': node, 'frontend': str(frontend), 'project': str(project), 'port': port,
        'source': str(local_path(project, entry['source'])),
        'mock': str(local_path(project, config['preview']['host'])),
        'info': {'host_version': 1, 'module_id': validated.manifest.module_id,
            'active_version': validated.manifest.version, 'artifact_sha256': '0'*64,
            'entrypoint_id': entry['entrypoint_id'], 'audience': 'operator',
            'features': {'operations': True, 'resource_authority': 'separate', 'browser_isolation': False,
                         'presentation_version': 1}, 'operations': operations}}


def preview_project(project, *, frontend=None, port=5178):
    settings = preview_settings(project, frontend=frontend, port=port)
    with tempfile.TemporaryDirectory(prefix='3mm-application-preview-') as temporary:
        root = Path(temporary)
        (root/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>3mm local simulation</title></head><body><div id="app"></div>'
            '<script type="module" src="/main.ts"></script></body></html>', encoding='utf-8')
        (root/'main.ts').write_text("import {createApp} from 'vue'; import Shell from '@preview-shell'; "
            "createApp(Shell).mount('#app');\n", encoding='utf-8')
        settings['root'] = str(root)
        (root/'settings.json').write_text(json.dumps(settings), encoding='utf-8')
        # The project is trusted development code, not a hostile-code sandbox.
        child = subprocess.Popen([settings['node'], str(ASSETS/'serve.mjs'), str(root/'settings.json')],
                                 cwd=project)
        try:
            result = child.wait()
            if result:
                raise ProjectCheckError('preview', 'Preview stopped unsuccessfully; inspect local tool output.')
        except KeyboardInterrupt:
            pass
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
