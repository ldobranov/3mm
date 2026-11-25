"""An installed version wins before building; a busy build must not stall Core reads."""
import asyncio
import hashlib
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.accounts import tokens
from backend.artifacts import api, compiled_ui
from backend.db.module import ModulePackage
from backend.storage.sessions import get_db
from backend.system.diagnostics import cases, failures
from backend.tests.test_compiled_ui import fake_compiler, package
from backend.tests.test_device_pairing_routes import make_client


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(tokens, 'SECRET_KEY', 'package-admission-test-key-with-at-least-32-bytes')
    engine = create_engine('sqlite:///'+str(tmp_path/'db'), connect_args={'check_same_thread': False})
    client, seed, admin, viewer = make_client(engine)
    def session():
        with Session(engine) as db:
            yield db
    client.app.dependency_overrides[get_db] = session
    client.app.include_router(api.router)
    ring = failures.RecentHttpFailures()
    client.app.add_middleware(failures.HttpFailureMiddleware, store=ring)
    monkeypatch.setattr(api, 'get_settings', lambda: SimpleNamespace(backend=SimpleNamespace(uploads_dir=tmp_path/'uploads')))
    monkeypatch.setenv('COMPILED_UI_ARTIFACTS_DIR', str(tmp_path/'compiled'))
    try:
        yield client, seed, {'Authorization':'Bearer '+admin}, {'Authorization':'Bearer '+viewer}, ring
    finally:
        client.close()
        seed.close()
        engine.dispose()


route = '/api/v1/modules/packages'
def files(blob):
    return {'package': ('ui.zip', blob, 'application/zip')}


def test_existing_version_conflict_does_not_build_or_leave_candidate_files(lab, monkeypatch, tmp_path):
    client, db, admin, _, ring = lab
    built = []
    monkeypatch.setattr(compiled_ui.subprocess, 'run', fake_compiler(built))
    old, other = package(), package('<template><p>candidate</p></template>')
    assert client.post(route, headers=admin, files=files(old)).status_code == 200
    refused = client.post(route, headers=admin, files=files(other))
    assert refused.status_code == 409 and len(built) == 1
    row, = db.scalars(select(ModulePackage)).all()
    assert Path(row.file_path).read_bytes() == old
    digest = hashlib.sha256(other).hexdigest()
    assert not list(tmp_path.rglob(digest)) and not list(tmp_path.rglob(digest+'.zip'))
    case, = cases.build_cases(ring.snapshot(), {'records':[]}, {'probe_status':'complete'})['cases']
    assert case['evidence']['reason'] == 'package_version_conflict' and case['evidence']['stage'] == 'package.catalog_check'
    assert case['summary'] == refused.json()['detail'] and not case['automatic_replay_allowed']


def test_management_read_and_second_upload_while_first_build_is_paused(lab, monkeypatch):
    client, _, admin, viewer, ring = lab
    entered, release = threading.Event(), threading.Event()
    calls = []
    def hold(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise AssertionError('Core did not service the other requests during the controlled build')
        return fake_compiler(calls)(*args, **kwargs)
    monkeypatch.setattr(compiled_ui.subprocess, 'run', hold)
    blob = package()
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url='http://test') as c:
            first = asyncio.create_task(c.post(route, headers=admin, files=files(blob)))
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                assert not first.done()
                listing = await c.get(route, headers=admin)
                assert listing.status_code == 200 and listing.json() == []
                assert (await c.post(route, headers=viewer, files=files(blob))).status_code == 403
                busy = await c.post(route, headers=admin, files=files(blob))
                assert busy.status_code == 503 and not first.done()
                case, = [r for r in cases.build_cases(ring.snapshot(), {'records':[]}, {'probe_status':'complete'})['cases'] if r['evidence']['status']==503]
                assert case['evidence']['reason'] == 'package_store_busy' and case['summary'] == busy.json()['detail']
            finally:
                release.set()
                result = await first
            assert result.status_code == 200
            assert (await c.post(route, headers=admin, files=files(blob))).status_code == 200
            assert len(calls) == 1
    asyncio.run(exercise())


def test_competing_publication_after_preflight_is_not_labelled_as_an_unbuilt_candidate(lab, monkeypatch, tmp_path):
    client, db, admin, _, ring = lab
    candidate = package('<template><span>candidate</span></template>')
    original = package()
    validated = api.validate_module_package(original)
    calls = []
    def finish_build(*args, **kwargs):
        result = fake_compiler(calls)(*args, **kwargs)
        # Independent writer wins the uniqueness race after the early read.
        archive = tmp_path/'uploads/modules'/(validated.sha256+'.zip')
        archive.write_bytes(original)
        with Session(db.get_bind()) as writer, writer.begin():
            writer.add(ModulePackage(module_id=validated.manifest.module_id, version=validated.manifest.version,
                                     manifest=validated.manifest.model_dump(mode='json'), sha256=validated.sha256,
                                     size_bytes=len(original), file_path=str(archive), registrations=[]))
        return result
    monkeypatch.setattr(compiled_ui.subprocess, 'run', finish_build)
    response = client.post(route, headers=admin, files=files(candidate))
    assert response.status_code == 409 and len(calls)==1
    winner, = db.scalars(select(ModulePackage)).all()
    assert winner.sha256==validated.sha256 and Path(winner.file_path).read_bytes()==original
    assert not (Path(winner.file_path).parent/(hashlib.sha256(candidate).hexdigest()+'.zip')).exists()
    report = cases.build_cases(ring.snapshot(), {'records':[]}, {'probe_status':'complete'})
    case, = report['cases']
    assert case['operation']=='package.store' and case['evidence']['stage']=='package.catalog_commit'
    from tools.diagnostics import explain
    offline, = explain(report)['cases']
    assert offline['reason']=='package_version_conflict' and offline['summary']==response.json()['detail']
    assert not offline['automatic_replay_allowed'] and 'not built' not in offline['summary']
