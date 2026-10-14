"""Protected historical stop evidence for a fresh one-use prepared restart.

Read-only under the caller's shared release/runtime locks. No original witness
is removed, moved, rewritten or inferred from process/health absence.
"""

import hashlib
import stat

from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    canonical,
    verify_metadata,
)
from three_mm_runtime.application_relational_session import _decode, _regular


def verify_stopped_source(state_root, ticket, secret):
    from three_mm_runtime.application_relational_activation_recovery import _witness

    source, purpose = _activation_recovery_ticket(ticket["source_recovery_ticket"])
    receipt = ticket["source_recovery_receipt"]
    verify_metadata(secret, purpose, source)  # Historical: no live clock renewal.
    verify_metadata(secret, "activation_recovery_result", receipt)
    source_sha = hashlib.sha256(canonical(source)).hexdigest()
    if (
        source["preparation_id"] != ticket["source_recovery_id"]
        or receipt["preparation_id"] != ticket["source_recovery_id"]
        or receipt["source_activation_id"] != source["source_activation_id"]
        or receipt["ticket_sha256"] != source_sha
        or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
        or receipt["outcome"] != "stopped_review_required"
        or any(
            source[name] != ticket[name]
            for name in (
                "instance_id",
                "database_lineage",
                "owner_sha256",
                "package_sha256",
                "service_sha256",
                "configuration_sha256",
                "profile_sha256",
                "schema_revision",
                "recovery_generation",
                "source_preparation_id",
                "prepared_lifecycle_sha256",
                "service_uid",
                "service_gid",
                "coordinator_uid",
                "transport_key_sha256",
            )
        )
    ):
        raise ValueError("Reactivation historical stop binding changed")
    path = state_root / (
        "relational-start-recovery-"
        + ticket["instance_id"]
        + "-"
        + ticket["source_recovery_id"]
        + ".json"
    )
    info = _regular(path, protected=True)
    if info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("Reactivation stop witness is not protected/bounded")
    expected = {
        "version": 1,
        "recovery_id": ticket["source_recovery_id"],
        "source_activation_id": source["source_activation_id"],
        "ticket_sha256": source_sha,
        "witness_sha256": receipt["witness_sha256"],
        "phase": "stopped_review_required",
        "receipt": receipt,
    }
    value = _decode(path.read_bytes())
    if (
        type(value) is not dict
        or type(value.get("version")) is not int
        or value != expected
        or _witness(state_root, source, secret) != receipt["witness_sha256"]
    ):
        raise ValueError("Reactivation confirmed stop evidence changed")
