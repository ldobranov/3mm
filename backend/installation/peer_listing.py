"""Public peer listing sources, NOT scoped grants or current-peer admission.

Compatibility/admin history keeps its existing module filter and 100-per-direction
limit, including revoked/historical records. Never use these rows as an execution
binding: instance/incarnation/consent/generation checks belong to admission.
"""

from datetime import datetime

from sqlalchemy import select

from backend.db.installation_peer import (
    InstallationPeerInbound,
    InstallationPeerOutbound,
)


def public_peer_records(db, application):
    """Read explicit presentation columns without autoflush or transaction control.

    Start requests are public signed wire metadata (including public challenges),
    validated by the existing serializer. No private signing key, whole
    credential/certificate, report payload/cache or separate inbound
    sender_challenge column is selected. No peer ORM entity is loaded.
    The caller still owns authentication, permission and transaction lifetime.
    """
    with db.no_autoflush:
        # Expired ORM application attributes can themselves trigger autoflush.
        module_id = application.module_id
        incoming = InstallationPeerInbound.__table__.c
        outgoing = InstallationPeerOutbound.__table__.c
        inbound = tuple(
            db.execute(
                select(
                    incoming.binding_id,
                    incoming.sender_identity,
                    incoming.state,
                    incoming.generation,
                    incoming.approval_expires_at,
                    incoming.start_request,
                    incoming.completed_digest,
                )
                .where(incoming.module_id == module_id)
                .order_by(incoming.created_at.desc())
                .limit(100)
            )
        )
        outbound = tuple(
            db.execute(
                select(
                    outgoing.link_id,
                    outgoing.state,
                    outgoing.consent_revision,
                    outgoing.consent,
                    outgoing.origin,
                    outgoing.receiver_identity,
                    outgoing.target_module_id,
                    outgoing.remote_binding_id,
                    outgoing.start_request,
                    outgoing.credential["claims"]["expires_at"]
                    .as_string()
                    .label("credential_expires_at"),
                )
                .where(outgoing.module_id == module_id)
                .order_by(outgoing.created_at.desc())
                .limit(100)
            )
        )
        for row in outbound:
            value = row.credential_expires_at
            if value is None:
                continue
            if type(value) is not str or len(value) > 64:
                raise ValueError("Peer credential expiry metadata is invalid")
            try:
                expires = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("Peer credential expiry metadata is invalid") from None
            if expires.tzinfo is None or expires.utcoffset() is None:
                raise ValueError("Peer credential expiry metadata is invalid")
        return inbound, outbound
