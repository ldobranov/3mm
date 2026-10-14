"""Explicit root reconciliation of EMPTY namespace bootstrap, never DB recovery.

Confirmation only checks a complete layout/key. Quarantine moves known empty
bootstrap objects to recoverable protected evidence; it never overwrites them.
Both require fresh LOCAL Core authority, confirmed stop and existing locks.
No SQL, package imports, rekey, migration, permission approval or restart.
"""

import hashlib
import os
import stat

from three_mm_application_sdk.relational_wire import (
    _RelationalNamespacePreparationResult,
    _RelationalNamespacePreparationTicket,
    _RelationalNamespaceRecoveryResult,
    _RelationalNamespaceRecoveryTicket,
    canonical,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _stop_for_data,
    _write_atomic,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_namespace import (
    _roots,
    _sync_directory,
    _validate_dependencies,
)
from three_mm_runtime.application_relational_preparation import (
    RelationalPreparationError,
    _live,
)
from three_mm_runtime.application_relational_session import (
    _decode,
    _protected_directory,
    _regular,
)

MAX_MARKERS = 32
SOURCE_BINDINGS = (
    "instance_id",
    "database_lineage",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
    "service_uid",
    "service_gid",
    "coordinator_uid",
    "transport_key_sha256",
)


def _json(path):
    info = _regular(path, protected=True)
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("Namespace evidence is not protected/bounded")
    return _decode(path.read_bytes(), limit=8192)


def _creation_evidence(source):
    return {
        "schema_version": 1,
        "operation": "create_owned_namespace",
        "preparation_id": source["preparation_id"],
        "ticket_sha256": hashlib.sha256(canonical(source)).hexdigest(),
        "phase": "creation_unconfirmed",
    }


def _witness(path, source, secret):
    value = _json(path)
    expected = _creation_evidence(source)
    if canonical(value) == canonical(expected):
        return
    receipt = _RelationalNamespacePreparationResult.model_validate(
        value.get("receipt") if type(value) is dict else None
    ).model_dump(mode="json")
    verify_metadata(secret, "namespace_preparation_result", receipt)
    if (
        receipt["preparation_id"] != source["preparation_id"]
        or receipt["ticket_sha256"] != expected["ticket_sha256"]
        or canonical(value)
        != canonical(
            dict(expected, phase="namespace_created_not_started", receipt=receipt)
        )
    ):
        raise ValueError("Namespace creation witness changed")


def _pending(directory, source, ticket, secret):
    """Closed known creation/recovery markers; unknown lifecycle evidence refuses."""
    _protected_directory(directory)
    entries = []
    for entry in directory.iterdir():
        entries.append(entry)
        if len(entries) > 1:
            raise ValueError("Unknown namespace checkpoint content")
    creation = ".activation-" + source["preparation_id"] + ".rollback"
    original_name = directory.name.removeprefix(".namespace-evidence-")
    if original_name == creation:
        if entries:
            if tuple(path.name for path in entries) != ("activation.json",):
                raise ValueError("Unknown creation checkpoint content")
            if canonical(_json(entries[0])) != canonical(_creation_evidence(source)):
                raise ValueError("Creation checkpoint changed")
        return
    if tuple(path.name for path in entries) != ("namespace-recovery.json",):
        raise ValueError("Unknown namespace recovery checkpoint")
    value = _json(entries[0])
    if (
        type(value) is not dict
        or set(value) != {"version", "ticket", "phase"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["phase"] not in {"checking", "completion_unconfirmed", "confirmed"}
    ):
        raise ValueError("Unknown namespace recovery evidence")
    old = _RelationalNamespaceRecoveryTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    verify_metadata(secret, "namespace_recovery", old)
    if (
        original_name != ".activation-" + old["preparation_id"] + ".rollback"
        or old["source_preparation_id"] != source["preparation_id"]
        or old["source_ticket_sha256"] != ticket["source_ticket_sha256"]
        or any(old[name] != ticket[name] for name in SOURCE_BINDINGS)
    ):
        raise ValueError("Foreign namespace recovery checkpoint")


def _layout(instance, source, ticket, secret, *, complete):
    if not os.path.lexists(instance):
        if complete:
            raise ValueError("Namespace is incomplete")
        return []
    _protected_directory(instance)
    pending = []
    count = 0
    found = set()
    for path in instance.iterdir():
        count += 1
        if count > MAX_MARKERS + 3:
            raise ValueError("Namespace checkpoint budget exceeded")
        if path.name in {"releases", "data", "run"}:
            found.add(path.name)
            info = path.lstat()
            uid = 0 if path.name == "releases" else ticket["service_uid"]
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_mode & 0o022
                or info.st_uid not in ({uid} if complete else {0, uid})
                or info.st_gid
                not in (
                    {ticket["service_gid"]} if complete else {0, ticket["service_gid"]}
                )
                or stat.S_IMODE(info.st_mode)
                not in ({0o750} if complete else {0o700, 0o750})
                or next(path.iterdir(), None) is not None
            ):
                raise ValueError("Namespace is not empty or ownership changed")
        elif path.name.startswith((".activation-", ".namespace-evidence-.activation-")):
            _pending(path, source, ticket, secret)
            if path.name.startswith(".activation-"):
                pending.append(path)
        else:
            raise ValueError("Namespace contains unknown data or lifecycle metadata")
    if complete and found != {"releases", "data", "run"}:
        raise ValueError("Namespace is incomplete")
    info = instance.lstat()
    if info.st_gid not in (
        {ticket["service_gid"]} if complete else {0, ticket["service_gid"]}
    ) or stat.S_IMODE(info.st_mode) not in ({0o750} if complete else {0o700, 0o750}):
        raise ValueError("Namespace ownership changed")
    return pending


def _key(path, ticket, secret, *, complete):
    if not os.path.lexists(path):
        if complete:
            raise ValueError("Namespace key is incomplete")
        return
    info = _regular(path, protected=True)
    if (
        info.st_gid
        not in ({ticket["service_gid"]} if complete else {0, ticket["service_gid"]})
        or stat.S_IMODE(info.st_mode) not in ({0o640} if complete else {0o600, 0o640})
        or info.st_size > 32
        or (complete and info.st_size != 32)
        or path.read_bytes() != secret[: info.st_size]
    ):
        raise ValueError("Namespace key changed")


def _select(original, archive):
    if os.path.lexists(original) and os.path.lexists(archive):
        raise ValueError("Namespace quarantine destination already exists")
    return archive if os.path.lexists(archive) else original


def _move(original, archive):
    if not os.path.lexists(original):
        return
    if os.path.lexists(archive):
        raise ValueError("Namespace evidence cannot be overwritten")
    original.rename(archive)
    _sync_directory(original.parent)


def reconcile_empty_relational_namespace(
    package_path,
    ticket,
    source_ticket,
    *,
    configuration,
    transport_secret,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    coordinator_uid,
    checkpoint,
    supervisor=None,
):
    """Trusted local dependencies only; partial quarantine needs a NEW human ticket.

    Old uncertain history is preserved. Quarantine never accepts a database,
    business file, wheel, unknown checkpoint or changed secret. Complete lost-ACK
    creation can instead be confirmed without replay, rekey or SQL writes.
    """
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalPreparationError("Protected namespace recovery unavailable")
    ticket = _RelationalNamespaceRecoveryTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    source = _RelationalNamespacePreparationTicket.model_validate(
        source_ticket
    ).model_dump(mode="json")
    verify_metadata(transport_secret, "namespace_recovery", ticket)
    verify_metadata(transport_secret, "namespace_preparation", source)
    if (
        ticket["source_preparation_id"] != source["preparation_id"]
        or ticket["source_ticket_sha256"]
        != hashlib.sha256(canonical(source)).hexdigest()
        or any(ticket[name] != source[name] for name in SOURCE_BINDINGS)
    ):
        raise ValueError("Namespace recovery source changed")
    _validate_dependencies(
        package_path,
        ticket,
        configuration=configuration,
        transport_secret=transport_secret,
        service_uid=service_uid,
        service_gid=service_gid,
        coordinator_uid=coordinator_uid,
    )
    root, key_root, state_root = _roots((root, key_root, state_root), coordinator_uid)
    with _release_lock(), _runtime_lock(state_root):
        root, key_root, state_root = _roots(
            (root, key_root, state_root), coordinator_uid
        )
        instance = root / ticket["instance_id"]
        key_path = key_root / (instance.name + ".key")
        witness = state_root / ("relational-namespace-" + instance.name + ".json")
        suffix = instance.name + "-" + source["preparation_id"]
        archived_instance = root / (".namespace-evidence-" + suffix)
        archived_key = key_root / (".namespace-evidence-" + suffix + ".key")
        archived_witness = state_root / (".namespace-evidence-" + suffix + ".json")
        complete = ticket["action"] == "confirm_owned_namespace"
        _witness(witness, source, transport_secret)
        if os.path.lexists(archived_witness):
            raise ValueError("Namespace witness archive already exists")
        if complete and any(
            os.path.lexists(path) for path in (archived_instance, archived_key)
        ):
            raise ValueError("Quarantined namespace cannot be confirmed")
        selected_instance = _select(instance, archived_instance)
        selected_key = _select(key_path, archived_key)
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Namespace recovery authorization unavailable")
        _stop_for_data(supervisor or SystemdApplicationSupervisor(), instance.name)
        _layout(selected_instance, source, ticket, transport_secret, complete=complete)
        _key(selected_key, ticket, transport_secret, complete=complete)
        # A pending marker blocks migration after unknown confirmation. It is
        # preserved inside quarantine, and only archived after durable finish.
        marker = None
        if os.path.lexists(selected_instance):
            if (
                sum(
                    path.name.startswith(
                        (".activation-", ".namespace-evidence-.activation-")
                    )
                    for path in selected_instance.iterdir()
                )
                >= MAX_MARKERS
            ):
                raise ValueError("Namespace recovery checkpoint budget exceeded")
            marker = selected_instance / (
                ".activation-" + ticket["preparation_id"] + ".rollback"
            )
            marker.mkdir(mode=0o700)

        def phase(value):
            if marker is not None:
                _write_atomic(
                    marker / "namespace-recovery.json",
                    canonical(
                        {
                            "version": 1,
                            "ticket": ticket,
                            "phase": value,
                        }
                    ),
                    0o600,
                )

        try:
            phase("checking")
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Namespace recovery begin unavailable")
            pending = _layout(
                selected_instance, source, ticket, transport_secret, complete=complete
            )
            _key(selected_key, ticket, transport_secret, complete=complete)
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Namespace recovery changed")
            _live(ticket)
            phase("completion_unconfirmed")
            if not complete:
                # Archive ancestry/keys become root-only too: a future process
                # with the same service UID must not mutate preserved evidence.
                for path, mode in ((selected_instance, 0o700), (selected_key, 0o600)):
                    if os.path.lexists(path):
                        path.chmod(mode)
                        os.chown(path, 0, 0)
                _move(instance, archived_instance)
                _move(key_path, archived_key)
                # Main witness remains blocking until Core confirmed quarantine.
                marker = (
                    (archived_instance / marker.name) if marker is not None else None
                )
            result = _RelationalNamespaceRecoveryResult.model_validate(
                sign_metadata(
                    transport_secret,
                    "namespace_recovery_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
                        "outcome": (
                            "namespace_confirmed_not_started"
                            if complete
                            else "namespace_quarantined_not_started"
                        ),
                    },
                )
            ).model_dump(mode="json")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": result["outcome"]
            }:
                raise ValueError("Namespace recovery completion unconfirmed")
            _witness(witness, source, transport_secret)
            _layout(
                _select(instance, archived_instance),
                source,
                ticket,
                transport_secret,
                complete=complete,
            )
            _key(
                _select(key_path, archived_key),
                ticket,
                transport_secret,
                complete=complete,
            )
            _live(ticket)
            phase("confirmed")
            if complete:
                for path in pending:
                    _move(path, path.with_name(".namespace-evidence-" + path.name))
            else:
                _move(witness, archived_witness)
            return result
        except Exception as exc:
            raise RelationalPreparationError(
                "Namespace recovery incomplete; evidence retained, fresh review required"
            ) from exc
