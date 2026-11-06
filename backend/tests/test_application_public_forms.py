"""CAP10: exact package review, real public HTTP and signed service transport."""
from contextlib import closing, contextmanager, ExitStack
from dataclasses import asdict
from http.cookiejar import CookieJar
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
from threading import Thread
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from backend import database
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationRetainedData, ModulePackage
from backend.services import application_public_web_transport as transport
from backend.services import public_form_guests
from backend.services.application_extensions import ApplicationGatewayError, prepare_application_invocation
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_application_authority_management import installed, source_installed, source_subject, identity
from backend.tests.test_application_consent import allow, preview
from backend.version import core_version
from three_mm_runtime.application_activation import (
    activate_application_package, application_instance_id, uninstall_application_instance,
)
from three_mm_platform_runtime.public_web import PublicWebRuntime
from three_mm_public_web.server import create_server_from_socket
from three_mm_public_web.webhook_pilot import WebhookPilotClient
from tools.build_public_form_reference import build_package, MODULE


SOURCE = Path(__file__).resolve().parents[2]
LINUX_LAB = pytest.mark.skipif(sys.platform != 'linux' or getattr(os, 'geteuid', lambda: 0)() == 0,
                              reason='Non-root Linux SCM_RIGHTS + protected review-key laboratory')


@contextmanager
def public_surface(base, keys, *, guest_forms=False, webhook_pilot=None):
    from backend.services.application_platform import CoreRuntimeAuthorityServer

    with ExitStack() as cleanup:
        uid = os.geteuid()
        gate = CoreRuntimeAuthorityServer(base/'authority.sock', keys, runtime_uid=uid)
        gate.start(); cleanup.callback(gate.stop)
        runtime = PublicWebRuntime(base/'public.sock', base/'authority.sock', core_uid=uid)
        runtime.start()
        worker = Thread(target=runtime.serve_forever, daemon=True)
        worker.start()
        cleanup.callback(worker.join, 3); cleanup.callback(runtime.close)
        listener = cleanup.enter_context(socket.socket())
        listener.bind(('127.0.0.1', 0)); listener.listen()
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        server = create_server_from_socket(base/'public.sock', listener, form_origin=origin,
                                           guest_forms=guest_forms, webhook_pilot=webhook_pilot)
        http = Thread(target=server.serve_forever, daemon=True)
        http.start()
        cleanup.callback(server.server_close); cleanup.callback(http.join, 3); cleanup.callback(server.shutdown)
        yield origin


def launch_host(instance_id, root, keys, log):
    return subprocess.Popen([sys.executable, '-c', 'from three_mm_runtime.application_host import serve; '
        'from pathlib import Path; import sys; serve(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))',
        instance_id, str(root), str(keys)], cwd=SOURCE, stdout=log, stderr=subprocess.STDOUT)


def stop_host(child):
    child.terminate()
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        child.kill(); child.wait(timeout=3)


def change_package(document, change):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(build_package())) as source, zipfile.ZipFile(output, 'w') as target:
        for name in source.namelist():
            contents = source.read(name)
            if name == document:
                value = json.loads(contents)
                change(value)
                contents = json.dumps(value).encode()
            target.writestr(name, contents)
    return output.getvalue()


@pytest.mark.parametrize('document,change,reason', [
    ('application-extension.json', lambda d: d['public_http_routes'][0].update(path='/api/v1/test'), 'non-administrative'),
    ('application-extension.json', lambda d: d['public_http_routes'][0].update(path='/demo/{name}'), 'literal'),
    ('application-extension.json', lambda d: d['public_http_routes'][0].update(form_operation_id='show_form'), 'anonymous command'),
    ('application-extension.json', lambda d: d['operations'][2]['audiences'].append('administrator'), 'anonymous command'),
    ('application-extension.json', lambda d: d['operations'][2]['input_schema']['properties']['choice'].update(maxLength=513), 'bounded single-line'),
    ('application-extension.json', lambda d: d['operations'][2]['input_schema'].update(required=[]), 'all fields required'),
    ('application-extension.json', lambda d: d['public_http_routes'][0].update(guest_session=True), 'GET/POST HTML form'),
    ('manifest.json', lambda d: d['permissions'].append('hardware.gpio'), 'platform resources'),
])
def test_package_refuses_wider_form_profiles(document, change, reason):
    with pytest.raises(ModulePackageError, match=reason):
        validate_module_package(change_package(document, change))


@pytest.fixture
def form_stack(installed, monkeypatch, request):
    s = installed
    Base.metadata.create_all(s.engine)
    s.manager.core_version = core_version()
    profile = getattr(request, 'param', None)
    build = lambda: build_package(guest=True) if profile in {'guest', 'guest-disabled'} else build_package()
    blob = build()
    assert build() == blob
    package = validate_module_package(blob)
    definition = package.application_extension
    archive = s.root / 'modules' / (package.sha256 + '.zip')
    archive.write_bytes(blob)
    monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=s.engine))
    with tempfile.TemporaryDirectory(prefix='cap10-', dir='/tmp') as directory, ExitStack() as cleanup:
        base = Path(directory)
        instance_id = 'a'*24
        instance = base / instance_id
        (instance / 'run').mkdir(parents=True)
        release = instance / 'releases' / package.sha256
        release.mkdir(parents=True)
        keys = base / 'keys'; keys.mkdir()
        (keys / (instance_id+'.key')).write_bytes(b'f'*32)
        wheel = Path(definition.service.artifact).name
        with zipfile.ZipFile(archive) as zipped:
            (release / wheel).write_bytes(zipped.read(definition.service.artifact))
        (instance/'active.json').write_text(json.dumps(dict(instance_id=instance_id, module_id=definition.module_id,
            version=definition.version, sha256=package.sha256, wheel=wheel, entrypoint=definition.service.entrypoint,
            storage=definition.storage.model_dump(mode='json'), configuration={},
            operations=[op.model_dump(mode='json') for op in definition.operations])))
        socket_path = instance/'run/service.sock'
        with s.engine.begin() as db:
            db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(module_id=definition.module_id,
                version=definition.version, manifest=package.manifest.model_dump(mode='json'),
                sha256=package.sha256, size_bytes=len(blob), file_path=str(archive)))
            db.execute(update(Installation).where(Installation.id == 1).values(module_id=definition.module_id,
                active_version=definition.version, configuration={}, socket_path=str(socket_path)))
        # This owned child executes the exact packaged wheel and native SDK host.
        with (base/'host.log').open('w+') as log:
            child = launch_host(instance_id, base, keys, log)
            cleanup.callback(stop_host, child)
            deadline = time.monotonic()+8
            while not socket_path.exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    pytest.fail('Packaged form host not ready: '+log.read()[-3000:])
                time.sleep(.02)

            pilot = WebhookPilotClient('/webhooks/pilot', base/'unavailable.sock') if profile == 'webhook-neighbor' else None
            s.form_url = cleanup.enter_context(public_surface(base, keys, guest_forms=profile == 'guest', webhook_pilot=pilot))
            s.form_db = instance/'data/state.sqlite3'
            s.form_keys = keys
            yield s


def _http(s, *, path='/demo-request', fields=None, headers=None, open_request=urlopen):
    headers = (headers if headers is not None else
               {'Cookie': 'not-forwarded=yes', 'Authorization': 'Bearer not-forwarded'})
    request = Request(s.form_url + path, data=urlencode(fields).encode() if fields is not None else None,
        headers={'Origin': s.form_url,
                 **({'Content-Type': 'application/x-www-form-urlencoded'} if fields is not None else {}), **headers})
    try:
        response = open_request(request, timeout=7)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read().decode()


def _saved(s):
    with closing(sqlite3.connect(s.form_db)) as connection:
        return connection.execute('SELECT request_id, choice FROM demo_submission ORDER BY rowid').fetchall()


def guest_payload(page, choice='afternoon'):
    return {**dict(re.findall(r'name="(_request_id|_guest_id)" value="([0-9a-f]{32})"', page)), 'choice': choice}


@LINUX_LAB
@pytest.mark.parametrize('form_stack', ['guest-disabled'], indirect=True)
def test_guest_requires_listener_opt_in(form_stack):
    s = form_stack
    assert allow(s, preview(s))['effective'] is True
    status, headers, _ = _http(s, path='/demo-guest')
    assert status == 403 and 'Set-Cookie' not in headers


@LINUX_LAB
@pytest.mark.parametrize('form_stack', ['guest'], indirect=True)
def test_guest_draft_is_private_bounded_and_never_resumed_after_expiry_or_revoke(form_stack, monkeypatch):
    s = form_stack
    path = '/demo-guest'
    first, second = (build_opener(HTTPCookieProcessor(CookieJar())) for _ in range(2))

    def get(browser):
        return _http(s, path=path, headers={}, open_request=browser.open)

    def submit(browser, fields, **headers):
        return _http(s, path=path, fields=fields, headers=headers, open_request=browser.open)[0]

    def records():
        with closing(sqlite3.connect(s.form_db)) as connection:
            return connection.execute('SELECT guest_id, request_id, choice FROM guest_draft').fetchall()

    status, headers, _ = get(first)
    assert status == 503 and 'Set-Cookie' not in headers
    assert allow(s, preview(s))['effective'] is True
    for metadata in ({'Sec-Fetch-Site': 'cross-site'}, {'Host': 'wrong.example'}, {'Origin': 'https://wrong.example'}):
        status, headers, _ = _http(s, path=path, headers=metadata)
        assert status == 403 and 'Set-Cookie' not in headers
    status, headers, page = get(first)
    cookie = headers['Set-Cookie']
    pair, *_ = cookie.split(';')
    name, token = pair.split('=', 1)
    assert status == 200 and headers['Cache-Control'] == 'no-store' and 'No saved draft.' in page
    assert token not in page and 'HttpOnly' in cookie and 'SameSite=Strict' in cookie
    draft = guest_payload(page)
    assert set(draft) == {'_guest_id', '_request_id', 'choice'}
    assert _http(s, path=path, fields=draft, headers={})[0] == 403
    assert submit(first, draft, Origin='https://wrong.example') == 403
    assert submit(first, draft, Cookie=f'{name}={token[:-1]}{"0" if token[-1] != "0" else "1"}') == 403
    assert submit(first, {**draft, '_guest_id': 'f'*32}) == 403
    assert records() == []
    assert submit(first, draft) == 200
    assert submit(first, draft) == 200
    assert records() == [(draft['_guest_id'], draft['_request_id'], 'afternoon')]
    status, headers, page = get(first)
    assert status == 200 and 'Saved draft: Afternoon' in page and 'Set-Cookie' not in headers
    assert guest_payload(page)['_guest_id'] == draft['_guest_id']
    status, headers, page = get(second)
    assert status == 200 and 'No saved draft.' in page and 'Set-Cookie' in headers
    assert guest_payload(page)['_guest_id'] != draft['_guest_id'] and submit(second, draft) == 403

    with monkeypatch.context() as clock:
        clock.setattr(public_form_guests, 'time', SimpleNamespace(time=lambda: int(token.split('.')[1])))
        assert submit(first, draft) == 403
    revision = s.manager.inspect(1)['grant_record_revision']
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=revision)
    assert get(first)[0] == 503 and submit(first, draft) == 503
    assert allow(s, preview(s))['effective'] is True
    assert submit(first, draft) == 403
    status, headers, page = get(first)
    assert status == 200 and 'No saved draft.' in page and 'Set-Cookie' in headers
    assert guest_payload(page)['_guest_id'] != draft['_guest_id']
    assert records() == [(draft['_guest_id'], draft['_request_id'], 'afternoon')]


@LINUX_LAB
def test_real_form_review_submit_dedupe_and_revocation(form_stack, monkeypatch):
    s = form_stack
    rejected = {'_request_id': 'b'*32, 'choice': 'morning'}
    assert _http(s)[0] == 503 and _http(s, fields=rejected)[0] == 503
    assert _saved(s) == []  # Compatibility never authorizes the new route.

    reviewed = preview(s)
    assert reviewed['selected_scopes'] == []
    assert allow(s, reviewed)['effective'] is True
    status, headers, page = _http(s)
    assert status == 200 and headers['Cache-Control'] == 'no-store'
    key = re.search(r'name="_request_id" value="([0-9a-f]{32})"', page)[1]
    payload = {'_request_id': key, 'choice': 'morning'}
    assert _http(s, path='/api/v1/users', fields=payload)[0] == 404
    assert _http(s, fields={**payload, 'choice': 'bad'})[0] == 400
    assert _http(s, fields={**payload, 'extra': 'field'})[0] == 400
    assert _saved(s) == []
    with Session(s.engine) as db, pytest.raises(ApplicationGatewayError, match='dedicated ingress'):
        prepare_application_invocation(db.get(Installation, 1), db.get(ModulePackage, 1),
            ApplicationRuntimeSettings(key_root=s.form_keys), 'submit_form', {'choice': 'morning'},
            {'audience': 'public', 'correlation_id': 'direct', 'idempotency_key': key}, required_audience='public')
    for _ in range(2):
        status, headers, message = _http(s, fields=payload)
        assert (status, message) == (200, 'Form received.\n') and headers['Cache-Control'] == 'no-store'
    assert _http(s, fields={**payload, 'choice': 'afternoon'})[0] == 400
    assert _saved(s) == [(key, 'morning')]

    # The reference's storage cap refuses new records without evicting receipts.
    with closing(sqlite3.connect(s.form_db)) as connection, connection:
        connection.executemany('INSERT INTO demo_submission VALUES (?, ?)',
                               ((f'{index:032x}', 'morning') for index in range(1023)))
    assert _http(s, fields=rejected)[0] == 429
    assert _http(s, fields=payload)[0] == 200
    assert len(_saved(s)) == 1024
    with closing(sqlite3.connect(s.form_db)) as connection, connection:
        connection.execute('DELETE FROM demo_submission WHERE request_id <> ?', (key,))

    original = transport.finish_public_http
    revision = s.manager.inspect(1)['grant_record_revision']
    def revoke_before_result(*args, **kwargs):
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=revision)
        return original(*args, **kwargs)
    monkeypatch.setattr(transport, 'finish_public_http', revoke_before_result)
    late = {'_request_id': 'c'*32, 'choice': 'afternoon'}
    status, _, message = _http(s, fields=late)
    assert status == 503 and 'not confirmed' in message  # Committed, but no longer confirmable.
    monkeypatch.setattr(transport, 'finish_public_http', original)
    assert _http(s)[0] == 503 and _http(s, fields=rejected)[0] == 503
    assert _saved(s) == [(key, 'morning'), ('c'*32, 'afternoon')]


@LINUX_LAB
@pytest.mark.parametrize('form_stack', ['webhook-neighbor'], indirect=True)
def test_real_form_is_independent_of_a_stopped_webhook_pilot(form_stack):
    s = form_stack
    assert allow(s, preview(s))['effective'] is True
    webhook = Request(s.form_url + '/webhooks/pilot', data=b'synthetic', headers={
        'Content-Type': 'application/octet-stream', 'X-3mm-Webhook-Id': 'test',
        'X-3mm-Webhook-Timestamp': str(int(time.time())), 'X-3mm-Webhook-Signature': 'v1=' + '0' * 64,
    })
    with pytest.raises(HTTPError) as unavailable:
        urlopen(webhook, timeout=5)
    with unavailable.value as response:
        assert (response.code, json.load(response)) == (503, {'status': 'refused'})
    status, _, page = _http(s)
    assert status == 200
    request_id = re.search(r'name="_request_id" value="([0-9a-f]{32})"', page)[1]
    assert _http(s, fields={'_request_id': request_id, 'choice': 'morning'})[0] == 200
    assert _saved(s) == [(request_id, 'morning')]


@LINUX_LAB
def test_form_lifecycle_uses_admin_routes_and_preserves_data(installed, monkeypatch):
    """Only the privileged IPC and systemd boundaries are doubled."""
    from backend.routes import application_authority, application_extensions, modules
    from backend.utils.db_utils import get_db

    s = installed
    Base.metadata.create_all(s.engine)
    s.manager.core_version = core_version()
    sessions = sessionmaker(bind=s.engine)
    monkeypatch.setattr(database, 'SessionLocal', sessions)
    blob = build_package()
    sha256 = validate_module_package(blob).sha256
    instance_id = application_instance_id(MODULE)
    denied_payload = {'_request_id': 'f'*32, 'choice': 'morning'}
    api = FastAPI()
    for router in (modules.router, application_extensions.router, application_authority.router):
        api.include_router(router)

    def session_dependency():
        with sessions() as session:
            yield session

    api.dependency_overrides[get_db] = session_dependency
    admin = {'Authorization': 'Bearer ' + s.token}
    user = {'Authorization': 'Bearer ' + s.user_token}
    prefix = '/api/v1/application-extensions'
    activate_url = f'{prefix}/packages/{sha256}/activate'
    app_url = f'{prefix}/{MODULE}'
    access = app_url + '/authority/consent'

    with tempfile.TemporaryDirectory(prefix='cap10-life-', dir='/tmp') as directory, ExitStack() as cleanup:
        base = Path(directory)
        root, keys = base/'apps', base/'keys'
        settings = SimpleNamespace(backend=SimpleNamespace(uploads_dir=s.root),
                                   applications=ApplicationRuntimeSettings(helper_socket=base/'unused.sock'))
        monkeypatch.setattr(modules, 'get_settings', lambda: settings)
        monkeypatch.setattr(application_extensions, 'get_settings', lambda: settings)
        s.form_url = cleanup.enter_context(public_surface(base, keys))
        s.form_db = root/instance_id/'data/state.sqlite3'
        log = cleanup.enter_context((base/'host.log').open('w+'))

        class Supervisor:
            process = None

            def is_enabled(self, instance):
                assert instance == instance_id
                return self.process is not None and self.process.poll() is None

            def restart(self, instance):
                self.stop(instance)
                self.process = launch_host(instance, root, keys, log)

            def stop(self, instance):
                assert instance == instance_id
                if self.process is not None:
                    stop_host(self.process)
                    self.process = None

        supervisor = Supervisor()
        cleanup.callback(supervisor.stop, instance_id)

        def activate(_helper, candidate, actor, configuration, _ticket):
            assert candidate == sha256 and actor == 1
            package = s.root/'modules'/f'{candidate}.zip'
            result = asdict(activate_application_package(package, candidate, configuration=configuration,
                root=root, key_root=keys, supervisor=supervisor))
            return {**result, 'socket_path': str(result['socket_path'])}

        def disable(_helper, instance, actor, _ticket):
            assert actor == 1
            supervisor.stop(instance)

        def uninstall(_helper, instance, actor, _ticket):
            assert instance == instance_id and actor == 1
            uninstall_application_instance(instance, root=root, key_root=keys, supervisor=supervisor)

        helper = application_extensions.UpdateHelperClient
        monkeypatch.setattr(helper, 'activate_application_extension', activate)
        monkeypatch.setattr(helper, 'disable_application_extension', disable)
        monkeypatch.setattr(helper, 'uninstall_application_extension', uninstall)

        with TestClient(api) as client:
            def admin_post(url, body=None, **kwargs):
                response = client.post(url, headers=admin, json=body, **kwargs)
                assert response.status_code == 200, response.text
                return response.json()

            package_path = '/api/v1/modules/packages'
            files = {'package': ('public-form.zip', blob, 'application/zip')}
            assert client.post(package_path, headers=user, files=files).status_code == 403
            assert admin_post(package_path, files=files)['sha256'] == sha256
            assert _http(s)[0] == 404 and not supervisor.is_enabled(instance_id)

            assert admin_post(activate_url)['status'] == 'active'
            assert supervisor.is_enabled(instance_id) and _saved(s) == []
            assert _http(s)[0] == 503 and _http(s, fields=denied_payload)[0] == 503
            assert client.post(access+'/preview', headers=user, json={'request_id': identity()}).status_code == 403
            review = admin_post(access+'/preview', {'request_id': identity()})
            assert review['selected_scopes'] == [] and not review['access_saved']
            assert _http(s, fields=denied_payload)[0] == 503 and _saved(s) == []
            saved = admin_post(access+'/allow', {'request_id': identity(), 'preview_id': review['preview_id'],
                'expected_revision': review['revision'], 'fingerprint': review['fingerprint'],
                'scopes': [], 'user_permissions': [], 'accept_native_code': True})
            assert saved['effective'] is True
            status, _, page = _http(s)
            assert status == 200
            key = re.search(r'name="_request_id" value="([0-9a-f]{32})"', page)[1]
            submission = {'_request_id': key, 'choice': 'afternoon'}
            assert _http(s, fields=submission)[0] == 200

            assert admin_post(app_url+'/disable')['status'] == 'disabled'
            assert not supervisor.is_enabled(instance_id)
            assert _http(s)[0] == 404 and _http(s, fields=denied_payload)[0] == 404
            assert _saved(s) == [(key, 'afternoon')]
            assert admin_post(activate_url)['status'] == 'active'
            assert _http(s, fields=submission)[0] == 200 and _saved(s) == [(key, 'afternoon')]

            removed = client.delete(app_url, headers=admin)
            assert removed.status_code == 200 and removed.json()['data_preserved'] is True
            assert _http(s)[0] == 404 and _http(s, fields=denied_payload)[0] == 404
            assert not supervisor.is_enabled(instance_id) and not (keys/f'{instance_id}.key').exists()
            assert _saved(s) == [(key, 'afternoon')]
            with sessions() as session:
                assert session.query(Installation).filter_by(module_id=MODULE).count() == 0
                assert session.get(ApplicationRetainedData, MODULE).instance_id == instance_id
