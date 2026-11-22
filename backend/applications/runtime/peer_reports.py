"""Scoped status export: projection grant AND separately approved sending link."""
import re

from backend.applications.authority.management import effect_admission
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.installation import peers
from backend.installation.sender_consent import report_profile
from packages.platform_wire import ENVELOPE_FIELDS
from packages.protocol.installation_peer import PEER_ID_PATTERN


def send_reviewed_report(db, installation, request):
    inspect = set(request) == ENVELOPE_FIELDS | {"binding_id", "inspect"} and request.get("inspect") is True
    if ((not inspect and set(request) != ENVELOPE_FIELDS | {"binding_id", "report_id", "sequence", "approval"})
            or request["action"] != "installation.peers.report" or type(request["version"]) is not int
            or request["version"] != 1 or request["instance_id"] != installation.instance_id
            or not isinstance(request["binding_id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", request["binding_id"])
            or (not inspect and (not isinstance(request["report_id"], str) or not re.fullmatch(r"report_[0-9a-f]{32}", request["report_id"])
                or not isinstance(request["approval"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["approval"])
                or type(request["sequence"]) is not int or not 0 < request["sequence"] < 2**53))
            or db.new or db.dirty or db.deleted or db.in_nested_transaction()):
        raise ValueError("Request has no supported resource grant")
    identifier = installation.id
    binding, report = request["binding_id"], request.get("report_id")
    try:
        app, _, definition = peers._application(db, installation.module_id, report_operator=True)
        if app.authority_mode != "enforced" or not report_profile(definition):
            raise ValueError()
        declaration, = (b for b in definition.peer_bindings if b.binding_id == binding)
        link = app.configuration.get(declaration.peer_id_config_key)
        if type(link) is not str or not re.fullmatch(PEER_ID_PATTERN, link):
            raise ValueError()
        db.rollback()
        with effect_admission(db, identifier, f"status:{link}:read") as admission:
            current = db.get(Installation, identifier, populate_existing=True)
            if (admission.compatibility or current is None or current.instance_id != request["instance_id"]
                    or not report_profile(admission.definition)
                    or not any(s.link_id == link for s in admission.status_projections)):
                raise ValueError()
            # Re-resolves configuration, signed human decision, package, epoch,
            # peer identity, generation, fields and sequence under the guard.
            if inspect:
                from backend.installation.sender_consent import review
                card = review(db, current, link)
                if not card["approved"] or card["review"]["binding_id"] != binding:
                    raise ValueError()
                state = {"binding_id": binding, "approval": card["review_hash"], "sequence": card["sequence"],
                         "checkpoint": card["checkpoint"], "contact": card["contact"]}
                db.commit()
                admission()
                return state
            work = peers._prepare_outbound_report(db, current, link, report, binding=binding, sequence=request["sequence"],
                                                   expected_approval=request["approval"])
            admission()
    except Exception:
        db.rollback()
        raise peers.LocalPeerConsentWithdrawn("Scoped sending authority is unavailable or changed") from None
    # No DB transaction or review-key lock spans HTTPS.
    return peers._deliver_prepared(db, current, link, report, work, scoped=True)
