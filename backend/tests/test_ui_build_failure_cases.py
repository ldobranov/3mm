"""An authenticated upload exposes the same safe process outcome as the support report."""
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.accounts import tokens
from backend.artifacts import api, compiled_ui
from backend.db.module import ModulePackage
from backend.system.diagnostics import cases, failures
from backend.tests.test_compiled_ui import fake_compiler, package
from backend.tests.test_device_pairing_routes import make_client
from tools.diagnostics import explain


@pytest.mark.parametrize('outcome', ['compiler_timeout', 'compiler_process_error', 'compiler_unsuccessful_exit',
                                     'compiler_entry_unreadable', 'no_directory', 'no_index', 'invalid_index', 'missing_asset'])
def test_compiler_failure_is_redacted_in_response_and_explained_offline(outcome, monkeypatch, tmp_path):
    bad_output = outcome in {'no_directory', 'no_index', 'invalid_index', 'missing_asset'}
    reason = 'compiler_output_invalid' if bad_output else outcome
    monkeypatch.setattr(tokens, 'SECRET_KEY', 'test-only-ui-build-case-secret-at-least-32-bytes')
    uploads = tmp_path / 'uploads'
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=uploads)))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(tmp_path / 'artifacts'))
    client, db, admin, viewer = make_client()
    ring = failures.RecentHttpFailures()
    client.app.include_router(api.router)
    client.app.add_middleware(failures.HttpFailureMiddleware, store=ring)
    marker = 'PRIVATE_COMPILER_SOURCE_AND_HOST_PATH'
    calls = []
    missing_tool = reason == 'compiler_entry_unreadable'
    status = 503 if missing_tool or bad_output else 422
    if missing_tool:
        monkeypatch.setenv('COMPILED_UI_COMPILER_SCRIPT', str(tmp_path / marker))

    def compiler(cmd, **kwargs):
        calls.append(1)
        if bad_output:
            output = Path(cmd[3])
            if outcome != 'no_directory':
                output.mkdir()
            if outcome in {'invalid_index', 'missing_asset'}:
                (output / 'entrypoints.json').write_text(json.dumps({
                    'entries': {'clock': marker if outcome == 'missing_asset' else []}}))
            return subprocess.CompletedProcess(cmd, 0, marker, '')
        if reason == 'compiler_timeout':
            raise subprocess.TimeoutExpired([marker], 90)
        if reason == 'compiler_process_error':
            raise PermissionError(marker)
        return subprocess.CompletedProcess(cmd, 1, '', marker)

    monkeypatch.setattr(compiled_ui.subprocess, 'run', compiler)
    blob = package()
    digest = hashlib.sha256(blob).hexdigest()

    def upload(token):
        return client.post('/api/v1/modules/packages', files={'package': ('app.zip', blob)},
                           headers={'Authorization': 'Bearer ' + token})

    try:
        assert upload(viewer).status_code == 403 and not calls
        response = upload(admin)
        assert response.status_code == status and calls == ([] if missing_tool else [1])
        assert db.scalar(select(ModulePackage.id)) is None
        assert not (uploads / 'modules' / (digest + '.zip')).exists()
        assert not list((tmp_path / 'artifacts').rglob(digest))
        export = cases.build_cases(ring.snapshot(), {'records': []}, {'probe_status': 'complete'})
        case, = [row for row in export['cases'] if row['evidence']['status'] == status]
        assert case['operation'] == 'package.ui_build'
        assert (case['evidence']['stage'], case['evidence']['reason']) == ('package.ui_compile', reason)
        assert case['summary'] == response.json()['detail']
        offline, = [c for c in explain(export)['cases'] if c['http_status'] == status]
        assert offline['reason'] == reason and offline['summary'] == case['summary']
        assert not offline['automatic_replay_allowed']
        assert marker not in response.text + json.dumps(export) + json.dumps(offline)
    finally:
        client.close()
        db.close()


def test_reupload_with_damaged_cached_index_keeps_registered_zip_without_reporting_a_new_build(monkeypatch, tmp_path):
    monkeypatch.setattr(tokens, 'SECRET_KEY', 'test-only-ui-build-case-secret-at-least-32-bytes')
    uploads, artifacts = tmp_path / 'uploads', tmp_path / 'artifacts'
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=uploads)))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(artifacts))
    calls = []
    monkeypatch.setattr(compiled_ui.subprocess, 'run', fake_compiler(calls))
    client, db, admin, _ = make_client()
    client.app.include_router(api.router)
    ring = failures.RecentHttpFailures()
    client.app.add_middleware(failures.HttpFailureMiddleware, store=ring)
    blob = package()
    def upload():
        return client.post('/api/v1/modules/packages', files={'package': ('app.zip', blob)},
                           headers={'Authorization': 'Bearer ' + admin})
    try:
        assert upload().status_code == 200
        record = db.scalars(select(ModulePackage)).one()
        archive = Path(record.file_path)
        (artifacts / record.module_id / record.version / record.sha256 / 'entrypoints.json').write_text('[]')
        assert upload().status_code == 422 and len(calls) == 1
        assert db.scalars(select(ModulePackage)).one().id == record.id and archive.read_bytes() == blob
        export = cases.build_cases(ring.snapshot(), {'records': []}, {'probe_status': 'complete'})
        assert all(row['evidence']['stage'] != 'package.ui_compile' for row in export['cases'])
    finally:
        client.close()
        db.close()
