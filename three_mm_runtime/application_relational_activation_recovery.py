"""Root-only explicit verified STOP of an interrupted prepared-service start.

Preserves the original witness, DB, lineage, wheel, configuration and key.
Never starts/imports a service, reruns migrations, enables boot, restores grants,
archives away ambiguity or retries an unknown helper outcome automatically.
Fresh Core tickets may reconcile lost recovery ACKs by another verified stop.
"""

import hashlib
import os
import re
import stat
from itertools import islice

from three_mm_application_sdk.relational_wire import (
    _activation_recovery_ticket,
    _RelationalActivationRecoveryResult,
    _RelationalActivationResult,
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import _application_metadata, _write_atomic
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_activation import (
    PreparedServiceSupervisor,
    _service_access,
)
from three_mm_runtime.application_relational_boot_policy import archive_stopped_boot
from three_mm_runtime.application_relational_namespace import (
    _exclusive_file,
    _roots,
    _validate_dependencies,
)
from three_mm_runtime.application_relational_preparation import _key, _live
from three_mm_runtime.application_relational_session import _decode, _prepared, _regular


class RelationalActivationRecoveryError(RuntimeError):
    pass


def _protected_evidence(path):
    info = _regular(path, protected=True)
    # 0600 grants no group access. Older Root-written recovery files retained
    # the Core group, which is immaterial to this Root-only evidence boundary.
    if stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= 8192:
        raise ValueError("Start evidence is not protected/bounded")
    value = _decode(path.read_bytes())
    if type(value) is not dict or type(value.get("version")) is not int:
        raise ValueError("Invalid start evidence")
    return value


def _confirmed_legacy_witness(state_root, instance, secret):
    """Recognize historical closure, never grant start or remove old evidence.

    Only Root's final stopped_review_required envelope (written AFTER the durable
    Core finish) plus its matching signed stop receipt closes a legacy witness.
    A signed receipt with stopped_unconfirmed is deliberately insufficient.
    The current start still needs its own ticket, authorization and verified stop.
    """
    marker = state_root / ("relational-activation-" + instance + ".json")
    value = _protected_evidence(marker)
    required = {
        "version",
        "activation_id",
        "ticket_sha256",
        "prepared_lifecycle_sha256",
        "phase",
    }
    phase = value.get("phase")
    if (
        value["version"] != 1
        or phase not in {"activation_unconfirmed", "active_review_required"}
        or set(value)
        != required | ({"receipt"} if phase == "active_review_required" else set())
        or type(value.get("activation_id")) is not str
        or re.fullmatch(r"[0-9a-f]{32}", value["activation_id"]) is None
        or any(
            type(value.get(name)) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value[name]) is None
            for name in ("ticket_sha256", "prepared_lifecycle_sha256")
        )
    ):
        raise ValueError("Legacy start witness changed")
    if phase == "active_review_required":
        original = _RelationalActivationResult.model_validate(
            value["receipt"]
        ).model_dump(mode="json")
        verify_metadata(secret, "activation_result", original)
        if (
            original["preparation_id"] != value["activation_id"]
            or original["lifecycle_sha256"] != value["prepared_lifecycle_sha256"]
        ):
            raise ValueError("Legacy start receipt changed")
    witness_sha = hashlib.sha256(
        canonical({"location": "pending", "evidence": value})
    ).hexdigest()
    prefix = "relational-start-recovery-" + instance + "-"
    paths = tuple(islice(state_root.glob(prefix + "*.json"), 33))
    if len(paths) > 32:
        raise ValueError("Start recovery evidence budget exceeded")
    for path in paths:
        evidence = _protected_evidence(path)
        if (
            evidence.get("source_activation_id") != value["activation_id"]
            or evidence.get("phase") != "stopped_review_required"
        ):
            continue
        receipt = _RelationalActivationRecoveryResult.model_validate(
            evidence.get("receipt")
        ).model_dump(mode="json")
        verify_metadata(secret, "activation_recovery_result", receipt)
        if (
            set(evidence)
            != {
                "version",
                "recovery_id",
                "source_activation_id",
                "ticket_sha256",
                "witness_sha256",
                "phase",
                "receipt",
            }
            or evidence["version"] != 1
            or path.name != prefix + receipt["preparation_id"] + ".json"
            or evidence["recovery_id"] != receipt["preparation_id"]
            or evidence["ticket_sha256"] != receipt["ticket_sha256"]
            or evidence["witness_sha256"] != witness_sha
            or receipt["source_activation_id"] != value["activation_id"]
            or receipt["lifecycle_sha256"] != value["prepared_lifecycle_sha256"]
            or receipt["witness_sha256"] != witness_sha
        ):
            raise ValueError("Legacy stop evidence changed")
        return value["activation_id"]
    raise ValueError("Legacy start witness requires confirmed recovery")


def _activation_marker(state_root, instance, identifier, secret):
    """Keep legacy paths readable; allocate a distinct pending path after closure."""
    legacy = state_root / ("relational-activation-" + instance + ".json")
    pending = state_root / (
        "relational-activation-" + instance + "-" + identifier + ".pending.json"
    )
    if os.path.lexists(legacy):
        value = _protected_evidence(legacy)
        if value.get("activation_id") == identifier:
            if os.path.lexists(pending):
                raise ValueError("Conflicting start witnesses require evidence review")
            return legacy
        _confirmed_legacy_witness(state_root, instance, secret)
        return pending
    return pending if os.path.lexists(pending) else legacy


def _witness(state_root, ticket, secret):
    marker = (
        _activation_marker(
            state_root, ticket["instance_id"], ticket["source_activation_id"], secret
        )
        if ticket["action"] != "reconcile_reactivated_start"
        else None
    )
    history = state_root / (
        "relational-activation-"
        + ticket["instance_id"]
        + "-"
        + ticket["source_activation_id"]
        + ".json"
    )
    reactivated = ticket["action"] == "reconcile_reactivated_start"
    if reactivated:
        history = state_root / (
            "relational-reactivation-"
            + ticket["instance_id"]
            + "-"
            + ticket["source_activation_id"]
            + ".json"
        )
        marker = history.with_suffix(".pending.json")
    pending, archived = os.path.lexists(marker), os.path.lexists(history)
    if pending and archived:
        raise ValueError("Conflicting start witnesses require evidence review")
    if not pending and not archived:
        if ticket["source_state"] != "recorded":
            raise ValueError("Interrupted start witness unavailable")
        # Absence proves neither a historical stop nor that a start never ran.
        # We will still require a fresh verified stop, not report 'never started'.
        return hashlib.sha256(canonical({"witness": "absent"})).hexdigest()
    path = marker if pending else history
    info = _regular(path, protected=True)
    if info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("Interrupted start witness is not protected/bounded")
    value = _decode(path.read_bytes())
    expected = {
        "version": 1,
        "activation_id": ticket["source_activation_id"],
        "ticket_sha256": ticket["source_ticket_sha256"],
        "prepared_lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
    }
    if type(value) is not dict or type(value.get("version")) is not int:
        raise ValueError("Interrupted start witness invalid")
    phase = value.get("phase")
    if (
        phase not in {"activation_unconfirmed", "active_review_required"}
        or (archived and phase != "active_review_required")
        or (
            phase == "active_review_required"
            and ticket["source_state"] not in {"activated", "activation_unconfirmed"}
        )
        or set(value)
        != set(expected)
        | {"phase"}
        | ({"receipt"} if phase == "active_review_required" else set())
        or any(value[name] != item for name, item in expected.items())
    ):
        raise ValueError("Interrupted start witness changed")
    if phase == "active_review_required":
        receipt = _RelationalActivationResult.model_validate(
            value["receipt"]
        ).model_dump(mode="json")
        verify_metadata(
            secret,
            "reactivation_result" if reactivated else "activation_result",
            receipt,
        )
        if (
            receipt["preparation_id"] != ticket["source_activation_id"]
            or receipt["lifecycle_sha256"] != ticket["prepared_lifecycle_sha256"]
        ):
            raise ValueError("Interrupted start completion receipt changed")
    return hashlib.sha256(
        canonical(
            {
                "location": "pending" if pending else "archived",
                "evidence": value,
            }
        )
    ).hexdigest()


def _stopped_prepared(instance, key_path, secret, ticket, expected, uid, gid):
    _live(ticket)
    info = _regular(key_path, protected=True)
    if (
        _key(key_path) != secret
        or info.st_gid != gid
        or stat.S_IMODE(info.st_mode) != 0o640
    ):
        raise ValueError("Prepared key changed")
    _service_access(key_path, uid, gid, 4)
    for name in ("data", "run"):
        path = instance / name
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != uid
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o750
        ):
            raise ValueError("Prepared namespace principal changed")
        _service_access(path, uid, gid, 5)
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = instance / "data" / ("state.sqlite3" + suffix)
        if suffix and not os.path.lexists(path):
            continue
        info = _regular(path)
        if info.st_uid != uid or info.st_gid != gid:
            raise ValueError("Prepared database principal changed")
    active = instance / "active.json"
    if (
        _regular(active, protected=True).st_size > 131072
        or _decode(active.read_bytes(), limit=131072) != expected
    ):
        raise ValueError("Prepared active metadata changed")
    record = _prepared(instance, secret)  # Bounded read-only metadata readiness.
    if (
        hashlib.sha256(canonical(record)).hexdigest()
        != ticket["prepared_lifecycle_sha256"]
        or record["database_lineage"] != ticket["database_lineage"]
        or record["lifecycle_id"] != ticket["source_preparation_id"]
    ):
        raise ValueError("Prepared lifecycle changed")


def reconcile_interrupted_relational_start(
    package_path,
    ticket,
    *,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    checkpoint,
    supervisor=None,
):
    """Success is currently stopped + review_required, NOT repaired/restarted.

    Core fences old authority at ticket issuance. Each source/recovery action
    stays one-use; fresh explicit reconciliation can supersede an unknown one.
    Original protected evidence stays intact even on success. No token/key in
    witnesses. Leases are never held across process/filesystem/read-only SQL I/O.
    """
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalActivationRecoveryError("Protected recovery helper required")
    ticket, purpose = _activation_recovery_ticket(ticket)
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    selected = supervisor or PreparedServiceSupervisor()
    instance = root / ticket["instance_id"]
    key_path = key_root / (ticket["instance_id"] + ".key")
    record_path = state_root / (
        "relational-start-recovery-"
        + ticket["instance_id"]
        + "-"
        + ticket["preparation_id"]
        + ".json"
    )
    with _release_lock(), _runtime_lock(state_root):
        _roots((root, key_root, state_root), coordinator_uid)
        secret = _key(key_path)
        verify_metadata(secret, purpose, ticket)
        validated, configuration = _validate_dependencies(
            package_path,
            ticket,
            configuration=configuration,
            transport_secret=secret,
            service_uid=service_uid,
            service_gid=service_gid,
            coordinator_uid=coordinator_uid,
        )
        expected = _application_metadata(validated, configuration, instance.name, root)
        expected["storage"]["relational"] = (
            validated.application_extension.storage.relational.model_dump(mode="json")
        )
        witness_sha = _witness(state_root, ticket, secret)
        if (
            os.path.lexists(record_path)
            or len(
                tuple(
                    islice(
                        state_root.glob(
                            "relational-start-recovery-" + instance.name + "-*.json"
                        ),
                        32,
                    )
                )
            )
            >= 32
        ):
            raise RelationalActivationRecoveryError(
                "Recovery requires fresh evidence review"
            )
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_stop_only"}:
            raise RelationalActivationRecoveryError(
                "Recovery stop authority unavailable"
            )
        evidence = {
            "version": 1,
            "recovery_id": ticket["preparation_id"],
            "source_activation_id": ticket["source_activation_id"],
            "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
            "witness_sha256": witness_sha,
            "phase": "stop_unconfirmed",
        }
        _exclusive_file(record_path, canonical(evidence), 0o600, 0)
        try:
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Recovery begin unconfirmed")
            selected.recover_disabled(instance.name)
            selected.verify_identity(
                instance.name, service_uid, service_gid, running=False
            )
            _stopped_prepared(
                instance, key_path, secret, ticket, expected, service_uid, service_gid
            )
            if _witness(state_root, ticket, secret) != witness_sha:
                raise ValueError("Interrupted start witness changed during stop")
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Recovery stop confirmation unavailable")
            selected.verify_identity(
                instance.name, service_uid, service_gid, running=False
            )
            _live(ticket)
            archive_stopped_boot(instance, state_root, ticket, secret)
            result = _RelationalActivationRecoveryResult.model_validate(
                sign_metadata(
                    secret,
                    "activation_recovery_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "ticket_sha256": evidence["ticket_sha256"],
                        "source_activation_id": ticket["source_activation_id"],
                        "lifecycle_sha256": ticket["prepared_lifecycle_sha256"],
                        "witness_sha256": witness_sha,
                        "outcome": "stopped_review_required",
                    },
                )
            ).model_dump(mode="json")
            # Retain this signed stop evidence BEFORE a possibly lost finish ACK.
            _write_atomic(
                record_path,
                canonical(dict(evidence, phase="stopped_unconfirmed", receipt=result)),
                0o600,
                uid=0,
                gid=0,
            )
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "stopped_review_required"
            }:
                raise ValueError("Recovery completion unconfirmed")
            _write_atomic(
                record_path,
                canonical(
                    dict(evidence, phase="stopped_review_required", receipt=result)
                ),
                0o600,
                uid=0,
                gid=0,
            )
            return result
        except Exception as exc:
            # No ambiguous response is success. No retries, evidence deletion,
            # start, rollback, migration or implicit permission restoration.
            raise RelationalActivationRecoveryError(
                "Recovery unconfirmed; retain evidence for fresh local review"
            ) from exc
