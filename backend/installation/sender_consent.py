"""A local operator permits one package to export one v2 status selection.

This is separate from proving possession of a peer key, the receiver's
decision and any read right. The reviewed record is signed in its own domain.
"""
import base64
import hashlib
from datetime import UTC, datetime

from backend.installation.identity import read_existing_installation_identity, _load_or_create
from packages.protocol.installation_peer import (
    PeerEnrollmentStartV1, canonical_json, enrollment_start_bytes, verify_signature,
)
from packages.protocol.installation_peer_v2 import parse_peer

DOMAIN = b"3mm.local.sender-report-approval.v1\n"


def report_profile(definition):
    return (definition.service.sdk_version == "1.3" and bool(definition.peer_bindings)
            and definition.peer_receiver is None and definition.storage.relational is None
            and all(b.direction == "outbound" and b.operations == ("report",)
                    for b in definition.peer_bindings))


def snapshot(db, application, package, definition, row):
    start = parse_peer(PeerEnrollmentStartV1, row.start_request, version=2)
    identity = read_existing_installation_identity(db)
    verify_signature(identity, start.signature, enrollment_start_bytes(start))
    metadata = start.enrollment_metadata
    if (not application.enabled or application.status != "active"
            or application.authority_mode not in ("compatibility", "enforced")
            or row.state != "active" or row.module_id != application.module_id
            or row.application_instance_id != application.instance_id
            or identity != start.sender or row.sender_identity != identity.model_dump(mode="json")
            or row.receiver_identity != start.receiver.model_dump(mode="json")
            or start.request_id != row.link_id or start.target_module_id != row.target_module_id
            or start.receiver_challenge.audience != row.origin
            or metadata.consent_revision != row.consent_revision or metadata.consent.model_dump(mode="json") != row.consent
            or not row.remote_binding_id or not row.credential
            or not {"installation.status.read", "installation.peers.report"} <= set(definition.platform_permissions)):
        raise ValueError("Sender report binding is unavailable")
    logical = None
    if definition.peer_bindings:
        matches = [b.binding_id for b in definition.peer_bindings
                   if (application.configuration or {}).get(b.peer_id_config_key) == row.link_id]
        if not report_profile(definition) or application.authority_mode != "enforced" or len(matches) != 1:
            raise ValueError("Sender declaration is not bound to this link")
        logical = matches[0]
    elif application.authority_mode != "compatibility":
        raise ValueError("A scoped report declaration is required")
    return {
        "contract": "installation.status.report.v2", "link_id": row.link_id,
        "binding_id": logical, "module_id": application.module_id, "application_id": application.id,
        "instance": application.instance_id, "incarnation": application.authority_incarnation,
        "authority_epoch": application.authority_epoch, "mode": application.authority_mode,
        "package_sha256": package.sha256, "sender_id": identity.installation_id, "sender_key": identity.key_id,
        "receiver_id": start.receiver.installation_id, "receiver_key": start.receiver.key_id,
        "origin": row.origin, "target": row.target_module_id, "remote_binding_id": row.remote_binding_id,
        "credential_generation": row.credential["claims"]["generation"], "revision": row.send_revision,
        "metadata": metadata.model_dump(mode="json"),
    }


def digest(view):
    return hashlib.sha256(DOMAIN + canonical_json(view)).hexdigest()


def contact_state(observation, revision, *, now=None):
    """A report receipt is a dated observation, not a live health probe."""
    if not isinstance(observation, dict) or observation.get("revision") != revision:
        return "unknown"
    try:
        age = ((now or datetime.now(UTC)) - datetime.fromisoformat(observation["at"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return "unknown"
    state = observation.get("state")
    if age < 0 or state not in {"online", "offline"}:
        return "unknown"
    return state if age <= 120 else "stale"


def approved(db, row, view):
    if row.send_approval is None:
        return False
    try:
        verify_signature(read_existing_installation_identity(db), row.send_approval, DOMAIN + canonical_json(view))
    except (ValueError, RuntimeError):
        return False
    return True


def review(db, application, link_id, *, decision=None, expected=None, user_id=None):
    from backend.db.installation_peer import InstallationPeerOutbound as Link
    from backend.installation.peers import _application, _audit, _deny, _lock
    row = db.get(Link, link_id) if decision is None else _lock(db, Link, link_id)
    if row is None or row.module_id != application.module_id or row.application_instance_id != application.instance_id:
        _deny()
    current, package, definition = _application(db, application.module_id, report_operator=True)
    view = snapshot(db, current, package, definition, row)
    if decision is None:
        return {"review": view, "review_hash": digest(view), "approved": approved(db, row, view),
                "sequence": row.report_sequence,
                "contact": contact_state(row.report_contact, row.consent_revision),
                "checkpoint": ("no_sample" if not row.report_id else "acknowledged" if row.report_result else "unconfirmed")}
    if decision not in ("allow", "withdraw") or user_id is None or expected != digest(view):
        _deny("The sender review changed; read it again")
    row.send_revision += 1
    view["revision"] = row.send_revision
    row.send_approval = (base64.b64encode(_load_or_create(db)[1].sign(DOMAIN + canonical_json(view))).decode()
                         if decision == "allow" else None)
    _audit(db, "INSTALLATION_PEER_SEND_ALLOWED" if decision == "allow" else "INSTALLATION_PEER_SEND_WITHDRAWN",
           link_id, user_id=user_id, generation=row.send_revision)
    db.commit()
