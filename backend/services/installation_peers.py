"""Durable dual-consent peers, PoP credentials and outgoing-only status delivery."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.device import Device
from backend.db.installation_peer import (
    InstallationPeerOrigin,
    InstallationPeerInbound,
    InstallationPeerOutbound,
    InstallationPeerNonce,
    InstallationPeerAudit,
)
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_access import (
    ApplicationPrincipal,
    can_access_application_operation,
)
from backend.services.application_extensions import (
    load_application_definition,
    invoke_application,
    find_operation,
    ApplicationGatewayError,
)
from backend.services.device_registry import as_utc
from backend.services.installation_identity import (
    _load_or_create,
    prove_installation_identity,
)
from backend.services.installation_projection import installation_projection
from three_mm_protocol.installation_identity import (
    InstallationIdentityV1,
    InstallationProofRequestV1,
    verify_installation_proof,
)
from three_mm_protocol.installation_peer import (
    PEER_PREFIX,
    PEER_SCOPE,
    PEER_MAX_BYTES,
    PeerEnrollmentStartV1,
    PeerEnrollmentChallengeV1,
    PeerEnrollmentCompleteV1,
    PeerEnrollmentResultV1,
    PeerCredentialClaimsV1,
    PeerCredentialV1,
    PeerRequestV1,
    PeerReportV1,
    ProjectionConsentV1,
    InstallationProjectionV1,
    canonical_json,
    credential_bytes,
    request_bytes,
    verify_signature,
    verify_peer_credential,
    enrollment_resource,
    enrollment_start_bytes,
)
from three_mm_protocol.installation_peer_v2 import (
    PEER_V2_PREFIX,
    PeerCapabilitiesV2,
    enrollment_metadata,
    normalized_consent,
    parse_peer,
    peer_model,
)


def _version(row):
    return parse_peer(PeerEnrollmentStartV1, row.start_request).peer_version


def _metadata(row):
    return getattr(
        parse_peer(PeerEnrollmentStartV1, row.start_request),
        "enrollment_metadata",
        None,
    )


def _prefix(row):
    return PEER_V2_PREFIX if _version(row) == 2 else PEER_PREFIX


def peer_capabilities():
    return PeerCapabilitiesV2().model_dump(mode="json")


def _verify_projection(projection, metadata):
    consent = metadata.consent
    if (
        projection.consent_revision != metadata.consent_revision
        or set(projection.summary) != set(consent.summary_fields)
        or {node.device_id for node in projection.nodes} != set(consent.node_ids)
        or any(
            set(node.fields) != set(consent.node_fields) for node in projection.nodes
        )
    ):
        _deny("Projection differs from the receiver-approved consent")


class InstallationPeerError(RuntimeError):
    pass


def _deny(message="Installation peer request is unavailable or not authorized"):
    raise InstallationPeerError(message)


def _audit(
    db,
    action,
    peer_id,
    *,
    user_id=None,
    generation=None,
    actor_kind="core",
    actor_id=None,
):
    if user_id is not None:
        db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entity_type="installation_peer",
                entity_name=peer_id,
                changes={"generation": generation} if generation is not None else {},
            )
        )
    db.add(
        InstallationPeerAudit(
            event_id=uuid.uuid4().hex,
            peer_id=peer_id,
            action=action,
            actor_kind="user" if user_id is not None else actor_kind,
            actor_id=str(user_id) if user_id is not None else actor_id,
            generation=generation,
            created_at=datetime.now(UTC),
        )
    )


def _application(db, module_id, *, permission=None, receiver=False):
    application = db.scalar(
        select(ApplicationExtensionInstallation)
        .where(ApplicationExtensionInstallation.module_id == module_id)
        .execution_options(populate_existing=True)
    )
    if application is None or not application.enabled or application.status != "active":
        _deny("Application installation is not active")
    package = db.get(ModulePackage, application.module_package_id)
    if (
        package is None
        or package.version != application.active_version
        or package.module_id != application.module_id
    ):
        _deny("Application package is unavailable")
    definition = load_application_definition(package)
    if (
        definition.service.sdk_version not in ("1.2", "1.3")
        or permission
        and permission not in definition.platform_permissions
        or receiver
        and definition.peer_receiver is None
    ):
        _deny("Installation peer contract or permission is not declared")
    return application, package, definition


def configured_origin(db) -> str:
    row = db.get(InstallationPeerOrigin, 1)
    if row is None:
        _deny("Installation peer HTTPS origin is not configured")
    return InstallationProofRequestV1.canonical_origin(row.origin)


def configure_origin(db, origin: str, *, user_id):
    origin = InstallationProofRequestV1.canonical_origin(origin)
    row = db.get(InstallationPeerOrigin, 1)
    if (
        row is not None
        and row.origin != origin
        and db.scalar(
            select(func.count())
            .select_from(InstallationPeerInbound)
            .where(InstallationPeerInbound.state != "revoked")
        )
    ):
        _deny("Revoke existing incoming bindings before changing their HTTPS origin")
    if row is None:
        db.add(InstallationPeerOrigin(singleton_id=1, origin=origin))
    else:
        row.origin = origin
    _audit(db, "INSTALLATION_PEER_ORIGIN_CONFIGURED", "origin", user_id=user_id)
    db.commit()
    return {"origin": origin}


def _lock(db, model, key):
    identity = model.binding_id if model is InstallationPeerInbound else model.link_id
    if (
        db.execute(
            update(model).where(identity == key).values(updated_at=model.updated_at)
        ).rowcount
        != 1
    ):
        _deny()
    return db.scalar(
        select(model).where(identity == key).execution_options(populate_existing=True)
    )


def _live_inbound(db, row):
    if row is None:
        _deny()
    application, package, definition = _application(
        db, row.module_id, permission="installation.peers.receive", receiver=True
    )
    identity, _ = _load_or_create(db)
    if (
        row.state == "revoked"
        or row.application_instance_id != application.instance_id
        or row.receiver_identity != identity.model_dump(mode="json")
        or row.origin != configured_origin(db)
        or row.state != "renewable"
        and definition.peer_receiver.peer_version != _version(row)
    ):
        _deny()
    return application, package, definition


def _live_outbound(db, row, application):
    if (
        row.module_id != application.module_id
        or row.application_instance_id != application.instance_id
        or row.state == "revoked"
    ):
        _deny("Local peer consent is unavailable or withdrawn")
    current, _, definition = _application(
        db, application.module_id, permission="installation.peers.enroll"
    )
    identity, _ = _load_or_create(db)
    if (
        row.sender_identity != identity.model_dump(mode="json")
        or current.instance_id != application.instance_id
    ):
        _deny("Local installation identity changed")
    metadata = _metadata(row)
    if metadata is not None and (
        definition.service.sdk_version != "1.3"
        or metadata.consent_revision != row.consent_revision
        or metadata.consent.model_dump(mode="json") != row.consent
    ):
        _deny("Local peer metadata or SDK version changed")


def create_outbound(
    db,
    application,
    *,
    origin,
    receiver_identity,
    target_module_id,
    consent,
    user_id,
    peer_version=1,
    application_intent=None,
):
    _, _, definition = _application(
        db, application.module_id, permission="installation.peers.enroll"
    )
    peer_model(PeerEnrollmentStartV1, peer_version)
    if peer_version == 2 and definition.service.sdk_version != "1.3":
        _deny("Proof-bound enrollment metadata requires SDK 1.3")
    if peer_version == 1 and application_intent is not None:
        _deny("Application intent requires peer v2")
    if (
        db.scalar(
            select(func.count())
            .select_from(InstallationPeerOutbound)
            .where(
                InstallationPeerOutbound.module_id == application.module_id,
                InstallationPeerOutbound.state != "revoked",
            )
        )
        >= 32
    ):
        _deny("An application may have at most 32 non-revoked outgoing links")
    origin = InstallationProofRequestV1.canonical_origin(origin)
    receiver = InstallationIdentityV1.model_validate(receiver_identity)
    selection = ProjectionConsentV1.model_validate(consent)
    metadata = (
        enrollment_metadata(application_intent, selection)
        if peer_version == 2
        else None
    )
    if metadata is not None:
        selection = metadata.consent
    available = set(
        db.scalars(
            select(Device.device_id).where(
                Device.device_id.in_(selection.node_ids), Device.revoked_at.is_(None)
            )
        )
    )
    if set(selection.node_ids) - available:
        _deny("Select only currently registered, non-revoked Nodes")
    identity, _ = _load_or_create(db)
    if receiver.installation_id == identity.installation_id:
        _deny("An installation cannot enroll itself")
    now = datetime.now(UTC)
    # Validate module ID through the shared start schema, before inserting state.
    link_id = f"peer_{uuid.uuid4().hex}"
    start = _signed_start(
        db, link_id, target_module_id, receiver, origin, now, metadata
    )
    row = InstallationPeerOutbound(
        link_id=link_id,
        module_id=application.module_id,
        application_instance_id=application.instance_id,
        sender_identity=identity.model_dump(mode="json"),
        receiver_identity=receiver.model_dump(mode="json"),
        origin=origin,
        target_module_id=target_module_id,
        consent=selection.model_dump(mode="json"),
        consent_revision=1,
        state="new",
        start_request=start.model_dump(mode="json"),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit(
        db, "INSTALLATION_PEER_LOCAL_CONSENT", link_id, user_id=user_id, generation=1
    )
    db.commit()
    return outbound_status(row)


def _challenge(receiver, origin, resource, now):
    return InstallationProofRequestV1(
        challenge=secrets.token_urlsafe(32),
        receiver_installation_id=receiver.installation_id,
        receiver_key_id=receiver.key_id,
        receiver_key_generation=receiver.key_generation,
        audience=origin,
        resource=resource,
        created_at=now,
        expires_at=now + timedelta(seconds=120),
    )


def _signed_start(db, link_id, target_module_id, receiver, origin, now, metadata=None):
    identity, private = _load_or_create(db)
    challenge = _challenge(
        identity,
        origin,
        enrollment_resource(link_id, target_module_id, (PEER_SCOPE,), metadata),
        now,
    )
    start = peer_model(PeerEnrollmentStartV1, 2 if metadata else 1)(
        **({"enrollment_metadata": metadata} if metadata else {}),
        request_id=link_id,
        target_module_id=target_module_id,
        sender=identity,
        receiver=receiver,
        receiver_challenge=challenge,
        signature=base64.b64encode(bytes(64)).decode(),
    )
    return start.model_copy(
        update={
            "signature": base64.b64encode(
                private.sign(enrollment_start_bytes(start))
            ).decode()
        }
    )


def enrollment_start(db, value, *, origin, now=None, peer_version=1):
    now = now or datetime.now(UTC)
    start = parse_peer(PeerEnrollmentStartV1, value, version=peer_version)
    metadata = getattr(start, "enrollment_metadata", None)
    application, _, definition = _application(
        db,
        start.target_module_id,
        permission="installation.peers.receive",
        receiver=True,
    )
    if definition.peer_receiver.peer_version != start.peer_version:
        _deny("Receiving application does not declare this peer version")
    receiver, _ = _load_or_create(db)
    if receiver != start.receiver:
        _deny("Pinned receiver installation identity changed")
    verify_signature(start.sender, start.signature, enrollment_start_bytes(start))
    resource = enrollment_resource(
        start.request_id, start.target_module_id, start.scopes, metadata
    )
    expected = start.receiver_challenge
    if (
        origin != configured_origin(db)
        or expected.audience != origin
        or expected.resource != resource
        or expected.receiver_installation_id != start.sender.installation_id
        or expected.receiver_key_id != start.sender.key_id
        or expected.receiver_key_generation != start.sender.key_generation
        or start.sender.installation_id == receiver.installation_id
    ):
        _deny("Enrollment receiver, resource or origin binding is invalid")
    # Produce the pinned receiver proof only for a still-valid caller challenge.
    receiver_proof = prove_installation_identity(db, expected, now=now)
    row = db.scalar(
        select(InstallationPeerInbound).where(
            InstallationPeerInbound.module_id == application.module_id,
            InstallationPeerInbound.sender_id == start.sender.installation_id,
        )
    )
    if row is None:
        # Bound unauthenticated bootstrap state; approval cannot be automatic.
        db.execute(
            delete(InstallationPeerInbound).where(
                InstallationPeerInbound.state.in_(["challenged", "pending"]),
                InstallationPeerInbound.approval_expires_at < now - timedelta(hours=24),
            )
        )
        if (
            db.scalar(
                select(func.count())
                .select_from(InstallationPeerInbound)
                .where(
                    InstallationPeerInbound.state.in_(["challenged", "pending"]),
                    InstallationPeerInbound.approval_expires_at > now,
                )
            )
            >= 256
        ):
            _deny("Installation enrollment queue is full")
        row = InstallationPeerInbound(
            binding_id=f"peer_{uuid.uuid4().hex}",
            module_id=application.module_id,
            application_instance_id=application.instance_id,
            sender_id=start.sender.installation_id,
            sender_identity=start.sender.model_dump(mode="json"),
            receiver_identity=receiver.model_dump(mode="json"),
            origin=origin,
            request_id=start.request_id,
            start_request=start.model_dump(mode="json"),
            sender_challenge=_challenge(receiver, origin, resource, now).model_dump(
                mode="json"
            ),
            state="challenged",
            generation=1,
            approval_expires_at=now + timedelta(minutes=15),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.scalar(
                select(InstallationPeerInbound).where(
                    InstallationPeerInbound.module_id == application.module_id,
                    InstallationPeerInbound.sender_id == start.sender.installation_id,
                )
            )
            if row is None:
                _deny()
    row = _lock(db, InstallationPeerInbound, row.binding_id)
    _live_inbound(db, row)
    if row.sender_identity != start.sender.model_dump(mode="json"):
        _deny(
            "Installation ID already has another key binding; explicit review is required"
        )
    if row.request_id != start.request_id or row.start_request != start.model_dump(
        mode="json"
    ):
        old = InstallationProofRequestV1.model_validate(row.sender_challenge)
        previous = _metadata(row)
        renewed_consent = (
            metadata is not None
            and previous is not None
            and metadata.application_intent == previous.application_intent
            and metadata.consent_revision > previous.consent_revision
            and row.origin == origin
            and row.request_id == start.request_id
        )
        if (
            row.state != "renewable"
            and metadata is not None
            and previous != metadata
            and not renewed_consent
        ):
            _deny("Enrollment metadata changed without a newer consent revision")
        if (
            row.state != "renewable"
            and not renewed_consent
            and not (row.state == "challenged" and old.expires_at <= now)
        ):
            _deny(
                "Installation already has an enrollment or binding; explicit review is required"
            )
        if metadata is not None:
            row.generation += 1
        row.request_id = start.request_id
        row.start_request = start.model_dump(mode="json")
        row.sender_challenge = _challenge(receiver, origin, resource, now).model_dump(
            mode="json"
        )
        row.state = "challenged"
        row.completed_digest = row.credential = row.rotation_digest = None
        row.approval_expires_at = now + timedelta(minutes=15)
        row.updated_at = now
    result = peer_model(PeerEnrollmentChallengeV1, start.peer_version)(
        **({"enrollment_metadata": metadata} if metadata else {}),
        binding_id=row.binding_id,
        receiver_proof=receiver_proof,
        sender_challenge=InstallationProofRequestV1.model_validate(
            row.sender_challenge
        ),
    )
    db.commit()
    return result


def _result(row):
    metadata = _metadata(row)
    return peer_model(PeerEnrollmentResultV1, _version(row))(
        **({"enrollment_metadata": metadata} if metadata else {}),
        binding_id=row.binding_id,
        state=row.state,
        generation=row.generation,
        credential=(
            parse_peer(PeerCredentialV1, row.credential, version=_version(row))
            if row.credential
            else None
        ),
    )


def enrollment_complete(db, value, *, origin, now=None, peer_version=1):
    now = now or datetime.now(UTC)
    complete = parse_peer(PeerEnrollmentCompleteV1, value, version=peer_version)
    row = _lock(db, InstallationPeerInbound, complete.binding_id)
    _live_inbound(db, row)
    metadata = _metadata(row)
    if row.origin != origin or _version(row) != complete.peer_version:
        _deny()
    if metadata is not None and complete.metadata_hash != metadata.metadata_hash:
        _deny("Enrollment completion metadata does not match")
    digest = hashlib.sha256(
        canonical_json(complete.model_dump(mode="json"))
    ).hexdigest()
    if row.completed_digest:
        if digest != row.completed_digest:
            _deny("Enrollment completion was already consumed")
        # Exact retry returns a public receipt only, never another credential.
        result = _result(row)
        db.commit()
        return result
    verify_installation_proof(
        complete.sender_proof,
        expected_identity=row.sender_identity,
        expected_request=row.sender_challenge,
        now=now,
    )
    if row.state != "challenged" or as_utc(row.approval_expires_at) <= now:
        _deny("Enrollment expired or is not awaiting proof")
    row.completed_digest = digest
    row.state = "pending"
    row.updated_at = now
    _audit(
        db,
        "INSTALLATION_PEER_PROOF_ACCEPTED",
        row.binding_id,
        generation=row.generation,
        actor_kind="installation",
        actor_id=row.sender_id,
    )
    result = _result(row)
    db.commit()
    return result


def _issue(db, row, now):
    identity, private = _load_or_create(db)
    metadata = _metadata(row)
    claims = peer_model(PeerCredentialClaimsV1, _version(row))(
        **({"enrollment_metadata": metadata} if metadata else {}),
        binding_id=row.binding_id,
        issuer=identity,
        subject=InstallationIdentityV1.model_validate(row.sender_identity),
        origin=row.origin,
        target_module_id=row.module_id,
        generation=row.generation,
        issued_at=now,
        expires_at=now + timedelta(hours=24),
    )
    certificate = peer_model(PeerCredentialV1, _version(row))(
        claims=claims,
        signature=base64.b64encode(private.sign(credential_bytes(claims))).decode(),
    )
    row.credential = certificate.model_dump(mode="json")
    return certificate


def approve_inbound(
    db,
    application,
    binding_id,
    expected_generation,
    *,
    user_id=None,
    now=None,
    expected_metadata_revision=None,
    expected_metadata_hash=None,
):
    now = now or datetime.now(UTC)
    if type(expected_generation) is not int or expected_generation < 1:
        _deny("Expected generation is invalid")
    row = _lock(db, InstallationPeerInbound, binding_id)
    _live_inbound(db, row)
    if (
        row.module_id != application.module_id
        or row.application_instance_id != application.instance_id
        or row.generation != expected_generation
    ):
        _deny()
    metadata = _metadata(row)
    if metadata is not None:
        if (
            type(expected_metadata_revision) is not int
            or expected_metadata_revision != metadata.consent_revision
            or expected_metadata_hash != metadata.metadata_hash
        ):
            _deny("Reviewed enrollment metadata revision or hash changed")
    elif expected_metadata_revision is not None or expected_metadata_hash is not None:
        _deny("Metadata review requires peer v2")
    if row.state == "active":
        result = _result(row)
        db.commit()
        return result.model_dump(mode="json")
    if (
        row.state != "pending"
        or not row.completed_digest
        or as_utc(row.approval_expires_at) <= now
    ):
        _deny("Verified enrollment is expired, revoked or not awaiting approval")
    row.state = "active"
    row.updated_at = now
    _issue(db, row, now)
    _audit(
        db,
        "INSTALLATION_PEER_RECEIVER_APPROVED",
        binding_id,
        user_id=user_id,
        generation=row.generation,
        actor_kind="application",
        actor_id=application.instance_id,
    )
    result = _result(row)
    db.commit()
    return result.model_dump(mode="json")


def revoke_peer(db, application, peer_id, direction, *, user_id=None):
    model = (
        InstallationPeerInbound
        if direction == "inbound"
        else InstallationPeerOutbound if direction == "outbound" else None
    )
    if model is None:
        _deny("Peer direction is invalid")
    row = _lock(db, model, peer_id)
    if (
        row.module_id != application.module_id
        or row.application_instance_id != application.instance_id
    ):
        _deny()
    if row.state != "revoked":
        row.state = "revoked"
        row.updated_at = datetime.now(UTC)
        if direction == "inbound":
            row.generation += 1
            row.credential = None
        else:
            row.consent_revision += 1
            row.credential = None
            row.rotation_request = None
            row.report_id = row.report_projection = row.report_result = None
        _audit(
            db,
            "INSTALLATION_PEER_REVOKED",
            peer_id,
            user_id=user_id,
            actor_kind="application",
            actor_id=application.instance_id,
        )
    db.commit()
    return {"peer_id": peer_id, "state": "revoked"}


def update_consent(db, application, link_id, consent, expected_revision, *, user_id):
    row = _lock(db, InstallationPeerOutbound, link_id)
    _live_outbound(db, row, application)
    if type(expected_revision) is not int or row.consent_revision != expected_revision:
        _deny("Local consent revision changed")
    selection = ProjectionConsentV1.model_validate(consent)
    available = set(
        db.scalars(
            select(Device.device_id).where(
                Device.device_id.in_(selection.node_ids), Device.revoked_at.is_(None)
            )
        )
    )
    if set(selection.node_ids) - available:
        _deny("Select only currently registered, non-revoked Nodes")
    previous = _metadata(row)
    if previous is not None:
        selection = normalized_consent(selection)
        if selection == previous.consent:
            result = outbound_status(row)
            db.commit()
            return result
    row.consent = selection.model_dump(mode="json")
    row.consent_revision += 1
    row.report_id = row.report_projection = row.report_result = None
    row.updated_at = datetime.now(UTC)
    if previous is not None:
        metadata = enrollment_metadata(
            previous.application_intent, selection, row.consent_revision
        )
        row.start_request = _signed_start(
            db,
            row.link_id,
            row.target_module_id,
            InstallationIdentityV1.model_validate(row.receiver_identity),
            row.origin,
            row.updated_at,
            metadata,
        ).model_dump(mode="json")
        row.state = "new"
        row.credential = row.complete_request = row.rotation_request = None
    _audit(
        db,
        "INSTALLATION_PEER_LOCAL_CONSENT",
        link_id,
        user_id=user_id,
        generation=row.consent_revision,
    )
    db.commit()
    return outbound_status(row)


def reopen_inbound(db, application, peer_id, expected_generation, *, user_id):
    row = _lock(db, InstallationPeerInbound, peer_id)
    if (
        type(expected_generation) is not int
        or row.generation != expected_generation
        or row.module_id != application.module_id
        or row.state != "revoked"
    ):
        _deny("Only an explicitly reviewed, revoked binding may be reopened")
    _application(
        db,
        application.module_id,
        permission="installation.peers.receive",
        receiver=True,
    )
    row.application_instance_id = application.instance_id
    row.state = "renewable"
    row.completed_digest = row.credential = row.rotation_digest = None
    row.updated_at = datetime.now(UTC)
    _audit(
        db,
        "INSTALLATION_PEER_REENROLLMENT_ALLOWED",
        peer_id,
        user_id=user_id,
        generation=row.generation,
    )
    db.commit()
    return {"binding_id": peer_id, "state": "renewable", "generation": row.generation}


def invalidate_application_peers(db, module_id):
    """Uninstall keeps revocation tombstones; a reinstall cannot inherit trust."""
    now = datetime.now(UTC)
    db.execute(
        update(InstallationPeerInbound)
        .where(
            InstallationPeerInbound.module_id == module_id,
            InstallationPeerInbound.state != "revoked",
        )
        .values(
            state="revoked",
            credential=None,
            generation=InstallationPeerInbound.generation + 1,
            updated_at=now,
        )
    )
    db.execute(
        update(InstallationPeerOutbound)
        .where(
            InstallationPeerOutbound.module_id == module_id,
            InstallationPeerOutbound.state != "revoked",
        )
        .values(
            state="revoked",
            credential=None,
            rotation_request=None,
            report_id=None,
            report_projection=None,
            report_result=None,
            consent_revision=InstallationPeerOutbound.consent_revision + 1,
            updated_at=now,
        )
    )


def outbound_status(row):
    result = {
        "link_id": row.link_id,
        "state": row.state,
        "consent_revision": row.consent_revision,
        "consent": row.consent,
        "origin": row.origin,
        "receiver_identity": row.receiver_identity,
        "target_module_id": row.target_module_id,
        "remote_binding_id": row.remote_binding_id,
        "credential_expires_at": (
            row.credential.get("claims", {}).get("expires_at")
            if row.credential
            else None
        ),
    }
    metadata = _metadata(row)
    if metadata is not None:
        result.update(
            peer_version=2, enrollment_metadata=metadata.model_dump(mode="json")
        )
    return result


def _inbound_status(row):
    result = {
        "binding_id": row.binding_id,
        "sender_identity": row.sender_identity,
        "state": row.state,
        "generation": row.generation,
        "approval_expires_at": as_utc(row.approval_expires_at).isoformat(),
    }
    metadata = _metadata(row)
    if metadata is not None:
        result.update(
            peer_version=2,
            verified_metadata=(
                metadata.model_dump(mode="json")
                if row.completed_digest and row.state in ("pending", "active")
                else None
            ),
        )
    return result


def list_peers(db, application):
    incoming = list(
        db.scalars(
            select(InstallationPeerInbound)
            .where(InstallationPeerInbound.module_id == application.module_id)
            .order_by(InstallationPeerInbound.created_at.desc())
            .limit(100)
        )
    )
    outgoing = list(
        db.scalars(
            select(InstallationPeerOutbound)
            .where(InstallationPeerOutbound.module_id == application.module_id)
            .order_by(InstallationPeerOutbound.created_at.desc())
            .limit(100)
        )
    )
    return {
        "inbound": [_inbound_status(row) for row in incoming],
        "outbound": [outbound_status(row) for row in outgoing],
    }


def notify_bootstrap(db, binding_id):
    row = db.get(InstallationPeerInbound, binding_id)
    if row is None or row.state != "pending":
        return
    application, package, definition = _live_inbound(db, row)
    context = machine_context(row, "installation_bootstrap", f"enrollment:{binding_id}")
    payload = {
        "binding_id": binding_id,
        "installation_identity": row.sender_identity,
        "requested_scopes": [PEER_SCOPE],
    }
    metadata = _metadata(row)
    generation = row.generation
    if metadata is not None:
        payload["enrollment_metadata"] = metadata.model_dump(mode="json")
        context = machine_context(
            row,
            "installation_bootstrap",
            f"enrollment:{binding_id}:{generation}:{metadata.metadata_hash}",
        )
    db.commit()  # Owner's handler may approve through another SDK connection.

    def still_pending():
        db.expire_all()
        current = db.get(InstallationPeerInbound, binding_id)
        try:
            _live_inbound(db, current)
        except (InstallationPeerError, ApplicationGatewayError):
            return False
        return current.state == "pending" and current.generation == generation

    try:
        invoke_application(
            application,
            package,
            get_settings().applications,
            definition.peer_receiver.bootstrap_operation_id,
            payload,
            context,
            required_audience="installation_bootstrap",
            before_dispatch=still_pending,
        )
    except ApplicationGatewayError:
        # Durable pending state is discoverable through the receiver SDK/UI.
        # A callback timeout is not approval and must not issue credentials.
        return


def machine_context(row, audience, idempotency_key):
    return {
        "audience": audience,
        "correlation_id": uuid.uuid4().hex,
        "idempotency_key": idempotency_key,
        "machine": {
            "installation_id": row.sender_id,
            "key_id": row.sender_identity["key_id"],
            "binding_id": row.binding_id,
            "generation": row.generation,
            "scopes": [PEER_SCOPE] if audience == "installation_peer" else [],
        },
    }


def authenticate_request(
    db, value, *, origin, path, now=None, allow_rotation_receipt=False
):
    now = now or datetime.now(UTC)
    wire_version = 2 if path.startswith(PEER_V2_PREFIX + "/") else 1
    request = parse_peer(PeerRequestV1, value, version=wire_version)
    row = _lock(db, InstallationPeerInbound, request.credential.claims.binding_id)
    _live_inbound(db, row)
    if (
        row.state != "active"
        or row.origin != origin
        or request.path != path
        or _version(row) != request.peer_version
    ):
        _deny()
    digest = hashlib.sha256(canonical_json(request.model_dump(mode="json"))).hexdigest()
    if allow_rotation_receipt and row.rotation_digest == digest:
        # Exact durable receipt is public and cannot rotate/revive the binding.
        return row, request, True
    issuer = InstallationIdentityV1.model_validate(row.receiver_identity)
    subject = InstallationIdentityV1.model_validate(row.sender_identity)
    verify_peer_credential(
        request.credential,
        issuer=issuer,
        subject=subject,
        origin=origin,
        module_id=row.module_id,
        now=now,
    )
    if (
        row.credential != request.credential.model_dump(mode="json")
        or row.generation != request.credential.claims.generation
        or request.expires_at <= now
        or request.created_at > now + timedelta(seconds=30)
    ):
        _deny("Peer credential generation or request deadline is invalid")
    verify_signature(subject, request.signature, request_bytes(request))
    # Persist one-time nonces before dispatch; restart does not clear replay state.
    db.execute(
        delete(InstallationPeerNonce).where(
            InstallationPeerNonce.expires_at < now - timedelta(seconds=30)
        )
    )
    db.add(
        InstallationPeerNonce(
            binding_id=row.binding_id,
            generation=row.generation,
            nonce=request.nonce,
            expires_at=request.expires_at,
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise InstallationPeerError("Peer request was already consumed") from exc
    return row, request, False


def rotate_inbound(db, value, *, origin, path, now=None):
    now = now or datetime.now(UTC)
    row, request, duplicate = authenticate_request(
        db, value, origin=origin, path=path, now=now, allow_rotation_receipt=True
    )
    if request.payload != {}:
        _deny("Rotation payload must be empty")
    if not duplicate:
        row.generation += 1
        row.rotation_digest = hashlib.sha256(
            canonical_json(request.model_dump(mode="json"))
        ).hexdigest()
        row.updated_at = now
        _issue(db, row, now)
        _audit(
            db,
            "INSTALLATION_PEER_CREDENTIAL_ROTATED",
            row.binding_id,
            generation=row.generation,
            actor_kind="installation",
            actor_id=row.sender_id,
        )
    result = _result(row)
    db.commit()
    return result


def receive_report(db, value, *, origin, path, now=None):
    row, request, _ = authenticate_request(db, value, origin=origin, path=path, now=now)
    report = PeerReportV1.model_validate(request.payload)
    if report.projection.installation_id != row.sender_id:
        _deny("Projection installation subject is invalid")
    metadata = _metadata(row)
    if metadata is not None:
        _verify_projection(report.projection, metadata)
    application, package, definition = _live_inbound(db, row)
    principal = ApplicationPrincipal(
        kind="installation",
        installation_id=row.sender_id,
        installation_key_id=row.sender_identity["key_id"],
        peer_binding_id=row.binding_id,
        peer_generation=row.generation,
        machine_scopes=frozenset([PEER_SCOPE]),
    )
    if not can_access_application_operation(
        find_operation(definition, definition.peer_receiver.report_operation_id),
        principal,
        audience="installation_peer",
    ):
        _deny()
    context = machine_context(row, "installation_peer", report.report_id)
    generation = row.generation
    db.commit()

    def still_authorized():
        db.expire_all()
        current = db.get(InstallationPeerInbound, row.binding_id)
        try:
            _live_inbound(db, current)
        except (InstallationPeerError, ApplicationGatewayError):
            return False
        return current.state == "active" and current.generation == generation

    # Only Core creates the machine context; extension ownership policy remains
    # in this receiver handler. Never forward caller-controlled context/results.
    invoke_application(
        application,
        package,
        get_settings().applications,
        definition.peer_receiver.report_operation_id,
        {"projection": report.projection.model_dump(mode="json")},
        context,
        required_audience="installation_peer",
        before_dispatch=still_authorized,
    )
    return {
        "status": "accepted",
        "report_id": report.report_id,
        "installation_id": principal.installation_id,
    }


def peer_http(origin, path, payload):
    """Approved HTTPS origin only, certificate verification, no proxy/redirects."""
    origin = InstallationProofRequestV1.canonical_origin(origin)
    data = canonical_json(payload)
    if len(data) > PEER_MAX_BYTES:
        _deny("Peer request exceeds its limit")
    headers = (
        {"Content-Type": "application/json", "Authorization": "ThreeMM-Peer"}
        if path.endswith(("/report", "/rotate"))
        else {"Content-Type": "application/json"}
    )
    try:
        with httpx.Client(
            verify=True,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(12, connect=4),
        ) as client:
            with client.stream(
                "POST", origin + path, content=data, headers=headers
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    _deny(
                        f"Installation peer rejected the request (HTTP {response.status_code})"
                    )
                content = b""
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > PEER_MAX_BYTES:
                        _deny("Peer response exceeds its limit")
    except httpx.HTTPError as exc:
        raise InstallationPeerError(
            "Peer transport failed; resume the same durable request"
        ) from exc
    import json

    try:
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError) as exc:
        raise InstallationPeerError("Peer response is invalid") from exc


def _save_outbound(
    db, application, link_id, revision, *, expected_report_id=None, **changes
):
    # Reload after network I/O, then CAS. Revoke always fences delayed responses.
    db.rollback()
    _application(db, application.module_id, permission="installation.peers.enroll")
    current = _lock(db, InstallationPeerOutbound, link_id)
    if current.state == "active" and changes.get("state") in {"new", "pending"}:
        _deny("A delayed enrollment response cannot downgrade an active peer")
    if expected_report_id is not None and current.report_id != expected_report_id:
        _deny("A delayed report response cannot replace a newer sample receipt")
    proposed = changes.get("credential")
    if (
        proposed
        and current.credential
        and current.credential["claims"]["generation"]
        > proposed["claims"]["generation"]
    ):
        _deny("A delayed response cannot replace a newer credential generation")
    changed = db.execute(
        update(InstallationPeerOutbound)
        .where(
            InstallationPeerOutbound.link_id == link_id,
            InstallationPeerOutbound.state != "revoked",
            InstallationPeerOutbound.consent_revision == revision,
            InstallationPeerOutbound.application_instance_id == application.instance_id,
        )
        .values(updated_at=datetime.now(UTC), **changes)
    ).rowcount
    if changed != 1:
        db.rollback()
        _deny("Local peer consent changed while the request was in flight")
    db.commit()


def enroll_outbound(db, application, link_id, *, transport=None):
    transport = transport or peer_http
    row = _lock(db, InstallationPeerOutbound, link_id)
    _live_outbound(db, row, application)
    revision = row.consent_revision
    version, metadata, prefix = _version(row), _metadata(row), _prefix(row)
    origin, receiver, sender, target = (
        row.origin,
        row.receiver_identity,
        row.sender_identity,
        row.target_module_id,
    )
    if row.state == "active":
        result = outbound_status(row)
        db.commit()
        return result
    if row.complete_request is None:
        start = parse_peer(PeerEnrollmentStartV1, row.start_request, version=version)
        if start.receiver_challenge.expires_at <= datetime.now(UTC):
            start = _signed_start(
                db,
                link_id,
                target,
                InstallationIdentityV1.model_validate(receiver),
                origin,
                datetime.now(UTC),
                metadata,
            )
            row.start_request = start.model_dump(mode="json")
        db.commit()
        response = parse_peer(
            PeerEnrollmentChallengeV1,
            transport(
                origin,
                prefix + "/enrollments/start",
                start.model_dump(mode="json"),
            ),
            version=version,
        )
        if metadata is not None and response.enrollment_metadata != metadata:
            _deny("Receiver enrollment metadata does not match")
        verify_installation_proof(
            response.receiver_proof,
            expected_identity=receiver,
            expected_request=start.receiver_challenge,
        )
        challenge = response.sender_challenge
        pinned = InstallationIdentityV1.model_validate(receiver)
        if (
            challenge.receiver_installation_id != pinned.installation_id
            or challenge.receiver_key_id != pinned.key_id
            or challenge.receiver_key_generation != pinned.key_generation
            or challenge.audience != origin
            or challenge.resource
            != enrollment_resource(link_id, target, (PEER_SCOPE,), metadata)
        ):
            _deny("Receiver enrollment challenge binding is invalid")
        complete = peer_model(PeerEnrollmentCompleteV1, version)(
            **({"metadata_hash": metadata.metadata_hash} if metadata else {}),
            binding_id=response.binding_id,
            sender_proof=prove_installation_identity(db, challenge),
        )
        if complete.sender_proof.identity.model_dump(mode="json") != sender:
            _deny("Local installation identity changed")
        _save_outbound(
            db,
            application,
            link_id,
            revision,
            complete_request=complete.model_dump(mode="json"),
            remote_binding_id=response.binding_id,
            state="pending",
        )
    row = _lock(db, InstallationPeerOutbound, link_id)
    _live_outbound(db, row, application)
    if row.consent_revision != revision:
        _deny("Local peer consent changed while enrollment was in flight")
    complete = dict(row.complete_request)
    remote_binding_id = row.remote_binding_id
    db.commit()
    result = parse_peer(
        PeerEnrollmentResultV1,
        transport(origin, prefix + "/enrollments/complete", complete),
        version=version,
    )
    if result.binding_id != remote_binding_id:
        _deny("Enrollment response binding is invalid")
    if metadata is not None and result.enrollment_metadata != metadata:
        _deny("Enrollment response metadata does not match")
    if result.credential:
        verify_peer_credential(
            result.credential,
            issuer=InstallationIdentityV1.model_validate(receiver),
            subject=InstallationIdentityV1.model_validate(sender),
            origin=origin,
            module_id=target,
            now=datetime.now(UTC),
        )
    _save_outbound(
        db,
        application,
        link_id,
        revision,
        state=result.state,
        credential=(
            result.credential.model_dump(mode="json") if result.credential else None
        ),
    )
    return outbound_status(db.get(InstallationPeerOutbound, link_id))


def signed_outbound_request(db, row, path, payload):
    identity, private = _load_or_create(db)
    version, metadata = _version(row), _metadata(row)
    credential = parse_peer(PeerCredentialV1, row.credential, version=version)
    if metadata is not None and credential.claims.enrollment_metadata != metadata:
        _deny("Credential metadata differs from local consent")
    verify_peer_credential(
        credential,
        issuer=InstallationIdentityV1.model_validate(row.receiver_identity),
        subject=identity,
        origin=row.origin,
        module_id=row.target_module_id,
        now=datetime.now(UTC),
    )
    now = datetime.now(UTC)
    request = peer_model(PeerRequestV1, version)(
        credential=credential,
        path=path,
        nonce=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(seconds=120),
        payload=payload,
        signature=base64.b64encode(bytes(64)).decode(),
    )
    return request.model_copy(
        update={
            "signature": base64.b64encode(private.sign(request_bytes(request))).decode()
        }
    )


def rotate_outbound(db, application, link_id, *, transport=None):
    row = _lock(db, InstallationPeerOutbound, link_id)
    _live_outbound(db, row, application)
    if row.state != "active":
        _deny("Peer is not active")
    version, metadata, prefix = _version(row), _metadata(row), _prefix(row)
    revision, origin, receiver, sender, target = (
        row.consent_revision,
        row.origin,
        row.receiver_identity,
        row.sender_identity,
        row.target_module_id,
    )
    if row.rotation_request is None:
        row.rotation_request = signed_outbound_request(
            db, row, prefix + "/rotate", {}
        ).model_dump(mode="json")
    request = dict(row.rotation_request)
    binding_id = row.remote_binding_id
    old_generation = row.credential["claims"]["generation"]
    db.commit()
    result = parse_peer(
        PeerEnrollmentResultV1,
        (transport or peer_http)(origin, prefix + "/rotate", request),
        version=version,
    )
    if (
        result.credential is None
        or result.binding_id != binding_id
        or result.generation != old_generation + 1
    ):
        _deny("Rotation response binding or generation is invalid")
    if metadata is not None and result.enrollment_metadata != metadata:
        _deny("Rotation response metadata does not match")
    verify_peer_credential(
        result.credential,
        issuer=InstallationIdentityV1.model_validate(receiver),
        subject=InstallationIdentityV1.model_validate(sender),
        origin=origin,
        module_id=target,
        now=datetime.now(UTC),
    )
    _save_outbound(
        db,
        application,
        link_id,
        revision,
        credential=result.credential.model_dump(mode="json"),
        rotation_request=None,
    )
    return outbound_status(db.get(InstallationPeerOutbound, link_id))


def report_outbound(db, application, link_id, report_id, *, transport=None):
    _application(db, application.module_id, permission="installation.peers.report")
    _application(db, application.module_id, permission="installation.status.read")
    row = _lock(db, InstallationPeerOutbound, link_id)
    _live_outbound(db, row, application)
    if row.state != "active":
        _deny("Peer is not active")
    if row.report_id == report_id and row.report_result:
        result = dict(row.report_result)
        db.commit()
        return result
    if row.report_id and row.report_result is None and row.report_id != report_id:
        _deny("Finish the outstanding report before starting another sample")
    projection = (
        InstallationProjectionV1.model_validate(row.report_projection)
        if row.report_id == report_id and row.report_projection
        else installation_projection(db, application, link_id)
    )
    report = PeerReportV1(report_id=report_id, projection=projection)
    metadata = _metadata(row)
    if metadata is not None:
        _verify_projection(projection, metadata)
    row.report_id = report_id
    row.report_projection = projection.model_dump(mode="json")
    row.report_result = None
    request = signed_outbound_request(
        db, row, _prefix(row) + "/report", report.model_dump(mode="json")
    )
    revision, origin = row.consent_revision, row.origin
    db.commit()
    result = (transport or peer_http)(
        origin, request.path, request.model_dump(mode="json")
    )
    if result != {
        "status": "accepted",
        "report_id": report_id,
        "installation_id": projection.installation_id,
    }:
        _deny("Reporting acknowledgement is invalid")
    _save_outbound(
        db,
        application,
        link_id,
        revision,
        expected_report_id=report_id,
        report_result=result,
    )
    return result
