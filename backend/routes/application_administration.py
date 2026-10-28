"""Declared current-administrator module/capability operations. No URL proxy."""
from contextlib import contextmanager
import hashlib
import json
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.device import Device, DeviceCapabilityState, DeviceCommand
from backend.db.module import ModulePackage
from backend.db.module import ApplicationExtensionInstallation
from backend.db.user import User
from backend.services import device_module_management as modules
from backend.services.application_access import resolve_application_principal
from backend.services import application_authority_management as authority
from backend.services.application_authority_management import AuthorityManagementError, _UI_TRUST_SNAPSHOT
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.device_commands import queue_command, DeviceCommandError, require_control_authority
from backend.services.device_command_notifier import device_command_notifier
from backend.services.device_capability_registry import capability_catalog
from backend.services.device_protocol import capability_snapshot
from backend.utils.db_utils import get_db
from three_mm_protocol.node_security import bounded_node_message
from three_mm_protocol.application_resources import ResourceScope, ResourceDiscoveryRequestV1

router = APIRouter()
ROOT = '/{module_id}/ui-host/{entrypoint_id}'


class ResourceInspectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    built_ui_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    scopes: list[ResourceScope] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def bounded_selection(self):
        ResourceDiscoveryRequestV1(scopes=self.scopes)
        return self


@router.post(ROOT+'/resources/inspect')
def resources(module_id: str, entrypoint_id: str, body: ResourceInspectionRequest, response: Response,
        authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    from backend.services.application_resource_discovery import discover_resources
    from three_mm_protocol.application_resources import ResourceDiscoveryRequestV1
    query = ResourceDiscoveryRequestV1(scopes=body.scopes)
    response.headers['Cache-Control'] = 'no-store'
    binding = _binding(entrypoint_id, body.artifact_sha256, body.built_ui_sha256)
    engine = db.get_bind().engine
    with _read(db, module_id, binding, authorization, 'resources.inspect') as current:
        app = current.scalar(select(ApplicationExtensionInstallation).where(ApplicationExtensionInstallation.module_id==module_id))
        identifier, instance = app.id, app.instance_id
    try:
        value = discover_resources(engine, identifier, instance, query.scopes)
    except (ValueError, RuntimeError, OSError, AuthorityManagementError, AuthorityReviewKeyError):
        raise HTTPException(409, 'Current resource observation is unavailable') from None
    with _read(db, module_id, binding, authorization, 'resources.inspect'):
        return value
DEVICE = r'^dev_[0-9a-f]{32}$'

class ActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    _bounded = model_validator(mode='after')(bounded_node_message)
    artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    built_ui_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    device_id: str = Field(pattern=DEVICE)

class ModuleInstall(ActionRequest):
    package_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

class ModuleDisable(ActionRequest):
    module_id: str = Field(pattern=r'^[a-z0-9]+(?:[.-][a-z0-9]+)+$')

class CapabilityInvoke(ActionRequest):
    capability_id: str = Field(min_length=1,max_length=160)
    provider_type: str = Field(min_length=1,max_length=64)
    provider_id: str = Field(min_length=1,max_length=160)
    declaration_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    contract_version: str = Field(pattern=r'^\d+\.\d+$',max_length=20)
    action: str = Field(min_length=1,max_length=100)
    arguments: dict = Field(default_factory=dict)
    ttl_seconds: int = Field(default=15,ge=5,le=30)

class Replayed(Exception):
    def __init__(self, receipt): self.receipt = receipt


def _binding(entrypoint_id, source, build):
    from backend.routes.application_extensions import _administration_binding
    return _administration_binding(entrypoint_id, source, build)


def _device(db, device_id):
    item=db.scalar(select(Device).where(Device.device_id==device_id))
    if item is None: raise HTTPException(404,'Device was not found')
    return item


def _read(db,module_id,binding,authorization,operation):
    from backend.routes.application_extensions import _administration_read
    return _administration_read(db,module_id,binding,authorization,operation)


@router.get(ROOT+'/module-packages')
def packages(module_id:str,entrypoint_id:str,artifact_sha256:str,built_ui_sha256:str,response:Response,
             authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    binding=_binding(entrypoint_id,artifact_sha256,built_ui_sha256)
    with _read(db,module_id,binding,authorization,'modules.list') as current:
        rows=current.scalars(select(ModulePackage).order_by(ModulePackage.module_id,ModulePackage.version))
        return [{'module_id':p.module_id,'version':p.version,'sha256':p.sha256,
                 'name':p.manifest.get('name') or p.module_id}
                for p in rows if 'agent' in p.manifest.get('runtimes',[])][:100]


@router.get(ROOT+'/devices/{device_id}/capabilities')
def capabilities(module_id:str,entrypoint_id:str,device_id:str,artifact_sha256:str,built_ui_sha256:str,response:Response,
                 authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    with _read(db,module_id,_binding(entrypoint_id,artifact_sha256,built_ui_sha256),authorization,'capabilities.list') as current:
        return capability_catalog(current,_device(current,device_id))


@router.get(ROOT+'/devices/{device_id}/capability-state/{capability_id}')
def state(module_id:str,entrypoint_id:str,device_id:str,capability_id:str,artifact_sha256:str,built_ui_sha256:str,response:Response,
          authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    with _read(db,module_id,_binding(entrypoint_id,artifact_sha256,built_ui_sha256),authorization,'capabilities.state') as current:
        device=_device(current,device_id)
        if not any(c.capability_id==capability_id and c.registered for c in capability_catalog(current,device)):
            raise HTTPException(409,'Capability is not currently registered')
        row=current.scalar(select(DeviceCapabilityState).where(DeviceCapabilityState.device_id==device.id,
            DeviceCapabilityState.capability_id==capability_id))
        if row is None: raise HTTPException(404,'Capability has no reported state')
        return capability_snapshot(device,row)


@router.get(ROOT+'/commands/{request_id}')
def command(module_id:str,entrypoint_id:str,request_id:str,artifact_sha256:str,built_ui_sha256:str,response:Response,
            authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    from backend.routes.device_commands import CommandStatusResponse
    response.headers['Cache-Control']='no-store'
    binding=_binding(entrypoint_id,artifact_sha256,built_ui_sha256)
    with _read(db,module_id,binding,authorization,'commands.get') as current:
        principal=resolve_application_principal(authorization,current)
        if len(request_id)!=32 or any(c not in '0123456789abcdef' for c in request_id):
            raise HTTPException(422,'Request identity is invalid')
        try: value=current.info[_UI_TRUST_SNAPSHOT].action_for(current,request_id)
        except AuthorityManagementError: raise HTTPException(404,'Request is not recorded') from None
        data=value['data'];request=data.get('result',{})
        if (data.get('operation')!='ui_administration' or data['actor'][0]!=principal.user_id
                or request.get('entrypoint_id')!=entrypoint_id or request.get('artifact_sha256')!=artifact_sha256 or request.get('built_ui_sha256')!=built_ui_sha256):
            raise HTTPException(403,'Request belongs to another actor or interface')
        row=current.scalar(select(DeviceCommand).where(DeviceCommand.command_id==request['command_id'],
            DeviceCommand.device_id==_device(current,request['device_id']).id))
        if row is None:raise HTTPException(409,'Command receipt is unavailable')
        return {'request_id':request_id,'device_id':request['device_id'],**CommandStatusResponse.model_validate(row,from_attributes=True).model_dump()}


@contextmanager
def _write(db,module_id,entrypoint_id,body,authorization,operation,receipt):
    from backend.routes.application_extensions import _installation, _active_package
    principal=resolve_application_principal(authorization,db)
    if principal.kind!='user' or not principal.is_admin: raise HTTPException(403,'Current administrator access is required')
    installation=_installation(db,module_id);installation_id=installation.id
    if installation.authority_mode=='compatibility':raise HTTPException(403,'Current native UI approval is required')
    manager=authority.configured_manager(db.get_bind().engine)
    request={'entrypoint_id':entrypoint_id,'operation':operation,**body.model_dump()}
    db.rollback()
    token=authorization.split(' ',1)[1].strip()
    try:
        with manager.ui_trust_write(installation_id,body.built_ui_sha256,token,body.request_id,request) as (current,mutation,actor,validated,saved):
            installation=_installation(current,module_id);package=_active_package(current,installation)
            route=next((r for r in validated.application_extension.routes if r.entrypoint_id==entrypoint_id),None)
            if (route is None or route.audience!='administrator' or operation not in route.administration_actions
                    or package.sha256!=body.artifact_sha256 or validated.sha256!=package.sha256):
                raise HTTPException(403,'Administrator action is not declared by this current route')
            if saved:raise Replayed({k:v for k,v in saved.items() if k not in {'replayed','historical'}})
            device=current.scalar(select(Device).where(Device.device_id==body.device_id).with_for_update())
            if device is None:raise HTTPException(404,'Device was not found')
            require_control_authority(current,device)
            receipt['saved']=saved
            yield current,mutation,device
    except (AuthorityManagementError,AuthorityReviewKeyError):
        raise HTTPException(403,'Current administrator UI approval/session is unavailable') from None


def _receipt(command,body,entrypoint_id,receipt):
    receipt['saved'].update(request_id=body.request_id,command_id=command.command_id,status=command.status,
        device_id=body.device_id,entrypoint_id=entrypoint_id,artifact_sha256=body.artifact_sha256,built_ui_sha256=body.built_ui_sha256)


def _module_action(module_id,entrypoint_id,body,authorization,db,operation):
    receipt={}
    principal=resolve_application_principal(authorization,db)
    if principal.kind!='user' or not principal.is_admin:raise HTTPException(403,'Current administrator access is required')
    admin=db.get(User,principal.user_id)
    @contextmanager
    def scope(preflight,device):
        with _write(preflight,module_id,entrypoint_id,body,authorization,operation,receipt) as values:yield values
    def queued(command):_receipt(command,body,entrypoint_id,receipt)
    client_key='ui:'+hashlib.sha256(json.dumps([module_id,entrypoint_id,body.artifact_sha256,body.built_ui_sha256,body.request_id]).encode()).hexdigest()
    try:
        if operation=='modules.install':
            modules.install_module(body.package_sha256,body.device_id,admin,db,client_key,write_scope=scope,on_queued=queued)
        else:
            modules.disable_module(body.module_id,body.device_id,admin,db,client_key,write_scope=scope,on_queued=queued)
        return receipt['saved']
    except Replayed as exc:return exc.receipt
    finally:db.rollback()


@router.post(ROOT+'/modules/install')
def install(module_id:str,entrypoint_id:str,body:ModuleInstall,response:Response,
            authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    return _module_action(module_id,entrypoint_id,body,authorization,db,'modules.install')


@router.post(ROOT+'/modules/disable')
def disable(module_id:str,entrypoint_id:str,body:ModuleDisable,response:Response,
            authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    return _module_action(module_id,entrypoint_id,body,authorization,db,'modules.disable')


@router.post(ROOT+'/capabilities/invoke')
def invoke(module_id:str,entrypoint_id:str,body:CapabilityInvoke,response:Response,
           authorization:str|None=Header(default=None),db:Session=Depends(get_db)):
    response.headers['Cache-Control']='no-store';receipt={}
    try:
        with _write(db,module_id,entrypoint_id,body,authorization,'capabilities.invoke',receipt) as (current,mutation,device):
            offer=next((c for c in capability_catalog(current,device) if c.capability_id==body.capability_id
                and c.provider_type==body.provider_type and c.provider_id==body.provider_id),None)
            if (offer is None or not offer.registered or offer.available is not True
                    or offer.contract_version!=body.contract_version or offer.declaration_digest!=body.declaration_digest):
                raise HTTPException(409,'Capability/provider contract changed or is unavailable')
            payload={'capability_id':body.capability_id,'action':body.action,'arguments':body.arguments,'contract_version':body.contract_version}
            from backend.services.authority_metadata import read_device_control
            payload['provider_binding']={'provider_type':offer.provider_type,'provider_id':offer.provider_id,
                'provider_version':offer.provider_version,'declaration_digest':offer.declaration_digest,
                'control_generation':read_device_control(current,device.id).generation}
            key='ui.capability:'+hashlib.sha256(json.dumps([module_id,body.artifact_sha256,entrypoint_id,body.request_id]).encode()).hexdigest()
            command=queue_command(current,device=device,command_type='capability.invoke',payload=payload,
                idempotency_key=key,ttl_seconds=body.ttl_seconds)
            _receipt(command,body,entrypoint_id,receipt)
            device_pk=device.id
        device_command_notifier.notify(device_pk)
        return receipt['saved']
    except Replayed as exc:return exc.receipt
    except DeviceCommandError as exc:raise HTTPException(409,str(exc)) from exc
    finally:db.rollback()
