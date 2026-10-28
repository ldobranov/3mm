"""Real current-user/native/action gates, command idempotency and status isolation."""
import importlib.util
import os
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from backend.db.device import Device, DeviceCommand, DeviceRuntimeFeatures
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.session import UserSession
from backend.db.user import User
from backend.routes.application_extensions import router
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_ui_authority import ui_app, adopt
from backend.tests.test_application_authority_management import installed as managed_installed
from backend.tests.test_application_authority_subjects import installed as source_subject, source_installed
from backend.utils.db_utils import get_db

pytestmark=[pytest.mark.skipif(os.name!='posix',reason='Real native approval keys'),
    pytest.mark.parametrize('ui_app',['administration_actions'],indirect=True)]

@pytest.fixture
def actions(ui_app):
    s=ui_app
    s.native_proof=adopt(s,scopes=[])
    spec=importlib.util.spec_from_file_location('probe_builder',Path('modules/agent-probe/build_package.py'))
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    blob=builder.build_package();package=validate_module_package(blob)
    archive=s.root/'modules'/(package.sha256+'.zip');archive.write_bytes(blob)
    with Session(s.engine) as db,db.begin():
        db.add(ModulePackage(module_id=package.manifest.module_id,version=package.manifest.version,
            sha256=package.sha256,size_bytes=len(blob),file_path=str(archive),manifest=package.manifest.model_dump(mode='json'),registrations=[]))
        features=db.get(DeviceRuntimeFeatures,1)
        features.declaration={**features.declaration,'command_types':['capability.invoke','application.capability.invoke','module.install','module.disable']}
        s.device_id=db.get(Device,1).device_id
    s.body={'artifact_sha256':s.validated.sha256,'built_ui_sha256':s.build.built_ui_sha256,
        'request_id':'d'*32,'device_id':s.device_id,'package_sha256':package.sha256}
    s.params={k:s.body[k] for k in ('artifact_sha256','built_ui_sha256')}
    s.auth={'Authorization':'Bearer '+s.token}
    s.base=f'/api/v1/application-extensions/{s.validated.manifest.module_id}/ui-host/operations'
    app=FastAPI();app.include_router(router)
    def session():
        with Session(s.engine) as db:yield db
    app.dependency_overrides[get_db]=session
    with TestClient(app) as client:
        s.client=client;yield s


def install(s,body=None,auth=None):
    return s.client.post(s.base+'/modules/install',json=body or s.body,headers=s.auth if auth is None else auth)


def test_install_once_status_and_changed_content_rejection(actions):
    s=actions
    catalog=s.client.get(s.base+'/module-packages',params=s.params,headers=s.auth)
    assert catalog.status_code==200 and [p['module_id'] for p in catalog.json()]==['org.3mm.agent-probe']
    first=install(s);assert first.status_code==200,first.text
    second=install(s);assert second.status_code==200 and first.json()['command_id']==second.json()['command_id']
    status=s.client.get(s.base+'/commands/'+s.body['request_id'],params=s.params,headers=s.auth)
    assert status.status_code==200 and status.json()['status']=='queued'
    assert 'package_base64' not in status.text
    assert s.client.post(s.base+'/modules/disable',json={k:v for k,v in {**s.body,'module_id':'org.3mm.agent-probe'}.items() if k!='package_sha256'},headers=s.auth).status_code==403
    with Session(s.engine) as db:assert len(db.scalars(select(DeviceCommand)).all())==1


@pytest.mark.parametrize('fault',['anonymous','user','demoted','revoked_session','disabled','source','build','route','device_revoked'])
def test_denial_never_creates_a_command(actions,fault):
    s=actions;body=dict(s.body);auth=s.auth;base=s.base
    if fault=='anonymous':auth={}
    if fault=='user':auth={'Authorization':'Bearer '+s.user_token}
    if fault=='source':body['artifact_sha256']='f'*64
    if fault=='build':body['built_ui_sha256']='f'*64
    if fault=='route':base=base.replace('/operations','/registration')
    with s.engine.begin() as db:
        if fault=='demoted':db.execute(update(User).where(User.id==1).values(role='user'))
        if fault=='revoked_session':db.execute(update(UserSession).where(UserSession.id==1).values(is_active=False))
        if fault=='disabled':db.execute(update(Installation).values(enabled=False,status='disabled'))
        if fault=='device_revoked':
            from datetime import UTC,datetime
            db.execute(update(Device).values(revoked_at=datetime.now(UTC)))
    response=s.client.post(base+'/modules/install',json=body,headers=auth)
    assert response.status_code in (401,403,409),response.text
    with Session(s.engine) as db:assert db.scalar(select(DeviceCommand)) is None


def test_preflight_does_not_cache_the_session_or_allow_a_foreign_receipt(actions,monkeypatch):
    s=actions
    original=s.manager.ui_trust_write
    @contextmanager
    def revoked(*args,**kwargs):
        with s.engine.begin() as db:db.execute(update(UserSession).where(UserSession.id==1).values(is_active=False))
        with original(*args,**kwargs) as values:yield values
    monkeypatch.setattr(s.manager,'ui_trust_write',revoked)
    assert install(s).status_code==403
    with Session(s.engine) as db:assert db.scalar(select(DeviceCommand)) is None


def test_command_receipts_are_bound_to_actor_route_and_native_approval(actions):
    s=actions;assert install(s).status_code==200
    with s.engine.begin() as db:db.execute(update(User).where(User.id==2).values(role='admin'))
    response=s.client.get(s.base+'/commands/'+s.body['request_id'],params=s.params,headers={'Authorization':'Bearer '+s.user_token})
    assert response.status_code==403
    s.manager.revoke_native_review(1,actor_token=s.token,request_id='e'*32,
        native_review_id=s.native_proof['native_review_id'],expected_revision=s.native_proof['native_revision'])
    assert s.client.get(s.base+'/commands/'+s.body['request_id'],params=s.params,headers=s.auth).status_code in (403,409)


def test_versioned_invocation_pins_provider_contract_and_does_not_repeat(actions):
    s=actions
    offers=s.client.get(s.base+'/devices/'+s.device_id+'/capabilities',params=s.params,headers=s.auth)
    assert offers.status_code==200
    offer=next(c for c in offers.json() if c['registered'])
    action,schema=next(iter(offer['contract']['actions'].items()))
    arguments={k:(v['enum'][0] if 'enum' in v else v.get('minimum',50)) for k,v in schema['arguments_schema']['properties'].items()}
    body={k:v for k,v in s.body.items() if k!='package_sha256'}
    body.update(capability_id=offer['capability_id'],provider_type=offer['provider_type'],provider_id=offer['provider_id'],
        declaration_digest=offer['declaration_digest'],contract_version=offer['contract_version'],action=action,arguments=arguments)
    wrong={**body,'declaration_digest':'f'*64}
    assert s.client.post(s.base+'/capabilities/invoke',json=wrong,headers=s.auth).status_code==409
    response=s.client.post(s.base+'/capabilities/invoke',json=body,headers=s.auth)
    assert response.status_code==200,response.text
    again=s.client.post(s.base+'/capabilities/invoke',json=body,headers=s.auth)
    assert again.status_code==200 and again.json()['command_id']==response.json()['command_id']
    with Session(s.engine) as db:assert len(db.scalars(select(DeviceCommand)).all())==1


def test_actual_mock_agent_install_switch_on_off_and_disable(actions,tmp_path):
    import base64
    from datetime import UTC,datetime
    from sqlalchemy import delete
    from agent.hardware import MockDigitalGpioDriver
    from agent.module_runtime import AgentModuleRuntime
    from agent.modules.gpio import GPIO_ENTRYPOINT,gpio_runtime_handler
    from backend.db.device import DeviceCapabilityProvider,DeviceCapabilityHealth
    from backend.services.device_commands import deliver_next_command,record_command_result
    from backend.services.device_capability_registry import capability_catalog,report_availability
    from backend.services.device_protocol import DeviceOperations
    from three_mm_protocol import AgentCommandResult,CapabilityStateReportV1
    from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1
    s=actions
    spec=importlib.util.spec_from_file_location('real_output_builder',Path('modules/digital-output/build_package.py'))
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    blob=builder.build_package(versioned=True);package=validate_module_package(blob)
    archive=s.root/'modules'/(package.sha256+'.zip');archive.write_bytes(blob)
    with Session(s.engine) as db,db.begin():
        db.execute(delete(DeviceCapabilityHealth));db.execute(delete(DeviceCapabilityProvider))
        db.add(ModulePackage(module_id=package.manifest.module_id,version=package.manifest.version,sha256=package.sha256,
            size_bytes=len(blob),file_path=str(archive),manifest=package.manifest.model_dump(mode='json'),
            registrations=[r.model_dump(mode='json') for r in package.manifest.registrations]))
    gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path/'actual-agent',architecture='x86_64',runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio)})
    def consume():
        with Session(s.engine) as db:
            device=db.get(Device,1)
            command=deliver_next_command(db,device=device)
            assert command is not None
            payload=command.payload
            if command.command_type=='module.install':
                runtime.install(base64.b64decode(payload['package_base64']),expected_sha256=payload['sha256']);output={}
            elif command.command_type=='module.disable':
                runtime.disable(payload['module_id']);output={}
            else:
                output=runtime.invoke(payload['capability_id'],payload['action'],payload['arguments'],
                    contract_version=payload['contract_version'],contract_digest=payload['contract_digest'])
            record_command_result(db,device=device,result=AgentCommandResult(command_id=command.command_id,device_id=s.device_id,
                status='succeeded',completed_at=datetime.now(UTC),output=output))
        with Session(s.engine) as db:
            device=db.get(Device,1)
            offers=capability_catalog(db,device)
            for offer in offers:
                if offer.provider_id!=package.manifest.module_id:continue
                report_availability(db,device,CapabilityAvailabilityReportV1(device_id=s.device_id,provider_type=offer.provider_type,
                    provider_id=offer.provider_id,provider_version=offer.provider_version,declaration_digest=offer.declaration_digest,
                    observed_at=datetime.now(UTC),capabilities=[{'capability_id':offer.capability_id,'healthy':True}]))
            db.commit()
            for capability,values in runtime.capability_states().items():
                DeviceOperations(db,device).capability_state(CapabilityStateReportV1(device_id=s.device_id,capability_id=capability,
                    values=values,observed_at=datetime.now(UTC)))
    try:
        body={**s.body,'package_sha256':package.sha256}
        response=install(s,body);assert response.status_code==200,response.text
        assert response.json()['status']=='queued'
        consume();assert gpio.output('gpio.output.1').read() is False
        assert s.client.get(s.base+'/commands/'+body['request_id'],params=s.params,headers=s.auth).json()['status']=='succeeded'
        for value,request in ((True,'1'*32),(False,'2'*32)):
            offer=next(c for c in s.client.get(s.base+'/devices/'+s.device_id+'/capabilities',params=s.params,headers=s.auth).json() if c['registered'])
            invocation={k:v for k,v in s.body.items() if k!='package_sha256'}
            invocation.update(request_id=request,capability_id=offer['capability_id'],provider_type=offer['provider_type'],provider_id=offer['provider_id'],
                declaration_digest=offer['declaration_digest'],contract_version=offer['contract_version'],action='set_output',arguments={'channel':'gpio.output.1','value':value})
            response=s.client.post(s.base+'/capabilities/invoke',json=invocation,headers=s.auth)
            assert response.status_code==200,response.text
            consume();assert gpio.output('gpio.output.1').read() is value
            state=s.client.get(s.base+'/devices/'+s.device_id+'/capability-state/gpio.digital.control',params=s.params,headers=s.auth)
            assert state.json()['values']['gpio.output.1'] is value
            result=s.client.get(s.base+'/commands/'+request,params=s.params,headers=s.auth)
            assert result.json()['status']=='succeeded' and result.json()['result']['outputs']['gpio.output.1'] is value
        disable={k:v for k,v in s.body.items() if k!='package_sha256'}
        disable.update(request_id='3'*32,module_id=package.manifest.module_id)
        assert s.client.post(s.base+'/modules/disable',json=disable,headers=s.auth).status_code==200
        consume();assert runtime.state(package.manifest.module_id)['enabled'] is False
    finally:runtime.close()


def test_provider_episode_change_before_dispatch_never_moves_the_command(actions):
    from backend.db.device import DevicePlatformState
    from backend.services.device_commands import deliver_next_command
    s=actions
    offer=next(c for c in s.client.get(s.base+'/devices/'+s.device_id+'/capabilities',params=s.params,headers=s.auth).json() if c['registered'])
    action,schema=next(iter(offer['contract']['actions'].items()))
    arguments={k:(v['enum'][0] if 'enum' in v else v.get('minimum',50)) for k,v in schema['arguments_schema']['properties'].items()}
    body={k:v for k,v in s.body.items() if k!='package_sha256'}
    body.update(capability_id=offer['capability_id'],provider_type=offer['provider_type'],provider_id=offer['provider_id'],
        declaration_digest=offer['declaration_digest'],contract_version=offer['contract_version'],action=action,arguments=arguments)
    assert s.client.post(s.base+'/capabilities/invoke',json=body,headers=s.auth).status_code==200
    with s.engine.begin() as db:db.execute(update(DevicePlatformState).values(control_generation='f'*32))
    with Session(s.engine) as db:
        assert deliver_next_command(db,device=db.get(Device,1)) is None
        command=db.scalar(select(DeviceCommand))
        assert command.status=='failed' and command.delivery_attempts==0
        assert command.result=={'execution_state':'not_dispatched'}
