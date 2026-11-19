"""Local observation of one outbound status report; never a sender or a permission check."""
import json
import re

from packages.protocol.module_manifest import MODULE_ID_PATTERN


LINK = re.compile(r"peer_[0-9a-f]{32}\Z")
REPORT = re.compile(r"report_[0-9a-f]{32}\Z")
STATES = frozenset(("not_observed_in_scope", "outcome_unconfirmed", "acknowledged", "unavailable"))
LIST_LIMIT = 16


def valid_owner(module_id):
    return type(module_id) is str and len(module_id) <= 160 and re.fullmatch(MODULE_ID_PATTERN, module_id) is not None


def identifiers(module_id, link_id, report_id):
    return (valid_owner(module_id)
            and type(link_id) is str and LINK.fullmatch(link_id) is not None
            and type(report_id) is str and REPORT.fullmatch(report_id) is not None)


def checked_observation(value):
    """For offline support readers too: return fixed vocabulary, never arbitrary attachments."""
    if (type(value) is not dict or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("kind") != "peer_report_observation" or value.get("source") != "local_outbound_slot"
            or value.get("automatic_replay_allowed") is not False
            or not identifiers(value.get("module_id"), value.get("link_id"), value.get("report_id"))
            or type(value.get("state")) is not str or value["state"] not in STATES):
        raise ValueError("Invalid peer report observation")
    return {k: value[k] for k in ("schema_version", "kind", "source", "module_id", "link_id",
                                  "report_id", "state", "automatic_replay_allowed")}


def _active_slots(module_id):
    """Build a scoped read without loading any ORM entities or report payload."""
    from sqlalchemy import and_, func, select
    from backend.db.installation_identity import CoreInstallationIdentity
    from backend.db.installation_peer import InstallationPeerOutbound
    from backend.db.module import ApplicationExtensionInstallation

    link, app = InstallationPeerOutbound.__table__.c, ApplicationExtensionInstallation.__table__.c
    # Keep one excess character so a corrupted value with a valid prefix
    # cannot compare equal to an actual 37-character installation identity.
    local_id = select(func.substr(CoreInstallationIdentity.installation_id, 1, 38)).where(
        CoreInstallationIdentity.singleton_id == 1).scalar_subquery()
    sender = func.substr(link.sender_identity["installation_id"].as_string(), 1, 38)
    sql = (select().select_from(InstallationPeerOutbound)
           .join(ApplicationExtensionInstallation, and_(app.module_id == link.module_id,
                                                       app.instance_id == link.application_instance_id))
           .where(link.module_id == module_id, link.state == "active", app.enabled.is_(True), app.status == "active"))
    return sql, link, local_id, sender


def current_references(db, module_id, after=None):
    """Discover bounded opaque IDs without selecting report results, URL, keys or projections."""
    from sqlalchemy import func
    if not valid_owner(module_id) or (after is not None and
            (type(after) is not str or len(after) != 37 or not LINK.fullmatch(after))):
        raise ValueError("Invalid peer report lookup")
    sql, link, current, sender = _active_slots(module_id)
    if after is not None:
        sql = sql.where(link.link_id > after)  # exclusive, not proof of access or delivery
    sql = (sql.add_columns(link.link_id, link.report_id, current)
           .where(func.length(link.link_id) == 37, func.length(link.report_id) == 39,
                  func.length(current) == 37, current == sender,
                  link.link_id.regexp_match(r"^peer_[0-9a-f]{32}$"),
                  link.report_id.regexp_match(r"^report_[0-9a-f]{32}$"),
                  current.regexp_match(r"^inst_[0-9a-f]{32}$"))
           .order_by(link.link_id).limit(LIST_LIMIT + 1))
    with db.no_autoflush:
        rows = db.execute(sql).all()
    choices = [{"link_id": lnk, "report_id": ref} for lnk, ref, identity in rows[:LIST_LIMIT]
               if re.fullmatch(r"inst_[0-9a-f]{32}", identity) and identifiers(module_id, lnk, ref)]
    return {"module_id": module_id, "references": choices, "limited": len(rows) > LIST_LIMIT}


def observe_report(db, module_id, link_id, report_id):
    """One snapshot against an exact active local link/app; no IO outside its catalog DB."""
    from sqlalchemy import LargeBinary, Text, case, cast, func, literal
    if not identifiers(module_id, link_id, report_id):
        raise ValueError("Invalid peer report identifiers")
    sql, link, current, sender = _active_slots(module_id)
    # The real ACK is three short scalar fields. Do not fetch a projection,
    # credential, remote URL or arbitrarily long damaged cache into the reader.
    bounded = case((func.length(cast(link.report_result, LargeBinary)) <= 512, cast(link.report_result, Text)),
                   (link.report_result.is_(None), literal("null")), else_=literal("invalid"))
    sql = sql.add_columns(bounded, current, sender).where(link.link_id == link_id, link.report_id == report_id)
    with db.no_autoflush:
        row = db.execute(sql).one_or_none()
    state = "not_observed_in_scope"
    if row is not None:
        raw, current, sender = row
        state = "unavailable"
        if isinstance(current, str) and re.fullmatch(r"inst_[0-9a-f]{32}", current) and sender == current:
            if raw == "null":
                state = "outcome_unconfirmed"
            else:
                try:
                    # Reject duplicate/extra ACK fields; do not print the cache even when damaged.
                    pairs = json.loads(raw, object_pairs_hook=list)
                    if (isinstance(pairs, list) and raw.lstrip().startswith("{") and len(pairs) == 3
                            and dict(pairs) == {"status":"accepted", "report_id":report_id, "installation_id":current}):
                        state = "acknowledged"
                except (TypeError, ValueError, RecursionError):
                    pass
    return checked_observation({"schema_version":1, "kind":"peer_report_observation", "source":"local_outbound_slot",
                                "module_id":module_id, "link_id":link_id, "report_id":report_id, "state":state,
                                "automatic_replay_allowed":False})
