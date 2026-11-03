"""Register a stopped application's next immutable package for fresh review.

No helper, wheel import, application startup, grant resurrection or data reset.
This bounded adapter does not replace prepared relational/session lifecycles.
"""
import hashlib,json
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation,ModulePackage,ApplicationJobState
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant,ApplicationAuthorityAction as Action
from backend.db.device import Device
from backend.db.audit_log import AuditLog
from backend.services.application_authority_management import _load,_save,_envelope
from backend.services.application_extensions import load_application_package
from backend.services.application_requirements import require_platform_requirements
from backend.services.application_configuration import (
    resolve_device_selection, binding_configuration_keys, require_available_device_bindings,
    device_configuration_keys, resolve_application_configuration,
)
from backend.services.authority_metadata import read_application_authority
from backend.services.application_commands import invalidate_commands
from backend.services.application_tasks import require_quiescent_task_journal


def registration_id(db,installation_id,package_id,sha256):
    from backend.services.application_authority_sources import _core_identity
    from backend.services.application_authority_context import _canonical_bytes
    current=read_application_authority(db,installation_id)
    # Persisted sealing format, shared with the original task registrations.
    # The tag conveys inert provenance only, never permission to execute code.
    return hashlib.sha256(b'3mm:task-inert-package:v1\0'+_canonical_bytes({
        'core':_core_identity(db),'installation':installation_id,'incarnation':current.incarnation,
        'package_id':package_id,'sha256':sha256})).hexdigest()[:32]


def _binding(db,key,installation_id,package_id,package):
    from backend.services.application_authority_context import AuthorityPrincipal
    from backend.services.application_authority_sources import _core_identity,_configuration
    current=read_application_authority(db,installation_id)
    principal=AuthorityPrincipal(core_installation_id=_core_identity(db),application_installation_id=str(installation_id),
        incarnation=current.incarnation,module_id=current.module_id)
    app=db.get(Installation,installation_id,populate_existing=True)
    return {'principal':principal.model_dump(mode='json'),'package_id':package_id,
        'sha256':package.sha256,'version':package.manifest.version,'instance_id':app.instance_id,
        'configuration':key._fingerprint_in_snapshot(db,principal,_configuration(db,installation_id,package)).model_dump(mode='json')}


def verify_registration(db,key,installation_id,pin,package):
    from backend.services.application_configuration_provenance import binding_matches
    from backend.services.application_authority_context import _canonical_bytes
    from backend.services.application_authority_management import AuthorityManagementError
    if key is None:
        from backend.services.application_authority_sources import _Unavailable
        raise _Unavailable('installation_unavailable')
    identifier=registration_id(db,installation_id,pin.module_package_id,pin.sha256)
    proof=_load(db,key,'action',db.get(Action,identifier),identifier)
    if (proof['state']!='task_registered_not_started'
            or set(proof['data'])!={'operation','actor','binding'} or proof['data']['operation']!='task_package_stage'
            or not binding_matches(db,key,installation_id,identifier,proof['revision'],
                proof['data']['binding'],_binding(db,key,installation_id,pin.module_package_id,package))):
        raise AuthorityManagementError('registration_unavailable')


def _supported(definition):
    # These profiles have separate prepared migration/provider lifecycles.
    return definition.storage.relational is None and not definition.session_providers


def stage_application_package(engine,sha256,request,actor_token):
    from backend.services.application_authority_management import configured_manager
    manager=configured_manager(engine)
    with Session(engine) as db:
        package=db.scalar(select(ModulePackage).where(ModulePackage.sha256==sha256))
        app=db.scalar(select(Installation).where(Installation.module_id==package.module_id)) if package else None
        if app is None:
            raise ValueError("An existing stopped application installation is required")
        identifier=app.id
        original=(app.authority_incarnation,app.authority_epoch,app.instance_id,app.module_package_id)
        old=manager._prepare(identifier)
        target=load_application_package(package)
        definition=target.application_extension
        require_platform_requirements(definition)
        if not _supported(old.package.application_extension) or not _supported(definition):
            raise ValueError("This profile requires its dedicated prepared lifecycle")
        if set(request.configuration or {})-set(binding_configuration_keys(definition)):
            raise ValueError("Only declared resource bindings may be selected")
        schema=package.manifest.get('configuration_schema') or {}
        if request.complete_device_configuration:
            required=set(device_configuration_keys(definition, required_only=True))
            required.update(set(schema.get('required', ())) & set(device_configuration_keys(definition)))
            missing=required-set(app.configuration or {})
            if (package.id!=app.module_package_id or app.active_version is not None
                    or app.authority_mode!='review_required' or request.expected_revision is not None
                    or not missing or set(request.configuration or {})!=missing):
                raise ValueError('Only missing required device choices may complete this inert registration')
            configuration=resolve_application_configuration(schema,{},definition,
                existing=app.configuration,overrides=request.configuration)
        else:
            configuration=resolve_device_selection(schema,
                package.manifest.get('configuration_defaults') or {},definition,
                existing=app.configuration,selection=request.configuration)
        if len(json.dumps(configuration,allow_nan=False).encode())>8192:
            raise ValueError("Application configuration exceeds its budget")
        pin=(package.id,package.module_id,package.version,package.sha256,package.file_path)
        original_configuration=dict(app.configuration or {})
    from backend.services.application_consent import _bootstrap_key
    _bootstrap_key(manager,actor_token)
    body=request.model_dump(mode='json',exclude={'complete_device_configuration'});body['package_sha256']=sha256
    if request.complete_device_configuration:
        body['complete_device_configuration']=True
    with manager._write(identifier,actor_token,request.request_id,'task_package_stage',body) as (db,key,mutation,actor,result):
        if result:
            return result
        current=db.get(Installation,identifier,populate_existing=True)
        candidate=db.get(ModulePackage,pin[0],populate_existing=True)
        grant_record=db.get(Grant,identifier)
        revision=(_load(db,key,'grant',grant_record,identifier)['revision']
            if grant_record is not None and not request.complete_device_configuration else None)
        if (current.enabled or current.status!='disabled'
                or (current.authority_incarnation,current.authority_epoch,current.instance_id,current.module_package_id)!=original
                or current.module_package_id!=old.pin.module_package_id
                or old.pin.sha256!=request.expected_artifact_sha256
                or revision!=request.expected_revision or current.configuration!=original_configuration
                or candidate is None or (candidate.id,candidate.module_id,candidate.version,candidate.sha256,candidate.file_path)!=pin
                or current.module_id!=candidate.module_id):
            raise ValueError("Stop the current application and refresh its exact review before staging")
        if request.complete_device_configuration:
            from backend.services import application_configuration_provenance as provenance
            if current.active_version is not None or current.authority_mode!='review_required':
                raise ValueError('Application registration changed before configuration was saved')
            # Prove the incomplete first registration; do not repair missing or
            # invalid evidence and do not carry a previous grant forward.
            provenance.verify_registration(db,key,identifier,old.pin,old.package)
        require_quiescent_task_journal(db,identifier)
        if db.scalar(select(ApplicationJobState.id).where(ApplicationJobState.application_installation_id==identifier,
                ApplicationJobState.lease_token.is_not(None)).limit(1)) is not None:
            raise ValueError("Historical job claims require outcome review before staging")
        devices=set(db.scalars(select(Device.device_id).where(Device.revoked_at.is_(None),Device.approved_at.is_not(None))))
        require_available_device_bindings(definition,configuration,devices)
        invalidate_commands(db,identifier)
        mutation.set_application_mode(read_application_authority(db,identifier),'review_required')
        current=db.get(Installation,identifier,populate_existing=True)
        if not request.complete_device_configuration:
            current.previous_package_id=current.module_package_id
        current.module_package_id=candidate.id;current.active_version=None
        current.configuration=configuration;current.health_checked_at=None
        db.flush()
        marker=registration_id(db,identifier,candidate.id,sha256)
        if marker==request.request_id:
            raise ValueError('Stage request collides with its registration identity')
        binding=_binding(db,key,identifier,candidate.id,target)
        existing=db.get(Action,marker)
        if existing is None:
            _save(db,key,'action',Action(request_id=marker,installation_id=identifier),
                _envelope('action',marker,identifier,'task_registered_not_started',{
                    'operation':'task_package_stage','actor':actor,'binding':binding}))
        else:
            proof=_load(db,key,'action',existing,marker)
            if proof['state']!='task_registered_not_started' or proof['data'].get('binding')!=binding:
                raise ValueError('A prior inert registration has a different exact binding')
        db.add(AuditLog(user_id=actor[0],action='APPLICATION_PACKAGE_STAGED',entity_type='application_extension',
            entity_name=current.module_id,changes={'artifact_sha256':sha256,'version':candidate.version,'execution':'not_started'}))
        result.update(module_id=current.module_id,installation_id=identifier,instance_id=current.instance_id,
            artifact_sha256=sha256,version=candidate.version,status='disabled',enabled=False,
            permission_approval='required',execution='not_started')
        return result
