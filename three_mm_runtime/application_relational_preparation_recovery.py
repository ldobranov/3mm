"""Root reconciliation of one restored-empty initial migration checkpoint.

No SQL, package imports, key replacement, deletion or start. Retained wheel/key
stay unchanged. Exact closed preimages and verified quiescence are mandatory.
Unknown/partial publication, candidate DB/files and foreign markers refuse.
"""

import hashlib
import os
import re
import stat

from three_mm_application_sdk.relational_preparation_recovery_wire import (
    _EmptyPreparationRecoveryResult,
    _EmptyPreparationRecoveryTicket,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalNamespacePreparationTicket,
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
from three_mm_runtime.application_relational_namespace_recovery import (
    SOURCE_BINDINGS,
    _witness,
)
from three_mm_runtime.application_relational_preparation import (
    RelationalPreparationError,
    _key,
    _live,
)
from three_mm_runtime.application_relational_session import (
    _decode,
    _protected_directory,
    _regular,
)

MAX_EVIDENCE = 32


def _children(path, maximum):
    result = {}
    for item in path.iterdir():
        result[item.name] = item
        if len(result) > maximum:
            raise ValueError("Empty preparation evidence budget exceeded")
    return result


def _json(path):
    info = _regular(path, protected=True)
    if stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 8192:
        raise ValueError("Empty preparation evidence is not protected/bounded")
    return _decode(path.read_bytes(), limit=8192)


def _empty_checkpoint(path, source):
    _protected_directory(path)
    if stat.S_IMODE(path.lstat().st_mode) != 0o700 or set(_children(path, 4)) != {
        "activation.json",
        "database.json",
        "files.json",
        "media.json",
    }:
        raise ValueError("Unknown restored-empty checkpoint content")
    expected = {
        "schema_version": 1,
        "candidate_sha256": source["package_sha256"],
        "previous_present": False,
        "previous_was_enabled": False,
        "database_present": False,
        "operation": "prepare_migrated_schema",
        "preparation_id": source["preparation_id"],
        "phase": "restored_not_started",
    }
    for name, value in (
        ("activation.json", expected),
        (
            "database.json",
            {"version": 1, "present": False, "size_bytes": None, "sha256": None},
        ),
        ("files.json", {"schema_version": 1, "present": False, "files": []}),
        ('media.json', {'version': 1, 'present': False, 'entries': {}}),
    ):
        if canonical(_json(path / name)) != canonical(value):
            raise ValueError("Restored-empty absence evidence changed")


def _recovery_marker(path, ticket, secret, *, archived, uncertain=False):
    _protected_directory(path)
    if stat.S_IMODE(path.lstat().st_mode) != 0o700 or set(_children(path, 1)) != {
        "preparation-recovery.json"
    }:
        raise ValueError("Unknown preparation recovery marker")
    value = _json(path / "preparation-recovery.json")
    if (
        type(value) is not dict
        or set(value)
        not in (
            {"version", "ticket", "phase"},
            {"version", "ticket", "phase", "receipt"},
        )
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["phase"] not in {"checking", "completion_unconfirmed", "confirmed"}
    ):
        raise ValueError("Preparation recovery evidence changed")
    old = _EmptyPreparationRecoveryTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    verify_metadata(secret, "empty_preparation_recovery", old)
    expected_name = (
        (
            ".preparation-uncertain-"
            if uncertain
            else ".preparation-evidence-" if archived else ".activation-"
        )
        + old["preparation_id"]
        + ".rollback"
    )
    if path.name != expected_name or any(
        old[name] != ticket[name]
        for name in (
            *SOURCE_BINDINGS,
            "source_preparation_id",
            "source_ticket_sha256",
            "source_namespace_id",
            "source_namespace_sha256",
        )
    ):
        raise ValueError("Foreign preparation recovery evidence")
    if archived or value["phase"] == "confirmed":
        receipt = _EmptyPreparationRecoveryResult.model_validate(
            value.get("receipt")
        ).model_dump(mode="json")
        verify_metadata(secret, "empty_preparation_recovery_result", receipt)
        if (
            value["phase"] != "confirmed"
            or receipt["preparation_id"] != old["preparation_id"]
            or receipt["ticket_sha256"] != hashlib.sha256(canonical(old)).hexdigest()
        ):
            raise ValueError("Preparation recovery completion evidence changed")
    elif "receipt" in value:
        raise ValueError("Unexpected preparation recovery receipt")
    return old


def validate_restored_empty_layout(instance, ticket, source, secret):
    """Bounded closed-tree inspection; no SQLite connection or recursive scan."""
    _protected_directory(instance)
    info = instance.lstat()
    if info.st_gid != ticket["service_gid"] or stat.S_IMODE(info.st_mode) != 0o750:
        raise ValueError("Restored-empty namespace ownership changed")
    entries = _children(instance, MAX_EVIDENCE + 4)
    pending_name = ".activation-" + source["preparation_id"] + ".rollback"
    archived_name = ".preparation-evidence-" + source["preparation_id"] + ".rollback"
    if not {"releases", "data", "run"} <= entries.keys() or (
        pending_name in entries
    ) == (archived_name in entries):
        raise ValueError("Restored-empty checkpoint is missing or ambiguous")
    pending = []
    for name, path in entries.items():
        if name in {"data", "run"}:
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != ticket["service_uid"]
                or info.st_gid != ticket["service_gid"]
                or stat.S_IMODE(info.st_mode) != 0o750
                or next(path.iterdir(), None) is not None
            ):
                raise ValueError("Restored-empty data/run is not empty and owned")
        elif name == "releases":
            _protected_directory(path)
            if set(_children(path, 1)) != {ticket["package_sha256"]}:
                raise ValueError("Unexpected staged release")
            release = path / ticket["package_sha256"]
            _protected_directory(release)
            if set(_children(release, 1)) != {"service.whl"}:
                raise ValueError("Unexpected staged wheel content")
            wheel = release / "service.whl"
            info = _regular(wheel, protected=True)
            if (
                info.st_gid != ticket["service_gid"]
                or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_size > 64 * 1024 * 1024
            ):
                raise ValueError("Staged wheel ownership/budget changed")
            with wheel.open("rb") as stream:
                if (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    != ticket["service_sha256"]
                ):
                    raise ValueError("Staged wheel digest changed")
        elif name in {pending_name, archived_name}:
            _empty_checkpoint(path, source)
        elif re.fullmatch(
            r"\.(activation|preparation-evidence|preparation-uncertain)-[0-9a-f]{32}\.rollback",
            name,
        ):
            _recovery_marker(
                path,
                ticket,
                secret,
                archived=name.startswith(".preparation-evidence-"),
                uncertain=name.startswith(".preparation-uncertain-"),
            )
            if name.startswith(".activation-"):
                pending.append(path)
        else:
            raise ValueError("Unknown restored-empty lifecycle content")
    return pending


def _move(original, archive):
    if os.path.lexists(archive):
        raise ValueError("Preparation evidence cannot be overwritten")
    original.rename(archive)
    _sync_directory(original.parent)


def reconcile_restored_empty_preparation(
    package_path,
    ticket,
    source_ticket,
    namespace_ticket,
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
    if os.name != "posix" or os.geteuid() != 0 or not callable(checkpoint):
        raise RelationalPreparationError("Protected preparation recovery unavailable")
    ticket = _EmptyPreparationRecoveryTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    source = _RelationalMigrationPreparationTicket.model_validate(
        source_ticket
    ).model_dump(mode="json")
    namespace = _RelationalNamespacePreparationTicket.model_validate(
        namespace_ticket
    ).model_dump(mode="json")
    for purpose, value in (
        ("empty_preparation_recovery", ticket),
        ("migration_preparation", source),
        ("namespace_preparation", namespace),
    ):
        verify_metadata(transport_secret, purpose, value)
    if (
        ticket["source_preparation_id"] != source["preparation_id"]
        or ticket["source_namespace_id"] != namespace["preparation_id"]
        or ticket["source_ticket_sha256"]
        != hashlib.sha256(canonical(source)).hexdigest()
        or ticket["source_namespace_sha256"]
        != hashlib.sha256(canonical(namespace)).hexdigest()
        or any(
            ticket[name] != source[name]
            for name in SOURCE_BINDINGS
            if name
            not in {
                "database_lineage",
                "service_uid",
                "service_gid",
                "coordinator_uid",
                "transport_key_sha256",
            }
        )
        or ticket["database_lineage"] != source["database_lineage"]
        or any(
            ticket[name] != namespace[name]
            for name in SOURCE_BINDINGS
            if name != "database_lineage"
        )
    ):
        raise ValueError("Preparation recovery sources changed")
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
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Preparation recovery authorization unavailable")
        _stop_for_data(supervisor or SystemdApplicationSupervisor(), instance.name)
        _witness(witness, namespace, transport_secret)
        info = _regular(key_path, protected=True)
        if (
            info.st_gid != service_gid
            or stat.S_IMODE(info.st_mode) != 0o640
            or _key(key_path) != transport_secret
        ):
            raise ValueError("Preparation recovery key changed")
        validate_restored_empty_layout(instance, ticket, source, transport_secret)
        marker = instance / (".activation-" + ticket["preparation_id"] + ".rollback")
        if len(_children(instance, MAX_EVIDENCE + 4)) >= MAX_EVIDENCE + 4:
            raise ValueError("Preparation recovery checkpoint budget exceeded")
        marker.mkdir(mode=0o700)

        def phase(value, receipt=None):
            payload = {"version": 1, "ticket": ticket, "phase": value}
            if receipt is not None:
                payload["receipt"] = receipt
            _write_atomic(
                marker / "preparation-recovery.json", canonical(payload), 0o600
            )
            _sync_directory(instance)

        try:
            phase("checking")
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Preparation recovery begin unavailable")
            pending = validate_restored_empty_layout(
                instance, ticket, source, transport_secret
            )
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Preparation recovery changed")
            _live(ticket)
            phase("completion_unconfirmed")
            original = instance / (
                ".activation-" + source["preparation_id"] + ".rollback"
            )
            if os.path.lexists(original):
                _move(
                    original,
                    instance
                    / (
                        ".preparation-evidence-"
                        + source["preparation_id"]
                        + ".rollback"
                    ),
                )
            # Our pending marker fences normal preparation/backup until Core's
            # durable confirmation is acknowledged and local evidence published.
            result = _EmptyPreparationRecoveryResult.model_validate(
                sign_metadata(
                    transport_secret,
                    "empty_preparation_recovery_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "ticket_sha256": hashlib.sha256(canonical(ticket)).hexdigest(),
                        "outcome": "restored_empty_not_started",
                    },
                )
            ).model_dump(mode="json")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": result["outcome"]
            }:
                raise ValueError("Preparation recovery completion unconfirmed")
            _live(ticket)
            validate_restored_empty_layout(instance, ticket, source, transport_secret)
            if _key(key_path) != transport_secret:
                raise ValueError("Preparation recovery key changed")
            # Earlier uncertain recovery markers are retained as evidence, not
            # relabelled confirmed. The fresh confirmed ticket reconciles them.
            for path in pending:
                if path != marker:
                    _move(
                        path,
                        instance
                        / (
                            ".preparation-uncertain-"
                            + path.name.removeprefix(".activation-")
                        ),
                    )
            phase("confirmed", result)
            _move(
                marker,
                instance
                / (".preparation-evidence-" + ticket["preparation_id"] + ".rollback"),
            )
            return result
        except Exception as exc:
            raise RelationalPreparationError(
                "Preparation recovery incomplete; evidence retained, fresh review required"
            ) from exc


def validate_preparation_resumption(instance, ticket, receipt, secret):
    """A sealed Core finish alone cannot authorize bypass of a local pending ACK."""
    ticket = _EmptyPreparationRecoveryTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    receipt = _EmptyPreparationRecoveryResult.model_validate(receipt).model_dump(
        mode="json"
    )
    verify_metadata(secret, "empty_preparation_recovery", ticket)
    verify_metadata(secret, "empty_preparation_recovery_result", receipt)
    _protected_directory(instance)
    from three_mm_runtime.application_activation import _require_no_pending_rollback

    _require_no_pending_rollback(instance)
    validate_restored_empty_layout(
        instance,
        ticket,
        {
            "preparation_id": ticket["source_preparation_id"],
            "package_sha256": ticket["package_sha256"],
        },
        secret,
    )
    marker = instance / (
        ".preparation-evidence-" + ticket["preparation_id"] + ".rollback"
    )
    _recovery_marker(marker, ticket, secret, archived=True)
    if canonical(_json(marker / "preparation-recovery.json")) != canonical(
        {
            "version": 1,
            "ticket": ticket,
            "phase": "confirmed",
            "receipt": receipt,
        }
    ):
        raise ValueError("Preparation resumption witness changed")
    for name in ("data", "run"):
        path = instance / name
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != ticket["service_uid"]
            or info.st_gid != ticket["service_gid"]
            or info.st_mode & 0o022
            or next(path.iterdir(), None) is not None
        ):
            raise ValueError("Preparation resumption requires restored-empty namespace")
    if any(
        os.path.lexists(instance / name) for name in ("active.json", "relational.json")
    ):
        raise ValueError("Preparation resumption is not an upgrade")
