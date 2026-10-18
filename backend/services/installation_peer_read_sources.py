"""Exact public peer snapshots, NOT approval, a grant or an SDK entry point.

The Core caller supplies an already validated, digest-pinned package and owns a
consistent read transaction. Future admission must resolve it again under the
authority guard and compare its complete binding. This primitive never changes
the scoped dispatch allowlist or authenticates/authorizes its caller.
"""

from datetime import UTC, datetime
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import Text, cast, func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.db.installation_peer import (
    InstallationPeerInbound,
    InstallationPeerOutbound,
    InstallationPeerOrigin,
)
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_authority_context import (
    AuthorityPrincipal,
    MAX_CONTEXT_BYTES,
    ResolvedPeerReadScope,
)
from backend.services.application_configuration import resolve_application_configuration
from backend.services.installation_identity import read_existing_installation_identity
from backend.services.installation_status_binding import _consent, _public_identity
from backend.services.module_packages import ValidatedModulePackage
from three_mm_protocol.installation_identity import (
    InstallationProofRequestV1,
)
from three_mm_protocol.installation_peer import (
    PEER_ID_PATTERN,
    PEER_MAX_BYTES,
    PeerEnrollmentStartV1,
    canonical_json,
    enrollment_resource,
    enrollment_start_bytes,
    verify_signature,
)
from three_mm_protocol.installation_peer_v2 import (
    normalized_consent,
    parse_peer,
)


MAX_SOURCE_BYTES = MAX_CONTEXT_BYTES


class _SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Keep the internal source's existing name without two drifting definitions.
# This shared strict type still carries no authenticated approval or live grant.
PeerReadBinding = ResolvedPeerReadScope


class PeerReadObservation(_SourceModel):
    """Changing state is not permission identity or a fresh credential/PoP."""

    state: Literal["new", "pending", "active"]
    generation: int | None = Field(default=None, strict=True, ge=1, le=2**53 - 1)
    remote_binding_id: str | None = Field(default=None, pattern=PEER_ID_PATTERN)
    approval_expires_at: AwareDatetime | None = None


class ExistingPeerReadSource(_SourceModel):
    source_kind: Literal["existing_peer_read_source"] = "existing_peer_read_source"
    reviewable: Literal[False] = False
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    binding: PeerReadBinding
    observation: PeerReadObservation


def _bounded_column(column, maximum):
    # Bound JSON/text in SQL before loading it. Character count is portable;
    # strict canonical-JSON byte ceilings are rechecked after decoding as well.
    return func.length(cast(column, Text)) <= maximum


def _start(value):
    if type(value) is not dict or len(canonical_json(value)) > PEER_MAX_BYTES:
        raise ValueError()
    start = parse_peer(PeerEnrollmentStartV1, value)
    verify_signature(start.sender, start.signature, enrollment_start_bytes(start))
    return start


def _application(db, installation_id, package, allow_stopped):
    app = ApplicationExtensionInstallation.__table__.c
    stored = ModulePackage.__table__.c
    row = db.execute(
        select(
            app.module_id,
            app.instance_id,
            app.enabled,
            app.status,
            app.authority_incarnation,
            app.configuration,
            app.active_version,
            stored.version,
            stored.sha256,
            stored.module_id.label("package_module_id"),
        )
        .join(ModulePackage.__table__, app.module_package_id == stored.id)
        .where(
            app.id == installation_id,
            app.module_id == package.manifest.module_id,
            stored.module_id == package.manifest.module_id,
            stored.version == package.manifest.version,
            stored.sha256 == package.sha256,
            app.active_version == stored.version,
            _bounded_column(app.configuration, 32 * 1024),
            _bounded_column(app.instance_id, 24),
            _bounded_column(app.authority_incarnation, 32),
        )
    ).one_or_none()
    if (
        row is None
        or row.module_id != package.manifest.module_id
        or row.module_id != row.package_module_id
        or row.version != package.manifest.version
        or row.active_version != row.version
        or row.sha256 != package.sha256
        or not (
            (row.enabled is True and row.status == "active")
            or (allow_stopped and row.enabled is False and row.status == "disabled")
        )
        or type(row.configuration) is not dict
        or re.fullmatch(r"[0-9a-f]{24}", row.instance_id or "") is None
        or re.fullmatch(r"[0-9a-f]{32}", row.authority_incarnation or "") is None
    ):
        raise ValueError()
    configuration = resolve_application_configuration(
        package.manifest.configuration_schema,
        {},
        package.application_extension,
        existing=row.configuration,
    )
    return row, configuration


def _peer(db, app, declaration, peer_id):
    inbound = declaration.direction == "inbound"
    c = (InstallationPeerInbound if inbound else InstallationPeerOutbound).__table__.c
    names = [
        "module_id",
        "application_instance_id",
        "sender_identity",
        "receiver_identity",
        "origin",
        "state",
        "start_request",
    ]
    names += (
        [
            "binding_id",
            "sender_id",
            "request_id",
            "completed_digest",
            "generation",
            "approval_expires_at",
        ]
        if inbound
        else [
            "link_id",
            "target_module_id",
            "consent_revision",
            "consent",
            "remote_binding_id",
        ]
    )
    key = c.binding_id if inbound else c.link_id
    predicates = [
        key == peer_id,
        c.module_id == app.module_id,
        c.application_instance_id == app.instance_id,
        c.state.in_(("pending", "active") if inbound else ("new", "pending", "active")),
        _bounded_column(c.sender_identity, 4096),
        _bounded_column(c.receiver_identity, 4096),
        _bounded_column(c.start_request, PEER_MAX_BYTES),
        _bounded_column(c.origin, 255),
    ]
    if not inbound:
        predicates.extend(
            [
                _bounded_column(c.consent, 16 * 1024),
                _bounded_column(c.target_module_id, 160),
            ]
        )
    else:
        predicates.extend(
            [
                _bounded_column(c.completed_digest, 64),
                _bounded_column(c.sender_id, 37),
                _bounded_column(c.request_id, 37),
            ]
        )
    row = db.execute(
        select(*(c[name] for name in names)).where(*predicates)
    ).one_or_none()
    if row is None:
        raise ValueError()
    return row


def _read_one(db, app, definition, declaration, peer_id, identity, owner, package):
    row = _peer(db, app, declaration, peer_id)
    sender = _public_identity(row.sender_identity)
    receiver = _public_identity(row.receiver_identity)
    origin = InstallationProofRequestV1.canonical_origin(row.origin)
    if origin != row.origin or sender.installation_id == receiver.installation_id:
        raise ValueError()
    start = _start(row.start_request)
    metadata = getattr(start, "enrollment_metadata", None)
    challenge = start.receiver_challenge
    # Public signature and exact persisted pins, not a new live possession proof.
    if (
        start.sender != sender
        or start.receiver != receiver
        or challenge.audience != origin
        or challenge.receiver_installation_id != sender.installation_id
        or challenge.receiver_key_id != sender.key_id
        or challenge.receiver_key_generation != sender.key_generation
        or challenge.resource
        != enrollment_resource(
            start.request_id, start.target_module_id, start.scopes, metadata
        )
    ):
        raise ValueError()
    if declaration.direction == "outbound":
        if (
            identity != sender
            or start.request_id != row.link_id
            or start.target_module_id != row.target_module_id
        ):
            raise ValueError()
        consent = normalized_consent(_consent(row.consent))
        revision = row.consent_revision
        if metadata is not None and (
            metadata.consent != consent or metadata.consent_revision != revision
        ):
            raise ValueError()
        if row.state in ("pending", "active") and row.remote_binding_id is None:
            raise ValueError()
        observation = PeerReadObservation(
            state=row.state, remote_binding_id=row.remote_binding_id
        )
        target = row.target_module_id
    else:
        configured = db.scalar(
            select(InstallationPeerOrigin.origin).where(
                InstallationPeerOrigin.singleton_id == 1,
                InstallationPeerOrigin.origin == origin,
            )
        )
        if (
            identity != receiver
            or row.sender_id != sender.installation_id
            or start.request_id != row.request_id
            or start.target_module_id != app.module_id
            or configured != origin
            or definition.peer_receiver is None
            or definition.peer_receiver.peer_version != start.peer_version
            or type(row.completed_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", row.completed_digest) is None
        ):
            raise ValueError()
        expires = row.approval_expires_at
        if not isinstance(expires, datetime):
            raise ValueError()
        if expires.tzinfo is None:  # Existing SQLite UTC storage contract.
            expires = expires.replace(tzinfo=UTC)
        observation = PeerReadObservation(
            state=row.state, generation=row.generation, approval_expires_at=expires
        )
        target = app.module_id
        consent = metadata.consent if metadata else None
        revision = metadata.consent_revision if metadata else None
    resource = PeerReadBinding(
        declaration=declaration,
        owner=owner,
        package_artifact_sha256=package.sha256,
        service_artifact_sha256=definition.service.artifact_sha256,
        application_instance_id=app.instance_id,
        peer_id=peer_id,
        peer_version=start.peer_version,
        sender_identity=sender,
        receiver_identity=receiver,
        origin=origin,
        target_module_id=target,
        consent_revision=revision,
        consent=consent,
        enrollment_metadata=metadata,
    )
    return ExistingPeerReadSource(binding=resource, observation=observation)


def read_configured_peer_sources(db, installation_id, package, *, allow_stopped=False):
    """Resolve every exact read request, or refuse the complete requested family.

    There is no peer selector/configuration/identity payload from an SDK caller.
    Missing, unsupported or aliased requests refuse the whole family. A returned
    source is stale as soon as the caller's snapshot ends and grants no access.
    The caller must prepare/validate the actual package before this transaction.
    """
    try:
        if (
            type(installation_id) is not int
            or installation_id < 1
            or type(allow_stopped) is not bool
            or not isinstance(package, ValidatedModulePackage)
            or package.application_extension is None
        ):
            raise ValueError()
        definition = package.application_extension
        declarations = definition.peer_bindings
        if not declarations:
            return ()
        if definition.service.sdk_version != "1.3" or any(
            item.operations != ("read",) for item in declarations
        ):
            raise ValueError()
        with db.no_autoflush:
            app, configuration = _application(
                db, installation_id, package, allow_stopped
            )
            selections = [
                (item, configuration.get(item.peer_id_config_key))
                for item in declarations
            ]
            if any(
                type(peer_id) is not str
                or re.fullmatch(PEER_ID_PATTERN, peer_id) is None
                for _, peer_id in selections
            ):
                raise ValueError()
            if len({(item.direction, peer_id) for item, peer_id in selections}) != len(
                selections
            ):
                raise ValueError()
            identity = read_existing_installation_identity(db)
            owner = AuthorityPrincipal(
                core_installation_id=identity.installation_id,
                application_installation_id=str(installation_id),
                incarnation=app.authority_incarnation,
                module_id=app.module_id,
            )
            sources = tuple(
                _read_one(db, app, definition, item, peer_id, identity, owner, package)
                for item, peer_id in sorted(
                    selections, key=lambda pair: pair[0].binding_id
                )
            )
            if (
                len(canonical_json([item.model_dump(mode="json") for item in sources]))
                > MAX_SOURCE_BYTES
            ):
                raise ValueError()
            return sources
    except (
        ValueError,
        RuntimeError,
        SQLAlchemyError,
        TypeError,
        AttributeError,
        KeyError,
        RecursionError,
        OverflowError,
    ):
        # No raw configuration, opaque intent, DB errors or partial resources.
        raise ValueError("Existing peer read sources are unavailable") from None
