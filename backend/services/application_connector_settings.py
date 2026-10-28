"""Core-owned connector setup. No service startup, external I/O or credential reads.

Writes share one key/guard/current-login transaction, including first inert
registration, configuration, encrypted credential, binding and redacted receipt.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import re
from types import SimpleNamespace
from fastapi import HTTPException

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action, ApplicationAuthorityGrant as Grant
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage, ApplicationConnectorBinding as Binding, ApplicationSecretReference as Secret
from backend.services import application_authority_management as authority
from backend.services import application_authority_sources as sources
from backend.services import application_configuration_provenance as provenance
from backend.services.application_authority_context import AuthorityPrincipal, _canonical_bytes, _bounded_json
from backend.services.application_authority_inspection import AuthorityInspectionBaseline, _read_baseline
from backend.services.application_consent import _bootstrap_key
from backend.services.application_configuration import ApplicationConfigurationError, MAX_CONFIGURATION_BYTES, _validate_value, resolve_application_configuration
from backend.services.application_connectors import ApplicationConnectorError, ConnectorBindingPlan, _package_state, bind_application_connector, validate_destination_origin
from backend.services.application_policy_reviews import _actor, PolicyReviewStoreError
from backend.services.application_secrets import ApplicationSecretError, create_secret_reference, read_secret_authority, rotate_secret_reference, revoke_secret_reference, _fernet
from backend.services.authority_metadata import authority_transaction, read_application_authority, read_authority_guard
from three_mm_runtime.application_activation import application_instance_id

OPERATION = 'connector_settings'


def _current_actor(db, token):
    try:
        actor = list(_actor(db, token))
        from backend.services.application_access import validate_application_login
        from backend.utils.jwt_utils import decode_token
        claims = decode_token(token)
        user = validate_application_login(claims, db)
        actor[2] = hashlib.sha256((user.subject_id + ':' + claims['jti']).encode()).hexdigest()
        return actor
    except (PolicyReviewStoreError, HTTPException):
        raise authority.AuthorityManagementError('actor_unavailable') from None


def _receipt_owner(saved, actor, app):
    # A valid token refresh within the same live login can still recover its
    # receipt. A different login, account or installation incarnation cannot.
    owner = saved['data'].get('actor')
    return (isinstance(owner, list) and len(owner) == 3
        and app is not None and saved['installation_id'] == app.id
        and saved['data'].get('incarnation') == app.authority_incarnation
        and owner == actor)


class ConnectorSettingsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_snapshot: str = Field(pattern=r'^[0-9a-f]{64}$')
    action: str = Field(pattern=r'^(save|rotate|revoke)$')
    destination_origin: str | None = Field(default=None, max_length=512)
    secret_ref: str | None = Field(default=None, pattern=r'^secret_[0-9a-f]{32}$')
    create_credential: bool = False
    credential_label: str = Field(default='', max_length=120)
    # Never serialize or repr the draft, and never hash it into a receipt.
    credential: dict[str, str] | None = Field(default=None, max_length=3, exclude=True, repr=False)
    confirm_credential_change: bool = False


@dataclass(frozen=True)
class Prepared:
    package_id: int
    module_id: str
    version: str
    sha256: str
    package: object
    authority_prepared: object = None


def prepare(manager, sha256, token):
    authority._digest(sha256)
    # Real actor first; no leases/DB connections span artifact reads.
    with Session(manager.engine) as db, authority_transaction(db):
        _current_actor(db, token)
        row = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
        if row is None:
            raise authority.AuthorityManagementError('artifact_unavailable')
        identifier, module_id, version = row.id, row.module_id, row.version
        app = db.scalar(select(Installation).where(Installation.module_id == module_id))
        if app is not None and app.module_package_id != identifier:
            raise authority.AuthorityManagementError('artifact_changed')
        installation_id = app.id if app else None
    if installation_id is not None:
        prepared = manager._prepare(installation_id)
        if prepared.pin.sha256 != sha256:
            raise authority.AuthorityManagementError('artifact_changed')
        package = prepared.package
    else:
        prepared = None
        package = _read_baseline(AuthorityInspectionBaseline(module_id, version, sha256,
            None, 'disabled', None), manager.uploads_root, manager.core_version)
    if not package.application_extension.connectors:
        raise authority.AuthorityManagementError('connector_unavailable')
    return Prepared(identifier, module_id, version, sha256, package, prepared)


def _current(db, prepared):
    row = db.get(ModulePackage, prepared.package_id, populate_existing=True)
    if row is None or (row.module_id, row.version, row.sha256) != (
            prepared.module_id, prepared.version, prepared.sha256):
        raise authority.AuthorityManagementError('artifact_changed')
    app = db.scalar(select(Installation).where(Installation.module_id == prepared.module_id)
        .execution_options(populate_existing=True))
    if app is not None and app.module_package_id != prepared.package_id:
        raise authority.AuthorityManagementError('artifact_changed')
    return app


def _credentials(db, app):
    if app is None:
        return []
    # Inspect never selects ciphertext, username or credential material.
    rows = db.execute(select(Secret.id, Secret.secret_ref, Secret.label, Secret.credential_kind,
        Secret.version, Secret.revoked_at).where(Secret.application_installation_id == app.id)
        .order_by(Secret.id).limit(129)).all()
    if len(rows) > 128:
        raise authority.AuthorityManagementError('credential_limit')
    return [dict(id=r.id, secret_ref=r.secret_ref, label=r.label,
        authentication=r.credential_kind, version=r.version, revoked=r.revoked_at is not None) for r in rows]


def _bindings(db, app):
    if app is None:
        return []
    result = [dict(connector_id=r.connector_id, origin=r.destination_origin, secret_id=r.secret_reference_id,
        enabled=r.enabled, revision=r.authority_revision) for r in db.scalars(select(Binding)
            .where(Binding.application_installation_id == app.id).order_by(Binding.connector_id).limit(65))]
    if len(result) > 64:
        raise authority.AuthorityManagementError('binding_limit')
    return result


def _snapshot(db, key, prepared, app, credentials, bindings):
    configuration = dict(prepared.package.manifest.configuration_defaults)
    configuration.update(app.configuration if app is not None else {})
    # A keyed fingerprint of configuration, never a password-derived receipt hash.
    principal = AuthorityPrincipal(core_installation_id=sources._core_identity(db),
        application_installation_id=str(app.id if app else 0),
        incarnation=app.authority_incarnation if app else '0' * 32, module_id=prepared.module_id)
    config = key._fingerprint_in_snapshot(db, principal, _bounded_json(configuration)).model_dump(mode='json')
    return hashlib.sha256(b'3mm:connector-settings-snapshot:v1\0' + _canonical_bytes({
        'artifact': prepared.sha256, 'core': read_authority_guard(db).generation,
        'configuration': config, 'credentials': credentials, 'bindings': bindings,
        'installation': None if app is None else [app.id, app.instance_id, app.authority_incarnation,
            app.authority_epoch, app.authority_mode, app.active_version, app.status, app.enabled,
            app.previous_package_id]})).hexdigest()


def _inspection(manager, db, key, prepared, app):
    credentials, bindings = _credentials(db, app), _bindings(db, app)
    snapshot = _snapshot(db, key, prepared, app, credentials, bindings)
    configuration = dict(prepared.package.manifest.configuration_defaults)
    configuration.update(app.configuration if app is not None else {})
    granted = set()
    has_grant = app is not None and db.get(Grant, app.id) is not None
    if has_grant and prepared.authority_prepared is not None:
        try:
            grant = manager._require_current_grant(db, key, app.id, prepared.authority_prepared)
            granted = set(grant['data']['selection']['scopes'])
        except (authority.AuthorityManagementError, ValueError, KeyError, TypeError):
            pass
    states = []
    for declaration in prepared.package.application_extension.connectors:
        binding = next((b for b in bindings if b['connector_id'] == declaration.connector_id), None)
        secret = next((s for s in credentials if binding and s['id'] == binding['secret_id']), None)
        reasons = []
        if not binding:
            reasons.append('connector_binding_unavailable')
        else:
            if not binding['enabled']:
                reasons.append('connector_disabled')
            if configuration.get(declaration.destination_config_key) != binding['origin']:
                reasons.append('connector_origin_mismatch')
            try:
                if validate_destination_origin(binding['origin'], declaration.allowed_schemes) != binding['origin']:
                    raise ValueError()
            except (ValueError, RuntimeError):
                if 'connector_origin_mismatch' not in reasons:
                    reasons.append('connector_origin_mismatch')
            if declaration.authentication != 'none' and (not secret or secret['revoked']
                    or secret['authentication'] != declaration.authentication
                    or configuration.get(declaration.credential_ref_config_key) != secret['secret_ref']):
                reasons.append('connector_credential_unavailable')
        affected = sorted(b['connector_id'] for b in bindings if secret and b['secret_id'] == secret['id'])
        states.append(dict(connector_id=declaration.connector_id, artifact_sha256=prepared.sha256,
            snapshot=snapshot, authentication=declaration.authentication,
            allowed_schemes=list(declaration.allowed_schemes), path_prefix=declaration.path_prefix,
            destination_origin=binding['origin'] if binding else None,
            credential=None if secret is None else {k: secret[k] for k in ('secret_ref', 'label', 'version', 'revoked')},
            affected_connector_ids=affected, reasons=reasons,
            state='unconfigured' if binding is None else 'disabled' if not binding['enabled'] else 'unavailable' if reasons else 'configured',
            authority='granted' if 'connector:' + declaration.connector_id in granted else 'stale' if has_grant else 'not_granted'))
    try:
        _fernet()
        encryption_available = True
    except RuntimeError:
        encryption_available = False
    return dict(module_id=prepared.module_id, artifact_sha256=prepared.sha256,
        installation_id=app.id if app else None, snapshot=snapshot,
        encryption_available=encryption_available, connectors=states,
        credentials=[{k: v for k, v in s.items() if k != 'id'} for s in credentials])


def inspect(manager, sha256, token):
    prepared = prepare(manager, sha256, token)
    _bootstrap_key(manager, token)  # Existing consent infrastructure only; no grant.
    with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db):
        _current_actor(db, token)
        return _inspection(manager, db, key, prepared, _current(db, prepared))


def _request_identity(prepared, connector_id, request):
    # No credential fields and no digest of credential material.
    return hashlib.sha256(_canonical_bytes(dict(artifact_sha256=prepared.sha256,
        connector_id=connector_id, expected_snapshot=request.expected_snapshot,
        action=request.action, destination_origin=request.destination_origin,
        secret_ref=request.secret_ref, create_credential=request.create_credential,
        credential_label=request.credential_label))).hexdigest()


def _configuration(prepared, app, declaration, origin, secret_ref, *, allow_incomplete=False):
    configuration = dict(prepared.package.manifest.configuration_defaults)
    configuration.update(app.configuration if app is not None else {})
    configuration[declaration.destination_config_key] = origin
    if declaration.credential_ref_config_key:
        configuration[declaration.credential_ref_config_key] = secret_ref
    schema = prepared.package.manifest.configuration_schema
    # Only first inert registration can be incomplete. Full validation still
    # gates native consent, SQL preparation and activation.
    if allow_incomplete:
        _validate_value(configuration, {**schema, 'required': []}, 'configuration')
    else:
        configuration = resolve_application_configuration(schema, {}, prepared.package.application_extension,
            existing=configuration)
    if len(_canonical_bytes(configuration)) > MAX_CONFIGURATION_BYTES:
        raise authority.AuthorityManagementError('configuration_unavailable')
    return _bounded_json(configuration)


@contextmanager
def _transaction(manager):
    with manager.keys.locked() as key, Session(manager.engine) as db:
        try:
            with authority_transaction(db) as mutation:
                yield db, key, mutation
        except (ApplicationConfigurationError, ApplicationConnectorError, ApplicationSecretError):
            # Convert after rollback but before leaving the key adapter, whose
            # generic filesystem boundary deliberately redacts ValueError too.
            raise authority.AuthorityManagementError('invalid_request') from None


def configure(manager, sha256, connector_id, request, token):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', connector_id):
        raise authority.AuthorityManagementError('invalid_request')
    prepared = prepare(manager, sha256, token)
    declaration = next((c for c in prepared.package.application_extension.connectors if c.connector_id == connector_id), None)
    if declaration is None:
        raise authority.AuthorityManagementError('connector_unavailable')
    request_hash = _request_identity(prepared, connector_id, request)
    _bootstrap_key(manager, token)
    with _transaction(manager) as (db, key, mutation):
        actor = _current_actor(db, token)
        key._check(db)
        app = _current(db, prepared)
        existing = db.get(Action, request.request_id)
        if existing is not None:
            saved = authority._load(db, key, 'action', existing, request.request_id)
            if (saved['state'] != 'recorded' or saved['data'].get('operation') != OPERATION
                    or not _receipt_owner(saved, actor, app) or saved['data'].get('request_hash') != request_hash):
                raise authority.AuthorityManagementError('request_conflict')
            return saved['data']['result']
        observation = _inspection(manager, db, key, prepared, app)
        if observation['snapshot'] != request.expected_snapshot:
            raise authority.AuthorityManagementError('snapshot_conflict')
        if app is not None:
            mutation.lock_application(read_application_authority(db, app.id))
            if app.authority_mode == 'compatibility' and (app.enabled or app.status != 'disabled'):
                raise authority.AuthorityManagementError('stop_required')
        source = None
        allow_incomplete = app is None
        if app is not None and app.active_version is None:
            source = provenance.current_registration(db, key, app.id, sources._package_pin(db, app.id), prepared.package)
            allow_incomplete = source[1]['data'].get('operation') == 'connector_first_registration'
        if app is not None and db.scalar(select(func.count()).select_from(Action).where(Action.installation_id == app.id)) >= 4094:
            raise authority.AuthorityManagementError('journal_full')
        if request.action != 'save' and (app is None or request.confirm_credential_change is not True
                or request.create_credential or request.destination_origin is not None):
            raise authority.AuthorityManagementError('invalid_request')
        if request.action == 'save':
            origin = validate_destination_origin(request.destination_origin or '', declaration.allowed_schemes)
            if declaration.authentication != 'none':
                try:
                    _fernet()
                except ApplicationSecretError:
                    raise authority.AuthorityManagementError('encryption_unavailable') from None
            if declaration.authentication == 'none':
                if request.secret_ref is not None or request.credential is not None or request.create_credential:
                    raise authority.AuthorityManagementError('invalid_request')
            elif request.create_credential:
                if request.secret_ref is not None or not request.credential_label.strip() or request.credential is None:
                    raise authority.AuthorityManagementError('invalid_request')
            elif request.secret_ref is None or request.credential is not None:
                raise authority.AuthorityManagementError('invalid_request')
            if app is None:
                app = Installation(module_id=prepared.module_id, module_package_id=prepared.package_id,
                    instance_id=application_instance_id(prepared.module_id), active_version=None,
                    status='disabled', enabled=False, socket_path='pending', configuration={}, authority_mode='review_required')
                db.add(app)
                db.flush()
            application = read_application_authority(db, app.id)
            secret_ref = request.secret_ref
            if request.create_credential:
                if len(_credentials(db, app)) >= 128:
                    raise authority.AuthorityManagementError('credential_limit')
                secret = create_secret_reference(db, application=application, authority=mutation,
                    label=request.credential_label, credential_kind=declaration.authentication, value=request.credential)
                secret_ref = secret.secret_ref
            configuration = _configuration(prepared, app, declaration, origin, secret_ref, allow_incomplete=allow_incomplete)
            row = db.get(ModulePackage, prepared.package_id)
            plan = ConnectorBindingPlan(application, _package_state(app, row), connector_id,
                declaration.authentication, origin, secret_ref)
            bind_application_connector(db, plan, authority=mutation)
            app.configuration = configuration
            db.flush()
        else:
            current = next(c for c in observation['connectors'] if c['connector_id'] == connector_id)
            if current['credential'] is None or request.secret_ref != current['credential']['secret_ref']:
                raise authority.AuthorityManagementError('invalid_request')
            expected = read_secret_authority(db, read_application_authority(db, app.id), request.secret_ref)
            if request.action == 'rotate':
                if request.credential is None:
                    raise authority.AuthorityManagementError('invalid_request')
                rotate_secret_reference(db, expected, request.credential, authority=mutation)
            else:
                if request.credential is not None:
                    raise authority.AuthorityManagementError('invalid_request')
                revoke_secret_reference(db, expected, authority=mutation)
        # Binding helpers may already have advanced the epoch. Read the resulting
        # snapshot before withdrawing consent; never resurrect a previous grant.
        mutation.set_application_mode(read_application_authority(db, app.id), 'review_required')
        db.expire(app, ['authority_epoch', 'authority_mode'])
        if app.active_version is None:
            if source is None:
                marker = provenance.registration_id(db, app.id)
                pin = SimpleNamespace(module_package_id=prepared.package_id, sha256=prepared.sha256, version=prepared.version)
                if db.get(Action, marker) is not None:
                    raise authority.AuthorityManagementError('request_conflict')
                authority._save(db, key, 'action', Action(request_id=marker, installation_id=app.id),
                    authority._envelope('action', marker, app.id, 'connector_registered_not_started', {
                        'operation': 'connector_first_registration', 'actor': actor,
                        'binding': provenance._binding(db, key, app.id, pin, prepared.package)}))
            else:
                provenance.record_transition(db, key, app.id, source, actor)
        state = next(c for c in _inspection(manager, db, key, prepared, app)['connectors'] if c['connector_id'] == connector_id)
        result = dict(request_id=request.request_id, status='applied', state=state)
        if _current_actor(db, token) != actor:
            raise authority.AuthorityManagementError('actor_unavailable')
        authority._save(db, key, 'action', Action(request_id=request.request_id, installation_id=app.id),
            authority._envelope('action', request.request_id, app.id, 'recorded', {
                'operation': OPERATION, 'actor': actor, 'request_hash': request_hash,
                'incarnation': app.authority_incarnation,
                'artifact_sha256': sha256, 'result': result}))
        db.add(AuditLog(user_id=actor[0], action='APPLICATION_CONNECTOR_SETTINGS', entity_type='application_extension',
            entity_name=prepared.module_id, changes={'request_id': request.request_id, 'action': request.action,
                'connector_id': connector_id, 'artifact_sha256': sha256, 'permission_approval': 'required'}))
        mutation.advance_guard_revision()
        return result


def outcome(manager, sha256, request_id, token):
    authority._identifier(request_id)
    prepared = prepare(manager, sha256, token)
    with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db):
        actor = _current_actor(db, token)
        app = _current(db, prepared)
        row = db.get(Action, request_id)
        if row is None:
            return dict(request_id=request_id, status='unknown')
        value = authority._load(db, key, 'action', row, request_id)
        if (value['data'].get('operation') != OPERATION or value['data'].get('artifact_sha256') != sha256
                or not _receipt_owner(value, actor, app)):
            raise authority.AuthorityManagementError('actor_unavailable')
        return value['data']['result']
