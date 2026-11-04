"""Admin-only local Agent / exact application-host web controls."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.db.user import User
from backend.db.device import Device, DeviceCommand
from backend.services.component_updates import (
    ComponentKind, ComponentUpdateStatus, ComponentPrepareRequest, ComponentSwitchRequest,
    ComponentApplyRequest, RuntimeAccepted,
)
from backend.services.update_policy import UpdatePolicyError, ensure_apply_is_allowed
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError, ComponentUpdateNotAccepted
from three_mm_runtime.component_updates import validate_target, confirmation

router = APIRouter(prefix='/components')


def target(component, target_id, db):
    try: validate_target(component, target_id)
    except ValueError: raise HTTPException(422, 'Invalid local component target') from None
    if component == 'application_host' and db.scalar(select(ApplicationExtensionInstallation.id).where(
            ApplicationExtensionInstallation.instance_id == target_id)) is None:
        raise HTTPException(404, 'Application host was not found')


@router.get('/targets')
def targets(response: Response, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    items = [{'component': 'agent', 'target_id': 'local', 'label': 'Local Agent'}]
    for installation, package in db.execute(select(ApplicationExtensionInstallation, ModulePackage).join(
            ModulePackage, ModulePackage.id == ApplicationExtensionInstallation.module_package_id).where(
            ApplicationExtensionInstallation.enabled.is_(True), ApplicationExtensionInstallation.status == 'active'
        ).order_by(ApplicationExtensionInstallation.module_id).limit(128)):
        items.append({'component': 'application_host', 'target_id': installation.instance_id,
            'label': (package.manifest.get('name') or installation.module_id) + ' · ' + installation.instance_id})
    return {'targets': items}


@router.get('/nodes')
def nodes(response: Response, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Local registry only; no catalog network call or device command on page load."""
    import re
    from backend.routes.node_updates import _current_node_release_id
    response.headers['Cache-Control'] = 'no-store'
    items = []
    for device in db.scalars(select(Device).where(Device.role == 'node', Device.revoked_at.is_(None))
            .order_by(Device.device_id).limit(128)):
        latest = db.scalar(select(DeviceCommand).where(DeviceCommand.device_id == device.id,
            DeviceCommand.command_type == 'agent.update.prepare').order_by(DeviceCommand.id.desc()).limit(1))
        identifier = (latest.payload or {}).get('operation_id') if latest else None
        if type(identifier) is not str or not re.fullmatch(r'nodeupd_[0-9a-f]{32}', identifier): identifier = None
        items.append({'device_id': device.device_id, 'label': device.display_name or device.device_id,
            'current_release_id': _current_node_release_id(db, device), 'latest_operation_id': identifier})
    return {'nodes': items}


@router.get('/{component}/{target_id}', response_model=ComponentUpdateStatus)
def component_status(component: ComponentKind, target_id: str, response: Response,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    target(component, target_id, db)
    try:
        result = UpdateHelperClient(get_settings().updates.helper_socket).component_status(component, target_id, admin.id)
        value = ComponentUpdateStatus.model_validate(result)
        if (value.component, value.target_id) != (component, target_id): raise ValueError('Target changed')
        return value
    except (UpdateHelperError, ValueError, KeyError):
        raise HTTPException(409, 'Component status is unavailable; other administration remains available.') from None


def operation(action, component, target_id, payload, admin, db):
    target(component, target_id, db)
    if action in {'apply', 'rollback'}:
        if payload.confirmation != confirmation(action, component, target_id, payload.build_id):
            raise HTTPException(422, 'Confirm the exact component, target and build.')
        try: ensure_apply_is_allowed(get_settings().updates, maintenance_override=payload.maintenance_override)
        except UpdatePolicyError:
            raise HTTPException(409, {'code': 'component_update_not_accepted'}) from None
    data = payload.model_dump(exclude={'maintenance_override'})
    data.update(action='component_' + action, component=component, target_id=target_id, requested_by_user_id=admin.id)
    try:
        identifier = UpdateHelperClient(get_settings().updates.helper_socket).component_operation(data)
    except ComponentUpdateNotAccepted:
        raise HTTPException(409, {'code': 'component_update_not_accepted'}) from None
    except (UpdateHelperError, ValueError, KeyError):
        raise HTTPException(409, 'Component operation is unconfirmed. Read its original status; do not resend.') from None
    db.add(AuditLog(user_id=admin.id, action='COMPONENT_OPERATION_ACCEPTED', entity_type=component,
        entity_name=target_id, changes={'operation': action, 'request_id': identifier}))
    db.commit()
    return RuntimeAccepted(request_id=identifier)


@router.post('/{component}/{target_id}/prepare', response_model=RuntimeAccepted, status_code=202)
def prepare(component: ComponentKind, target_id: str, payload: ComponentPrepareRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return operation('prepare', component, target_id, payload, admin, db)


@router.post('/{component}/{target_id}/apply', response_model=RuntimeAccepted, status_code=202)
def apply(component: ComponentKind, target_id: str, payload: ComponentApplyRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return operation('apply', component, target_id, payload, admin, db)


@router.post('/{component}/{target_id}/rollback', response_model=RuntimeAccepted, status_code=202)
def rollback(component: ComponentKind, target_id: str, payload: ComponentSwitchRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return operation('rollback', component, target_id, payload, admin, db)


@router.post('/{component}/{target_id}/recover', response_model=RuntimeAccepted, status_code=202)
def recover(component: ComponentKind, target_id: str, payload: ComponentPrepareRequest,
        admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return operation('recover', component, target_id, payload, admin, db)
