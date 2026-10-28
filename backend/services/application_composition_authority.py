"""One-hop query resources in M20's existing sealed consent/grant framework.

Only Core reconstructs these models. None is a transport ticket, a sandbox or
permission to dispatch a request. Artifact I/O finishes before key/guard leases.
"""
from typing import Literal
import re

from pydantic import Field, model_validator
from sqlalchemy import select

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_context import (
    ContextModel, AuthorityPrincipal, AuthorityArtifact, ConfigurationIdentity,
    Digest, Identity, Revision, QueryScopeKey, AuthorityQueryPolicyV12,
    AuthorityReviewContextV1, AuthoritySelectionV1,
)
from backend.services.application_authority_policy import PolicySubjectV1, CorePolicyEvidenceV1
from three_mm_protocol.application_composition import (
    ApplicationQueryDependencyV1, ApplicationQueryExportV1,
)


class ResolvedQueryScope(ContextModel):
    declaration: ApplicationQueryDependencyV1
    export: ApplicationQueryExportV1
    owner: AuthorityPrincipal
    owner_instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    package_artifact_sha256: Digest
    provider: AuthorityPrincipal
    provider_instance_id: str = Field(pattern=r'^[0-9a-f]{24}$')
    provider_artifact: AuthorityArtifact
    provider_configuration: ConfigurationIdentity
    provider_authority_epoch: Identity
    provider_grant_revision: Revision
    provider_grant_record_revision: str = Field(pattern=r'^[0-9a-f]{32}$')
    contract_digest: Digest

    @model_validator(mode='after')
    def exact_contract(self):
        if (self.owner.core_installation_id != self.provider.core_installation_id
                or self.owner.application_installation_id == self.provider.application_installation_id
                or self.owner.module_id == self.provider.module_id
                or self.owner_instance_id == self.provider_instance_id
                or self.declaration.contract.digest() != self.export.contract.digest()
                or self.contract_digest != self.export.contract.digest()):
            raise ValueError('Query scope requires distinct local principals and an exact contract')
        return self


def validate_queries(value, principal, artifact):
    if value.commands or value.connectors or not value.queries:
        raise ValueError('Query authority requires the one-hop query-only profile')
    ids = set()
    for query in value.queries:
        if (query.owner != principal or query.package_artifact_sha256 != artifact
                or query.declaration.binding_id in ids):
            raise ValueError('Queries require distinct exact owned declarations')
        ids.add(query.declaration.binding_id)


class QueryPolicySubjectV12(PolicySubjectV1):
    subject_version: Literal[12]
    queries: tuple[ResolvedQueryScope, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def exact_owned(self):
        validate_queries(self, self.binding.principal, self.binding.candidate.sha256)
        return self


class QueryPolicyEvidenceV12(CorePolicyEvidenceV1):
    evidence_version: Literal[12]
    queries: tuple[ResolvedQueryScope, ...] = Field(min_length=1, max_length=16)
    required_scopes: tuple[QueryScopeKey, ...] = Field(max_length=16)

    @model_validator(mode='after')
    def exact_owned(self):
        validate_queries(self, self.binding.principal, self.binding.candidate.sha256)
        return self


class QueryReviewContextV12(AuthorityReviewContextV1):
    context_version: Literal[12]
    policy: AuthorityQueryPolicyV12
    queries: tuple[ResolvedQueryScope, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode='after')
    def exact_owned(self):
        validate_queries(self, self.principal, self.candidate.sha256)
        return self


class QuerySelectionV12(AuthoritySelectionV1):
    selection_version: Literal[12]
    scopes: tuple[QueryScopeKey, ...] = Field(max_length=16)


def prepare_providers(manager, prepared):
    """Read explicit saved choices and validate selected packages before locking."""
    from backend.services.application_authority_sources import _read_snapshot, _package_pin, _configuration, _Unavailable
    from backend.services.application_authority_management import AuthorityManagementError
    app = prepared.package.application_extension
    if not app.query_dependencies:
        return {}
    with _read_snapshot(manager.engine) as db:
        installation_id = db.scalar(select(Installation.id).where(
            Installation.module_id == prepared.pin.module_id))
        if _package_pin(db, installation_id) != prepared.pin:
            raise AuthorityManagementError('artifact_unavailable')
        try:
            configuration = _configuration(db, installation_id, prepared.package)
        except (ValueError, _Unavailable):
            return {}  # Unresolved choice cannot manufacture a provider.
        ids = {value for item in app.query_dependencies
               if isinstance(value := configuration.get(item.provider_instance_config_key), str)
               and re.fullmatch(r'[0-9a-f]{24}', value)}
        choices = dict(db.execute(select(Installation.instance_id, Installation.id).where(
            Installation.instance_id.in_(ids))).all())
    result = {}
    for instance, identifier in choices.items():
        # Never recurse into a provider's dependencies or implicitly form a chain.
        if identifier == installation_id:
            continue
        try:
            provider = manager._prepare(identifier, include_queries=False)
            if not provider.package.application_extension.query_dependencies:
                result[instance] = (identifier, provider)
        except (AuthorityManagementError, ValueError, OSError, _Unavailable):
            pass  # The authoritative resolver refuses missing/stale choices.
    return result


def resolve_queries(manager, db, key, installation_id, prepared, *, proposed_configuration=None):
    from backend.services.application_authority_sources import _configuration, _resolve_code_identity
    from backend.services.application_authority_management import AuthorityManagementError
    from backend.services.authority_metadata import read_application_authority
    from three_mm_protocol.application_composition import assess_application_query

    app = prepared.package.application_extension
    if not app.query_dependencies:
        return ()
    _, _, owner = _resolve_code_identity(db, installation_id, *prepared, registration_key=key)
    configuration = _configuration(db, installation_id, prepared.package, proposed=proposed_configuration)
    owner_instance = db.scalar(select(Installation.instance_id).where(Installation.id == installation_id))
    resources = []
    for dependency in app.query_dependencies:
        instance = configuration.get(dependency.provider_instance_config_key)
        export_id = configuration.get(dependency.provider_export_config_key)
        selected = prepared.query_providers.get(instance) if type(instance) is str else None
        if selected is None or type(export_id) is not str:
            raise AuthorityManagementError('query_binding_unavailable')
        provider_id, provider = selected
        if provider.package.application_extension.storage.relational is not None:
            raise AuthorityManagementError('query_profile_unsupported')
        # This check and all grant/source reads share the caller's guard snapshot.
        row = db.get(Installation, provider_id, populate_existing=True)
        if row is None or row.instance_id != instance or not row.enabled or row.status != 'active':
            raise AuthorityManagementError('query_binding_unavailable')
        current = read_application_authority(db, provider_id)
        grant = manager._require_current_grant(db, key, provider_id, provider)
        provider_subject = manager._subject(db, key, provider_id, provider)
        result = assess_application_query(app, provider.package.application_extension,
            binding_id=dependency.binding_id, export_id=export_id)
        if not result.compatible:
            raise AuthorityManagementError('query_contract_mismatch')
        export = next(item for item in provider.package.application_extension.query_exports
                      if item.export_id == export_id)
        resources.append(ResolvedQueryScope(declaration=dependency, export=export, owner=owner,
            owner_instance_id=owner_instance, package_artifact_sha256=prepared.pin.sha256,
            provider=provider_subject.binding.principal, provider_instance_id=instance,
            provider_artifact=provider_subject.binding.candidate,
            provider_configuration=provider_subject.binding.configuration,
            provider_authority_epoch=current.epoch,
            provider_grant_revision=grant['data']['grant_revision'],
            provider_grant_record_revision=grant['revision'], contract_digest=result.contract_digest))
    return tuple(resources)
