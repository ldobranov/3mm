"""Core-owned pairing; encrypted finite response recovery, never business replay."""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationKioskEnrollment as Enrollment, ApplicationKioskTerminal as Terminal
from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services.application_delegations import login_actor
from backend.services.authority_metadata import authority_transaction, read_application_authority
from backend.utils.jwt_utils import create_access_token


def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def utc(value): return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _admin(db, authorization):
    actor, _ = login_actor(db, authorization)
    if db.get(User, actor['user_id']).role != 'admin': raise HTTPException(403,'Administrator required')
    return actor


def _installation(db, module):
    app=db.scalar(select(Installation).where(Installation.module_id==module))
    if app is None: raise HTTPException(404,'Application unavailable')
    return app


def _prepare(engine,module):
    manager=authority.configured_manager(engine)
    with Session(engine) as db: identifier=_installation(db,module).id
    prepared=manager._prepare(identifier)
    definition=prepared.package.application_extension
    if (prepared.package.compiled_ui is None or not any(r.audience=='kiosk' for r in definition.routes)
            or not any('kiosk' in op.audiences for op in definition.operations)):
        raise HTTPException(409,'Application has no kiosk interface')
    return manager,identifier,prepared


def _active(manager,db,key,identifier,prepared):
    app=db.get(Installation,identifier,populate_existing=True)
    if app is None or not app.enabled or app.status!='active' or app.module_package_id!=prepared.pin.module_package_id:
        raise HTTPException(409,'Application is unavailable')
    if app.authority_mode!='compatibility':
        manager._require_ui_trust_in_snapshot(db,key,identifier,prepared.built_ui_sha256,prepared)
    return app


def _record(db,key,app,request_id,purpose):
    row=db.get(Action,request_id,populate_existing=True)
    if row is None:return None,None
    value=authority._load(db,key,'action',row,request_id)
    data=value['data']
    if (value['installation_id']!=app.id or data.get('operation')!=purpose
            or data.get('incarnation')!=app.authority_incarnation or data.get('module_id')!=app.module_id):
        raise HTTPException(409,'Pairing request conflicts with its owner')
    return row,value


def _save(db,key,app,request_id,purpose,data):
    data.update(operation=purpose,module_id=app.module_id,incarnation=app.authority_incarnation)
    value=authority._envelope('action',request_id,app.id,'recorded',data)
    authority._save(db,key,'action',Action(request_id=request_id,installation_id=app.id),value)


def _expiry(until,seconds=None):
    boot,instant=authority._clock()
    end=min(utc(until),datetime.now(UTC)+timedelta(seconds=seconds)) if seconds else utc(until)
    return dict(expires_at=end.isoformat(),boot_id=boot,expires_ms=instant+max(0,int((end-datetime.now(UTC)).total_seconds()*1000)))


def _expired(data):
    boot,instant=authority._clock()
    return boot!=data['boot_id'] or instant>=data['expires_ms'] or datetime.now(UTC)>=datetime.fromisoformat(data['expires_at'])


def _audit(db,app,operation,user=None,terminal=None):
    db.add(AuditLog(user_id=user,action='APPLICATION_KIOSK_'+operation,entity_type='application_extension',
        entity_name=app.module_id,changes={'terminal_id':terminal}))


def _token(app,terminal,prepared):
    return dict(module_id=app.module_id,installation_incarnation=app.authority_incarnation,
        terminal_id=terminal.terminal_id,artifact_sha256=prepared.package.sha256,built_ui_sha256=prepared.built_ui_sha256,
        access_token=create_access_token('kiosk:'+terminal.terminal_id,{'token_type':'application_kiosk',
            'module_id':app.module_id,'terminal_id':terminal.terminal_id,'incarnation':app.authority_incarnation},
            expires_delta=timedelta(minutes=15)),expires_in_seconds=900)


def enroll(engine,module,authorization,request):
    # Auth before artifact/key work. Infrastructure provisioning is explicit and
    # available only to this authenticated administrator operation.
    with Session(engine) as db:_admin(db,authorization)
    manager,identifier,prepared=_prepare(engine,module)
    from backend.services.application_consent import _bootstrap_key
    _bootstrap_key(manager,authorization.split(' ',1)[1].strip())
    with manager.keys.locked() as key,Session(engine) as db,authority_transaction(db) as mutation:
        actor=_admin(db,authorization);app=_active(manager,db,key,identifier,prepared)
        mutation.lock_application(read_application_authority(db,identifier))
        _,old=_record(db,key,app,request.request_id,'kiosk.enrollment')
        body=request.model_dump()
        if old:
            data=old['data']
            if data['actor']!=actor or data['request']!=body or data['artifact_sha256']!=prepared.package.sha256:
                raise HTTPException(409,'Enrollment request changed')
            if _expired(data):raise HTTPException(410,'Enrollment recovery expired; review and issue another code')
            enrollment=db.get(Enrollment,data['enrollment_id'])
            if enrollment is None or enrollment.consumed_at is not None:raise HTTPException(409,'Enrollment was already claimed')
            secret=key.encrypted_receipt(db,'kiosk.enrollment',ciphertext=data['response'])
            return dict(request_id=request.request_id,code=secret['code'],expires_at=data['expires_at'])
        if db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.application_installation_id==identifier))>=1024:
            raise HTTPException(409,'Enrollment history budget reached')
        code=secrets.token_urlsafe(24);expires=datetime.now(UTC)+timedelta(minutes=request.expires_in_minutes)
        row=Enrollment(application_installation_id=identifier,installation_incarnation=app.authority_incarnation,
            code_hash=digest(code),label=request.label,expires_at=expires,created_by=actor['user_id'])
        db.add(row);db.flush()
        data=dict(actor=actor,request=body,artifact_sha256=prepared.package.sha256,enrollment_id=row.id,
            response=key.encrypted_receipt(db,'kiosk.enrollment',{'code':code}),**_expiry(expires))
        _save(db,key,app,request.request_id,'kiosk.enrollment',data);_audit(db,app,'ENROLL',actor['user_id'])
        return dict(request_id=request.request_id,code=code,expires_at=data['expires_at'])


def claim(engine,module,request):
    manager,identifier,prepared=_prepare(engine,module)
    with manager.keys.locked() as key,Session(engine) as db,authority_transaction(db) as mutation:
        app=_active(manager,db,key,identifier,prepared)
        mutation.lock_application(read_application_authority(db,identifier))
        _,old=_record(db,key,app,request.request_id,'kiosk.claim')
        code_hash,proof_hash=digest(request.code),digest(request.recovery_proof)
        if old:
            data=old['data']
            if not secrets.compare_digest(data['proof_hash'],proof_hash) or not secrets.compare_digest(data['code_hash'],code_hash):
                raise HTTPException(409,'Claim belongs to another client')
            if _expired(data):raise HTTPException(410,'Claim recovery expired; review and revoke before pairing again')
            terminal=db.scalar(select(Terminal).where(Terminal.terminal_id==data['terminal_id']))
            if not _owned(app,terminal):raise HTTPException(401,'Terminal is revoked or unavailable')
            credential=key.encrypted_receipt(db,'kiosk.claim',ciphertext=data['response'])['credential']
            return dict(credential=credential,**_token(app,terminal,prepared))
        enrollment=db.scalar(select(Enrollment).where(Enrollment.application_installation_id==identifier,
            Enrollment.installation_incarnation==app.authority_incarnation,Enrollment.code_hash==code_hash))
        if enrollment is None or utc(enrollment.expires_at)<=datetime.now(UTC):
            raise HTTPException(400,'Invalid or expired enrollment code')
        if enrollment.consumed_at is not None:raise HTTPException(409,'Code already claimed by another request')
        receipt=db.scalar(select(Action).where(Action.installation_id==identifier,
            func.json_extract(Action.payload,'$.data.operation')=='kiosk.enrollment',
            func.json_extract(Action.payload,'$.data.enrollment_id')==enrollment.id))
        if receipt is None:raise HTTPException(400,'Invalid enrollment code')
        _,issued=_record(db,key,app,receipt.request_id,'kiosk.enrollment')
        if _expired(issued['data']):raise HTTPException(410,'Enrollment expired; issue another code')
        if issued['data']['artifact_sha256']!=prepared.package.sha256:
            raise HTTPException(409,'Application changed; issue another code')
        credential=secrets.token_urlsafe(32)
        terminal=Terminal(terminal_id=uuid.uuid4().hex,enrollment_id=enrollment.id,application_installation_id=identifier,
            installation_incarnation=app.authority_incarnation,label=enrollment.label,credential_hash=digest(credential),enabled=True)
        db.add(terminal);enrollment.consumed_at=datetime.now(UTC);db.flush()
        _save(db,key,app,request.request_id,'kiosk.claim',dict(terminal_id=terminal.terminal_id,code_hash=code_hash,
            proof_hash=proof_hash,response=key.encrypted_receipt(db,'kiosk.claim',{'credential':credential}),
            **_expiry(enrollment.expires_at,300)))
        # The sealed claim above records the terminal event. Human audit_logs
        # require a real user actor; never attribute a kiosk claim to its issuer.
        return dict(credential=credential,**_token(app,terminal,prepared))


def _owned(app,terminal):
    return (terminal is not None and terminal.enabled and terminal.revoked_at is None
        and terminal.application_installation_id==app.id and terminal.installation_incarnation==app.authority_incarnation)


def renew(engine,module,request):
    manager,identifier,prepared=_prepare(engine,module)
    with manager.keys.locked() as key,Session(engine) as db,authority_transaction(db) as mutation:
        app=_active(manager,db,key,identifier,prepared)
        mutation.lock_application(read_application_authority(db,identifier))
        terminal=db.scalar(select(Terminal).where(Terminal.terminal_id==request.terminal_id))
        if not _owned(app,terminal) or not secrets.compare_digest(terminal.credential_hash,digest(request.credential)):
            raise HTTPException(401,'Terminal is revoked or unavailable')
        terminal.last_seen_at=datetime.now(UTC)
        return _token(app,terminal,prepared)


def terminals(engine,module,authorization):
    with Session(engine) as db:
        _admin(db,authorization);app=_installation(db,module)
        rows=db.scalars(select(Terminal).where(Terminal.application_installation_id==app.id).order_by(Terminal.id)).all()
        return {'items':[dict(terminal_id=t.terminal_id,label=t.label,enabled=_owned(app,t),
            created_at=t.created_at,last_seen_at=t.last_seen_at,revoked_at=t.revoked_at,
            needs_pairing=t.installation_incarnation!=app.authority_incarnation) for t in rows]}


def revoke(engine,module,authorization,terminal_id):
    # Administration remains available when a package or optional UI is broken.
    with Session(engine) as db,authority_transaction(db) as mutation:
        actor=_admin(db,authorization);app=_installation(db,module)
        mutation.lock_application(read_application_authority(db,app.id))
        terminal=db.scalar(select(Terminal).where(Terminal.application_installation_id==app.id,Terminal.terminal_id==terminal_id))
        if terminal is None:raise HTTPException(404,'Owned terminal unavailable')
        if terminal.enabled:
            terminal.enabled=False;terminal.revoked_at=datetime.now(UTC)
            _audit(db,app,'REVOKE',actor['user_id'],terminal.terminal_id)
        return {'status':'revoked'}
