"""Actual two-package HTTP preview decoded by the shipped TypeScript boundary."""
import json
import os
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from backend.routes.application_authority import router
from backend.tests.test_application_composition_authority import pair, installed, source_subject, source_installed, identity
from backend.utils.db_utils import get_db

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real M20 package/key fixture')


def test_real_query_preview_matches_frontend_contract_without_hidden_selection(pair, tmp_path):
    app = FastAPI(); app.include_router(router)
    def database():
        with Session(pair.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    module = pair.consumer.manifest.module_id
    with TestClient(app) as client:
        response = client.post(f'/api/v1/application-extensions/{module}/authority/consent/preview',
            headers={'Authorization': 'Bearer '+pair.token}, json={'request_id': identity()})
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['selected_scopes'] == []
    (tmp_path/'query-preview.json').write_text(json.dumps(value), encoding='utf-8')
    root = Path(__file__).resolve().parents[2]
    frontend = root/'frontend'
    node = shutil.which('node')
    if node is None or not (frontend/'compiler/node_modules/esbuild').is_dir():
        pytest.skip('Requires locked Node/esbuild toolchain; HTTP preview retained, not a parser pass')
    script = r'''
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [frontend, output] = process.argv.slice(1);
const {build} = createRequire(frontend+'/compiler/package.json')('esbuild');
await build({entryPoints:[frontend+'/src/components/extensions/application-consent.ts'],
  outfile:output,bundle:true,format:'esm',platform:'node',logLevel:'silent'});
const {readConsentPreview} = await import(pathToFileURL(output).href);
const value = JSON.parse(readFileSync(0,'utf8'));
if (JSON.stringify(readConsentPreview(value,value.module_id)) !== JSON.stringify(value)) throw new Error('Projection changed');
const bad = structuredClone(value); bad.resources.queries[0].export.contract.contract_version = '2.0';
let refused = false; try {readConsentPreview(bad,bad.module_id)} catch {refused = true}
if (!refused) throw new Error('Contract drift was accepted');
console.log(JSON.stringify({accepted:1,refused:1}));
'''
    result = subprocess.run([node, '--input-type=module', '-e', script, str(frontend), str(tmp_path/'query-decoder.mjs')],
        input=json.dumps(value), text=True, capture_output=True, cwd=root, timeout=45)
    assert result.returncode == 0, result.stdout+result.stderr
    assert json.loads(result.stdout) == {'accepted': 1, 'refused': 1}
