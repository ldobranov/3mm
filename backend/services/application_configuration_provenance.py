"""Sealed configuration transitions for inert packages, never executable grants.

Keep the original registration/adoption immutable. A configuration-only overlay
must refer to its exact authenticated revision and cannot alter its other fields.
"""
import hashlib

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_authority_context import AuthorityPrincipal, _canonical_bytes, _bounded_json
from backend.services import application_authority_sources as sources
from backend.services.authority_metadata import read_application_authority


def _id(domain, value):
    return hashlib.sha256(domain + _canonical_bytes(value)).hexdigest()[:32]


def registration_id(db, installation_id):
    current = read_application_authority(db, installation_id)
    return _id(b'3mm:connector-inert-registration:v1\0', {
        'core': sources._core_identity(db), 'installation': installation_id,
        'incarnation': current.incarnation})


def _binding(db, key, installation_id, pin, package):
    current = read_application_authority(db, installation_id)
    principal = AuthorityPrincipal(core_installation_id=sources._core_identity(db),
        application_installation_id=str(installation_id), incarnation=current.incarnation,
        module_id=current.module_id)
    app = db.get(Installation, installation_id, populate_existing=True)
    # A first inert registration may still lack another connector's required
    # keys. Full schema/resource validation still gates consent/preparation.
    return {'principal': principal.model_dump(mode='json'), 'package_id': pin.module_package_id,
        'version': pin.version, 'sha256': pin.sha256, 'instance_id': app.instance_id,
        'previous_package_id': app.previous_package_id,
        'configuration': key._fingerprint_in_snapshot(db, principal,
            _bounded_json(app.configuration)).model_dump(mode='json')}


def transition_id(identifier, revision, binding):
    return _id(b'3mm:inert-configuration-transition:v1\0', {
        'registration': identifier, 'revision': revision, 'binding': binding})


def binding_matches(db, key, installation_id, identifier, revision, original, current):
    if original == current:
        return True
    if ({k: v for k, v in original.items() if k != 'configuration'} !=
            {k: v for k, v in current.items() if k != 'configuration'}):
        return False
    marker = transition_id(identifier, revision, current)
    try:
        value = authority._load(db, key, 'action', db.get(Action, marker), marker)
        return (value['installation_id'] == installation_id
            and value['state'] == 'configuration_prepared_not_started'
            and value['data']['operation'] == 'connector_configuration_binding'
            and value['data']['source_registration'] == identifier
            and value['data']['source_revision'] == revision
            and value['data']['binding'] == current)
    except (authority.AuthorityManagementError, KeyError, ValueError, TypeError):
        return False


def verify_registration(db, key, installation_id, pin, package):
    marker = registration_id(db, installation_id)
    proof = authority._load(db, key, 'action', db.get(Action, marker), marker)
    if (proof['state'] != 'connector_registered_not_started'
            or proof['data'].get('operation') != 'connector_first_registration'
            or not binding_matches(db, key, installation_id, marker, proof['revision'],
                proof['data']['binding'], _binding(db, key, installation_id, pin, package))):
        raise authority.AuthorityManagementError('registration_unavailable')


def current_registration(db, key, installation_id, pin, package):
    """Authenticate existing provenance before preparing a configuration change."""
    from backend.services import application_package_staging as staging
    from backend.services import application_relational_registration as relational
    # Match code-identity resolution: the current package's explicit staging
    # proof takes precedence over a first-registration marker from an old version.
    marker = staging.registration_id(db, installation_id, pin.module_package_id, pin.sha256)
    if db.get(Action, marker) is not None:
        staging.verify_registration(db, key, installation_id, pin, package)
        binding = lambda: staging._binding(db, key, installation_id, pin.module_package_id, package)
    else:
        marker = registration_id(db, installation_id)
        if db.get(Action, marker) is not None:
            verify_registration(db, key, installation_id, pin, package)
            binding = lambda: _binding(db, key, installation_id, pin, package)
        else:
            relational.verify_registration(db, key, installation_id, pin, package)
            marker = relational.candidate_registration_id(db, installation_id, pin)
            if db.get(Action, marker) is None:
                marker = relational.registration_id(db, installation_id)
            binding = lambda: relational._binding(db, key, installation_id, pin, package)
    proof = authority._load(db, key, 'action', db.get(Action, marker), marker)
    return marker, proof, binding


def record_transition(db, key, installation_id, source, actor):
    marker, original, current_binding = source
    binding = current_binding()
    if original['data']['binding'] == binding:
        return
    identifier = transition_id(marker, original['revision'], binding)
    existing = db.get(Action, identifier)
    if existing is not None:
        if not binding_matches(db, key, installation_id, marker, original['revision'],
                original['data']['binding'], binding):
            raise authority.AuthorityManagementError('request_conflict')
        return
    authority._save(db, key, 'action', Action(request_id=identifier, installation_id=installation_id),
        authority._envelope('action', identifier, installation_id, 'configuration_prepared_not_started', {
            'operation': 'connector_configuration_binding', 'actor': actor,
            'source_registration': marker, 'source_revision': original['revision'], 'binding': binding}))
