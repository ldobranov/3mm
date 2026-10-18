"""One exact outbound public peer read through current installed authority.

The signed gateway authenticates the instance. Lock order is review key -> Core
guard -> all approved peer rows. Read current resources only after those locks;
no credentials, private signing key, compatibility list or network operations.
"""

import re

from sqlalchemy import select, update

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.authority import CoreAuthorityGuard
from backend.db.installation_peer import InstallationPeerOutbound as Peer
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_context import _parse
from backend.services.application_authority_policy import PolicySubjectV9
from three_mm_protocol.application_peer_read import ApplicationPeerReadV1
from three_mm_protocol.installation_peer import PeerOutboundStatusV1
from three_mm_protocol.installation_peer_v2 import peer_model


_FIELDS = {
    "version",
    "request_id",
    "timestamp",
    "instance_id",
    "action",
    "signature",
    "binding_id",
}


def read_application_peer(db, installation, request):
    """Gateway-only: selectors are logical declaration IDs, never caller peers."""
    if (
        set(request) != _FIELDS
        or request.get("action") != "installation.peers.read"
        or type(request.get("version")) is not int
        or request["version"] != 1
        or type(request.get("binding_id")) is not str
        or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", request["binding_id"]) is None
    ):
        raise ValueError("Peer read request fields are invalid")
    if db.new or db.dirty or db.deleted or db.in_nested_transaction():
        raise ValueError("Peer read requires a clean session")
    installation_id = installation.id
    binding_id = request["binding_id"]
    db.rollback()  # End gateway snapshot before key and write-lock acquisition.
    from backend.services.application_authority_management import (
        configured_manager,
        _load,
    )

    try:
        manager = configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)  # ZIP validation outside locks.
        with manager.keys.locked() as key:
            if (
                db.execute(
                    update(CoreAuthorityGuard)
                    .where(CoreAuthorityGuard.singleton_id == 1)
                    .values(revision=CoreAuthorityGuard.revision)
                ).rowcount
                != 1
            ):
                raise ValueError("Core authority guard is unavailable")
            grant = _load(
                db,
                key,
                "grant",
                db.get(Grant, installation_id, populate_existing=True),
                installation_id,
            )
            approved = _parse(PolicySubjectV9, grant["data"]["subject"])
            # Bound the whole family, even omitted scopes. Row locks serialize
            # against existing peer writers without loading private ORM columns.
            columns = Peer.__table__.c
            for resource in sorted(approved.peer_reads, key=lambda item: item.peer_id):
                if (
                    resource.declaration.direction != "outbound"
                    or db.execute(
                        update(Peer.__table__)
                        .where(
                            columns.link_id == resource.peer_id,
                            columns.module_id == resource.owner.module_id,
                            columns.application_instance_id
                            == resource.application_instance_id,
                            columns.state.in_(("new", "pending", "active")),
                        )
                        .values(
                            consent_revision=columns.consent_revision,
                            updated_at=columns.updated_at,
                        )
                    ).rowcount
                    != 1
                ):
                    raise ValueError("Peer read binding is unavailable")
            manager._require_grant(
                db, key, installation_id, prepared, f"peer:{binding_id}:read"
            )
            current = db.get(Installation, installation_id, populate_existing=True)
            if (
                current is None
                or current.instance_id != request["instance_id"]
                or not current.enabled
                or current.status != "active"
            ):
                raise ValueError("Peer read transport binding changed")
            matches = [
                item
                for item in approved.peer_reads
                if item.declaration.binding_id == binding_id
            ]
            if len(matches) != 1:
                raise ValueError("Peer read declaration is unavailable")
            resource = matches[0]
            observation = db.execute(
                select(columns.state, columns.remote_binding_id).where(
                    columns.link_id == resource.peer_id
                )
            ).one()
            values = dict(
                link_id=resource.peer_id,
                state=observation.state,
                consent_revision=resource.consent_revision,
                consent=resource.consent,
                origin=resource.origin,
                receiver_identity=resource.receiver_identity,
                target_module_id=resource.target_module_id,
                remote_binding_id=observation.remote_binding_id,
                credential_expires_at=None,
            )  # Unknown: never inspect a credential.
            if resource.peer_version == 2:
                values.update(
                    peer_version=2, enrollment_metadata=resource.enrollment_metadata
                )
            result = ApplicationPeerReadV1(
                binding_id=binding_id,
                peer=peer_model(PeerOutboundStatusV1, resource.peer_version)(**values),
            ).model_dump(mode="json")
            db.commit()  # Release row/guard locks before releasing the key/reply.
            return result
    except Exception:
        db.rollback()
        # No raw DB/configuration, intent, credentials or partial resource leaks.
        raise ValueError(
            "Application peer read is unavailable or not authorized"
        ) from None
