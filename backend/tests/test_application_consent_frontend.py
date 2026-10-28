"""Decode current HTTP consent responses with the actual frontend TypeScript.

Static UI fixtures alone cannot detect a backend envelope gaining a field.
No VM, application startup, real connector or permission approval is involved.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.db.module import ApplicationConnectorBinding
from backend.routes.application_authority import router
from backend.tests.test_application_consent import state, installed, source_subject, source_installed, identity
from backend.tests.test_application_checkpoints import store_checkpoint_package
from backend.utils.db_utils import get_db

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX authority seals')


def test_actual_backend_previews_pass_the_frontend_boundary(state, tmp_path):
    root = Path(__file__).resolve().parents[2]
    frontend = root / 'frontend'
    node = shutil.which('node')
    if node is None or not (frontend / 'node_modules/esbuild').is_dir():
        pytest.skip('Requires the existing frontend Node/esbuild toolchain')
    s = state
    app = FastAPI()
    app.include_router(router)
    def database():
        with Session(s.engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    url = '/api/v1/application-extensions/' + s.validated.manifest.module_id + '/authority/consent/preview'
    headers = {'Authorization': 'Bearer ' + s.token}
    with TestClient(app) as client:
        normal = client.post(url, headers=headers, json={'request_id': identity()})
        assert normal.status_code == 200, normal.text
        definition = s.validated.application_extension.model_dump(mode='json')
        definition['service']['sdk_version'] = '1.3'
        definition['optional_resources'] = ['connector:business_api']
        definition['command_bindings'] = []
        manifest = s.validated.manifest.model_dump(mode='json')
        manifest['permissions'].remove('capabilities.invoke')
        manifest['capabilities']['consumes'] = []
        store_checkpoint_package(s, definition, manifest)
        with s.engine.begin() as db:
            db.execute(delete(ApplicationConnectorBinding))
        optional = client.post(url, headers=headers, json={'request_id': identity()})
        assert optional.status_code == 200, optional.text
    assert normal.json()['optional_resources'] == []
    assert optional.json()['optional_resources'] == ['connector:business_api']
    assert optional.json()['scopes'] == optional.json()['selected_scopes'] == []
    script = r'''
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [frontend, output] = process.argv.slice(1);
const {build} = createRequire(frontend + '/package.json')('esbuild');
await build({entryPoints:[frontend + '/src/components/extensions/application-consent.ts'],
  outfile:output, bundle:true, format:'esm', platform:'node', logLevel:'silent'});
const {readConsentPreview} = await import(pathToFileURL(output).href);
const responses = JSON.parse(readFileSync(0, 'utf8'));
for (const response of responses) {
  const parsed = readConsentPreview(response, response.module_id);
  if (JSON.stringify(parsed) !== JSON.stringify(response)) throw new Error('Consent projection changed');
}
console.log(JSON.stringify({accepted:responses.length}));
'''
    result = subprocess.run([node, '--input-type=module', '-e', script,
        str(frontend), str(tmp_path / 'consent-decoder.mjs')],
        input=json.dumps([normal.json(), optional.json()]), text=True,
        capture_output=True, cwd=root, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'accepted': 2}
