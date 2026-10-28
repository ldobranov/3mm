from three_mm_platform_wire import COMPATIBILITY_ACTIONS
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.services.core_components import CoreComponents


@pytest.mark.parametrize("failure", ["construct", "start", "stop"])
def test_optional_failure_never_prevents_other_components_or_cleanup(failure):
    async def scenario():
        calls=[]
        class Resource:
            def start(self):
                calls.append('start')
                if failure=='start': raise OSError('password=must-not-leak')
            def stop(self):
                calls.append('stop')
                if failure=='stop': raise OSError('secret=must-not-leak')
        def factory():
            if failure=='construct': raise ImportError('private-runtime-path')
            return Resource()
        healthy=SimpleNamespace(start=lambda:calls.append('healthy_start'),stop=lambda:calls.append('healthy_stop'))
        components=CoreComponents()
        await components.start('optional',factory)
        await components.start('healthy',lambda:healthy)
        assert components.snapshot()['components']['healthy']['state']=='ready'
        if failure!='stop':
            assert components.snapshot()['components']['optional']['state']=='failed'
        await components.close()
        assert 'healthy_stop' in calls
        assert 'password' not in str(components.snapshot()) and 'private-runtime-path' not in str(components.snapshot())
        if failure!='construct': assert 'stop' in calls
    asyncio.run(scenario())


def test_task_failure_and_iteration_recovery_are_visible_without_ending_core():
    async def scenario():
        components=CoreComponents()
        async def fails(): raise RuntimeError('must-not-leak')
        components.spawn('broken_worker',fails)
        await asyncio.sleep(0)
        assert components.snapshot()['components']['broken_worker']==dict(state='failed',reason='worker_failed')
        components.ready('retrying_worker')
        components.degraded('retrying_worker')
        assert components.snapshot()['components']['retrying_worker']['state']=='degraded'
        components.ready('retrying_worker')
        assert components.snapshot()['components']['retrying_worker']['state']=='ready'
        await components.close()
    asyncio.run(scenario())


def test_async_start_cancellation_cleans_already_started_resources():
    async def scenario():
        calls=[]
        class Pending:
            async def start(self):
                calls.append('started')
                await asyncio.Event().wait()
            async def stop(self): calls.append('stopped')
        components=CoreComponents()
        task=asyncio.create_task(components.start('pending',Pending))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        await components.close()
        assert calls==['started','stopped']
    asyncio.run(scenario())


@pytest.fixture
def core(tmp_path,monkeypatch):
    import backend.main as main
    import backend.database as database
    from backend.db.base import Base
    from backend.db.user import User
    from backend.utils.db_utils import get_db
    from backend.utils import jwt_utils
    from backend.utils.jwt_utils import create_access_token

    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    with sessions() as db:
        admin=User(username='startup-admin',email='admin@example.test',hashed_password='unused',role='admin')
        viewer=User(username='startup-viewer',email='viewer@example.test',hashed_password='unused',role='user')
        db.add_all([admin,viewer]);db.commit()
        admin_id,viewer_id=admin.id,viewer.id
    monkeypatch.setattr(jwt_utils,'SECRET_KEY','test-only-core-startup-key-at-least-32-bytes')
    def databases():
        with sessions() as db: yield db
    overrides=dict(main.app.dependency_overrides)
    main.app.dependency_overrides[get_db]=databases
    main.app.dependency_overrides[database.get_db]=databases
    monkeypatch.setattr(main,'get_db',databases)
    monkeypatch.setattr(main,'init_db',lambda:None)
    settings=main.app_settings.model_copy(deep=True)
    settings.backend.uploads_dir=tmp_path/'uploads'
    settings.applications.runtime_socket=tmp_path/'sdk.sock'
    settings.applications.authority_socket=tmp_path/'authority.sock'
    if hasattr(__import__('os'),'getuid'):
        import pwd,os
        settings.applications.runtime_user=pwd.getpwuid(os.getuid()).pw_name
    monkeypatch.setattr(main,'app_settings',settings)
    class Background:
        fail_start=False
        fail_stop=False
        def __init__(self): self._worker_task=self._monitoring_task=None
        async def start(self):
            if self.fail_start: raise ImportError('password=must-not-leak')
            self._worker_task=asyncio.create_task(asyncio.Event().wait())
            self._monitoring_task=self._worker_task
        async def stop(self):
            if self._worker_task:
                self._worker_task.cancel()
                try: await self._worker_task
                except asyncio.CancelledError: pass
                self._worker_task=self._monitoring_task=None
            if self.fail_stop: raise OSError('secret=must-not-leak')
        start_update_worker=start
        start_monitoring=start
        stop_update_worker=stop
        stop_monitoring=stop
    system=Background()
    monkeypatch.setattr(main,'system_update_check_manager',system)
    state=SimpleNamespace(main=main,settings=settings,sessions=sessions,system=system,
        admin_id=admin_id,admin={'Authorization':'Bearer '+create_access_token(str(admin_id),{'role':'admin'})},
        viewer={'Authorization':'Bearer '+create_access_token(str(viewer_id),{'role':'user'})})
    yield state
    main.app.dependency_overrides.clear();main.app.dependency_overrides.update(overrides)
    engine.dispose()


@pytest.mark.parametrize('component',['runtime_authority','language_extensions','system_updates'])
def test_real_core_http_stays_administrable_when_an_optional_component_fails(core,monkeypatch,component):
    def unavailable(*args): raise ImportError('private-password=must-not-leak')
    if component=='runtime_authority':
        # An occupied path is a real filesystem failure, not a stubbed listener.
        core.settings.applications.authority_socket.mkdir()
    elif component=='language_extensions': monkeypatch.setattr(core.main,'_language_packages',unavailable)
    elif component=='system_updates': core.system.fail_start=True
    with TestClient(core.main.app) as client:
        assert client.get('/health').json()=={'status':'ok'}
        assert client.get('/ready').json()=={'status':'ready'}
        assert client.get('/settings/read').status_code==200
        assert client.get('/api/v1/diagnostics/components').status_code==401
        assert client.get('/api/v1/diagnostics/components',headers=core.viewer).status_code==403
        response=client.get('/api/v1/diagnostics/components',headers=core.admin)
        assert response.status_code==200
        status=response.json()
        assert status['status']=='degraded' and status['components'][component]['state']=='failed'
        assert 'must-not-leak' not in response.text and 'private-password' not in response.text
        assert response.headers['cache-control']=='no-store'
    assert not core.settings.applications.runtime_socket.exists()
    if component=='runtime_authority': assert core.settings.applications.authority_socket.is_dir()


def test_missing_sdk_import_is_optional_and_a_failed_shutdown_still_closes_sockets(core,monkeypatch):
    import builtins
    original=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name=='backend.services.application_platform': raise ModuleNotFoundError('private-runtime-path')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    core.system.fail_stop=True
    with TestClient(core.main.app) as client:
        assert client.get('/ready').status_code==200
        status=client.get('/api/v1/diagnostics/components',headers=core.admin).json()
        assert status['components']['runtime_authority']['reason']=='startup_failed'
        assert 'public_web' not in status['components']
    assert core.main.app.state.core_components.snapshot()['components']['system_updates']['reason']=='shutdown_failed'


@pytest.mark.parametrize('revoked',['blocked','token_version'])
def test_component_status_honors_current_admin_revocation(core,revoked):
    from backend.db.user import User
    with TestClient(core.main.app) as client:
        assert client.get('/api/v1/diagnostics/components',headers=core.admin).status_code==200
        with core.sessions() as db:
            admin=db.get(User,core.admin_id)
            if revoked=='blocked': admin.is_blocked=True
            else: admin.token_version+=1
            db.commit()
        assert client.get('/api/v1/diagnostics/components',headers=core.admin).status_code==401


def test_database_initialization_failure_is_not_reported_as_ready(core,monkeypatch):
    def unavailable(): raise RuntimeError('database unavailable')
    monkeypatch.setattr(core.main,'init_db',unavailable)
    with pytest.raises(RuntimeError,match='database unavailable'):
        with TestClient(core.main.app): pytest.fail('Core must not serve with an uninitialized database')


def test_managed_background_task_failure_is_observed_after_successful_start():
    async def scenario():
        release=asyncio.Event()
        class Managed:
            _worker_task=None
            async def start(self):
                async def work():
                    await release.wait()
                    raise RuntimeError('credential=must-not-leak')
                self._worker_task=asyncio.create_task(work())
            async def stop(self):
                if self._worker_task:
                    self._worker_task.cancel()
                    try: await self._worker_task
                    except (asyncio.CancelledError,RuntimeError): pass
        components=CoreComponents()
        await components.start('managed',Managed,task_attribute='_worker_task')
        assert components.snapshot()['components']['managed']['state']=='ready'
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert components.snapshot()['components']['managed']==dict(state='failed',reason='worker_failed')
        assert 'credential' not in str(components.snapshot())
        await components.close()
    asyncio.run(scenario())


def test_old_enabled_python_and_every_retired_http_entry_stay_inert(core,tmp_path,monkeypatch):
    import sqlalchemy as sa
    marker=tmp_path/'executed'
    directory=tmp_path/'old-extension'
    directory.mkdir()
    (directory/'manifest.json').write_text('{"backend_entry":"danger.py"}')
    (directory/'danger.py').write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit('must never run')")
    with core.sessions() as db:
        evidence=sa.Table('retired_extensions',sa.MetaData(),sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('manifest',sa.JSON()),sa.Column('file_path',sa.String()),sa.Column('is_enabled',sa.Boolean()))
        evidence.create(db.get_bind())
        db.execute(evidence.insert().values(id=1,manifest={'backend_entry':'danger.py'},file_path=str(directory),is_enabled=True));db.commit()
    with TestClient(core.main.app) as client:
        assert client.get('/ready').status_code==200
        for method,path in [('get','/api/extensions'),('get','/api/extensions/public'),
                ('get','/api/extensions/widgets'),('post','/api/extensions/upload'),
                ('patch','/api/extensions/1'),('delete','/api/extensions/1'),
                ('get','/api/marketplace/updates'),('post','/api/marketplace/update/1'),('post','/api/marketplace/rollback/1'),('get','/api/extensions/monitoring/overview'),
                ('post','/api/main-server/schedule-update'),('get','/pages/read'),('get','/api/translations/extensions/1/tables/example'),('get','/api/permissions/entities'),('get','/api/permissions/extension-types'),('get','/api/permissions/my/extensions')]:
            # Removed GETs may match the path of the generic DELETE-by-ID API.
            assert client.request(method,path,headers=core.admin).status_code in (404,405)
        state=client.get('/api/v1/diagnostics/components',headers=core.admin).json()
        assert not {'extension_loader','extension_updates','extension_monitoring','application_jobs'} & state['components'].keys()
    assert not marker.exists()


def test_core_http_remains_available_when_sdk_connections_are_full(core,monkeypatch):
    from contextlib import ExitStack
    import socket
    import time
    from backend.services.application_platform import CoreRuntimeAuthorityServer
    from three_mm_platform_wire import AUTHORITY_CONNECTIONS as MAX_CONNECTIONS
    import os
    server=CoreRuntimeAuthorityServer(core.settings.applications.authority_socket,
        core.settings.applications.key_root,runtime_uid=os.getuid(),group="missing-test-group")
    monkeypatch.setattr(core.main,"_runtime_authority",lambda:server)
    with TestClient(core.main.app) as client, ExitStack() as stack:
        for _ in range(MAX_CONNECTIONS):
            connection=stack.enter_context(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM))
            connection.connect(str(server.socket_path));connection.sendall(b"\0{")
        deadline=time.monotonic()+2
        while server.active_connections < MAX_CONNECTIONS:
            assert time.monotonic() < deadline
            time.sleep(.005)
        assert client.get("/ready").status_code==200
        assert client.get("/settings/read").status_code==200
        status=client.get("/api/v1/diagnostics/components",headers=core.admin).json()
        assert status["components"]["runtime_authority"]["state"]=="ready"
        assert "sdk_platform" not in status["components"]
        assert not core.settings.applications.runtime_socket.exists()
        assert server.active_connections==MAX_CONNECTIONS
    assert server.active_connections==0


def test_production_runtime_factory_refuses_to_share_the_core_os_principal(core):
    import os
    if not hasattr(os,'getuid'):pytest.skip('POSIX principal check')
    with pytest.raises(ValueError,match='distinct OS principals'):core.main._runtime_authority()


def test_startup_prepares_included_routes_without_executing_authority_or_handlers(core):
    from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException

    schemas, authority_calls, effects = [], [], []

    class TrackedValue(int):
        @classmethod
        def __get_pydantic_core_schema__(cls, source, handler):
            schemas.append(True)
            return handler(int)

    def authorize(token: str | None = Header(default=None)):
        authority_calls.append(token)
        if token != "current":
            raise HTTPException(status_code=401)

    router = APIRouter()

    @router.post("/probe")
    def command(value: TrackedValue):
        effects.append(value)
        return {"value": value}

    app = FastAPI(lifespan=core.main.lifespan, dependencies=[Depends(authorize)])
    app.include_router(router)
    before = len(schemas)
    with TestClient(app) as client:
        prepared = len(schemas)
        assert prepared > before
        assert authority_calls == effects == []
        assert client.post("/probe?value=1").status_code == 401
        assert effects == []
        assert client.post("/probe?value=2", headers={"token": "current"}).json() == {"value": 2}
        assert len(schemas) == prepared
        assert authority_calls == [None, "current"] and effects == [2]
