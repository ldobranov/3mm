"""Protected accept-candidate recovery, never restore/migration/SQL replay.

Only a fully published exact candidate with valid old receipt metadata can be
accepted. Pending migration, unconfirmed worker stop, partial publication,
foreign/unknown checkpoints and key drift remain refused. Ordinary startup has
no bypass. Evidence is archived, not erased; all failures stay stopped/blocked.
"""

import hashlib
import os
import sqlite3
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from three_mm_application_sdk.relational_receipts import (
    _recover_receipt_lineage,
    _RelationalReceiptStore,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalPreparationResult,
    _RelationalRecoveryTicket,
    canonical,
    profile_digest,
    recovered_lifecycle,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _application_metadata,
    _set_owner,
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_database_snapshot import (
    _sync_directory,
    capture_database,
)
from three_mm_runtime.application_files_snapshot import capture_private_files
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_preparation import (
    _auxiliary,
    _connection,
    _key,
    _live,
    _stage_wheel,
)
from three_mm_runtime.application_relational_session import (
    _decode,
    _PreparedLifecycle,
    _protected_directory,
    _regular,
)


class RelationalRecoveryError(RuntimeError):
    pass


def _recovery_connection(database, ticket, declaration, *, write):
    connection = _connection(database, ticket, declaration, write=write)
    # Fixed SDK metadata only; oversized/tampered rows cannot allocate arbitrary
    # Python payloads. No business rows are evaluated by this helper.
    connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
    return connection


def _source_marker(instance, ticket):
    pending = list(instance.glob(".activation-*.rollback")) + list(
        instance.glob(".database-*.rollback")
    )
    expected = instance / (
        ".activation-" + ticket["source_preparation_id"] + ".rollback"
    )
    if not pending:
        return None
    if pending != [expected]:
        raise ValueError("Unknown or overlapping relational recovery is pending")
    _published_source_checkpoint(expected, ticket)
    return expected


def _published_source_checkpoint(expected, ticket):
    """Validate a fixed preparation marker, including an archived preimage."""
    _protected_directory(expected)
    path = expected / "activation.json"
    if _regular(path, protected=True).st_size > 4096:
        raise ValueError("Recovery source checkpoint is too large")
    value = _decode(path.read_bytes(), limit=4096)
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema_version",
            "candidate_sha256",
            "previous_present",
            "previous_was_enabled",
            "database_present",
            "operation",
            "preparation_id",
            "phase",
        }
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["candidate_sha256"] != ticket["package_sha256"]
        or value["preparation_id"] != ticket["source_preparation_id"]
        or value["operation"]
        not in {"prepare_existing_schema", "prepare_migrated_schema"}
        or value["phase"] not in {"completion_unconfirmed", "prepared_not_started"}
        or value["previous_was_enabled"] is not False
        or type(value["previous_present"]) is not bool
        or type(value["database_present"]) is not bool
    ):
        raise ValueError("Source is not a confirmed published candidate")


def accept_prepared_relational_candidate(
    package_path,
    ticket,
    *,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    checkpoint,
    supervisor=None,
):
    """Trusted root-helper action; no service factory, rekey or enable/restart.

    Validation failure never repairs a mismatched source. Once this one-use
    recovery begins, any interruption preserves the current candidate/preimage
    and a blocking checkpoint. It does not restore over a possibly committed
    lineage, clear unknown work or retry the caller's ticket.
    """
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid <= 0
    ):
        raise RelationalRecoveryError("Protected relational recovery unavailable")
    ticket = _RelationalRecoveryTicket.model_validate(ticket).model_dump(mode="json")
    root, key_root, state_root = map(Path, (root, key_root, state_root))
    package_path = Path(package_path)
    if _regular(package_path).st_size > MAX_PACKAGE_BYTES:
        raise RelationalRecoveryError("Recovery package too large")
    blob = package_path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != ticket["package_sha256"]:
        raise RelationalRecoveryError("Recovery artifact changed")
    validated = validate_module_package(blob)
    definition = validated.application_extension
    if definition is None or definition.storage.relational is None:
        raise RelationalRecoveryError("Recovery declaration unavailable")
    configuration = resolve_application_configuration(
        validated.manifest.configuration_schema,
        validated.manifest.configuration_defaults,
        definition,
        overrides=configuration,
    )
    expected = {
        "instance_id": application_instance_id(definition.module_id),
        "service_sha256": definition.service.artifact_sha256,
        "configuration_sha256": hashlib.sha256(canonical(configuration)).hexdigest(),
        "profile_sha256": profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        ),
        "schema_revision": definition.storage.schema_revision,
    }
    if any(ticket[name] != item for name, item in expected.items()):
        raise RelationalRecoveryError("Recovery identity changed")
    instance = root / ticket["instance_id"]
    data, database = instance / "data", instance / "data" / "state.sqlite3"
    key_path = key_root / (instance.name + ".key")
    active, record_path = instance / "active.json", instance / "relational.json"
    selected = supervisor or SystemdApplicationSupervisor()
    with _release_lock(), _runtime_lock(state_root):
        for path in (root, instance, instance / "releases", key_root):
            _protected_directory(path)
        for path in (data, instance / "run"):
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != service_uid
                or info.st_mode & 0o022
            ):
                raise RelationalRecoveryError("Recovery own namespace unavailable")
        secret = _key(key_path)
        verify_metadata(secret, "recovery", ticket)
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise RelationalRecoveryError("Core recovery authorization unavailable")
        source_marker = _source_marker(instance, ticket)
        if (
            _regular(record_path, protected=True).st_size > 8192
            or _regular(active, protected=True).st_size > 131072
        ):
            raise RelationalRecoveryError("Recovery source metadata too large")
        previous_record, previous_active = record_path.read_bytes(), active.read_bytes()
        source = _PreparedLifecycle.model_validate(_decode(previous_record)).model_dump(
            mode="json"
        )
        verify_metadata(secret, "lifecycle", source)
        if (
            hashlib.sha256(canonical(source)).hexdigest()
            != ticket["source_lifecycle_sha256"]
            or source["lifecycle_id"] != ticket["source_preparation_id"]
            or source["database_lineage"] == ticket["database_lineage"]
            or any(
                source[name] != ticket[name]
                for name in (
                    "instance_id",
                    "owner_sha256",
                    "package_sha256",
                    "service_sha256",
                    "configuration_sha256",
                    "profile_sha256",
                    "schema_revision",
                    "recovery_generation",
                )
            )
        ):
            raise RelationalRecoveryError("Recovery source lineage changed")
        metadata = _application_metadata(validated, configuration, instance.name, root)
        metadata["storage"]["relational"] = definition.storage.relational.model_dump(
            mode="json"
        )
        if _decode(previous_active, limit=131072) != metadata:
            raise RelationalRecoveryError("Recovery source publication changed")
        # Never stage or repair a missing wheel. Exact publication is prerequisite.
        release = instance / "releases" / ticket["package_sha256"]
        _protected_directory(release)
        _regular(release / "service.whl", protected=True)
        _stage_wheel(instance, validated, blob, definition, service_gid, ticket)
        if _regular(database).st_uid != service_uid:
            raise RelationalRecoveryError("Recovery database owner changed")
        _auxiliary(database, definition.storage.relational)
        evidence = instance / (".database-" + ticket["preparation_id"] + ".rollback")
        evidence.mkdir(mode=0o700)

        def phase(value):
            _write_atomic(
                evidence / "recovery.json",
                canonical(
                    {
                        "version": 1,
                        "recovery_id": ticket["preparation_id"],
                        "source_preparation_id": ticket["source_preparation_id"],
                        "source_lifecycle_sha256": ticket["source_lifecycle_sha256"],
                        "database_lineage": ticket["database_lineage"],
                        "phase": value,
                    }
                ),
                0o600,
            )

        phase("preparing")
        try:
            _stop_for_data(selected, instance.name)
            _live(ticket)
            if not capture_database(database, evidence / "state.sqlite3"):
                raise ValueError("Recovery database disappeared")
            capture_private_files(data, evidence)
            _write_atomic(evidence / "previous-active.json", previous_active, 0o600)
            _write_atomic(evidence / "previous-relational.json", previous_record, 0o600)
            connection = _recovery_connection(
                database, ticket, definition.storage.relational, write=False
            )
            try:
                connection.execute("BEGIN")
                _RelationalReceiptStore(
                    database_lineage=source["database_lineage"],
                    schema_revision=ticket["schema_revision"],
                    secret=secret,
                )._validate(connection)
            finally:
                connection.close()
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core recovery begin unavailable")
            phase("relineaging")
            connection = _recovery_connection(
                database, ticket, definition.storage.relational, write=True
            )
            try:
                connection.execute("BEGIN IMMEDIATE")
                _recover_receipt_lineage(
                    connection,
                    previous_lineage=source["database_lineage"],
                    database_lineage=ticket["database_lineage"],
                    schema_revision=ticket["schema_revision"],
                    secret=secret,
                )
                _auxiliary(database, definition.storage.relational)
                _live(ticket)
                connection.commit()
            finally:
                connection.close()
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core recovery publication unavailable")
            if _key(key_path) != secret:
                raise ValueError("Recovery transport key changed")
            _live(ticket)
            record = recovered_lifecycle(ticket, secret)
            phase("publishing")
            _write_atomic(record_path, canonical(record), 0o640)
            _set_owner(record_path, 0, service_gid)
            if (
                record_path.read_bytes() != canonical(record)
                or active.read_bytes() != previous_active
            ):
                raise ValueError("Recovery publication changed")
            connection = _recovery_connection(
                database, ticket, definition.storage.relational, write=False
            )
            try:
                connection.execute("BEGIN")
                _RelationalReceiptStore(
                    database_lineage=ticket["database_lineage"],
                    schema_revision=ticket["schema_revision"],
                    secret=secret,
                )._validate(connection)
            finally:
                connection.close()
            _set_owner(database, service_uid, service_gid)
            for suffix in ("-wal", "-shm", "-journal"):
                path = database.with_name(database.name + suffix)
                if os.path.lexists(path):
                    _regular(path)
                    _set_owner(path, service_uid, service_gid)
            _auxiliary(database, definition.storage.relational)
            if _key(key_path) != secret:
                raise ValueError("Recovery transport key changed")
            _live(ticket)
            result = sign_metadata(
                secret,
                "recovery_result",
                {
                    "version": 1,
                    "preparation_id": ticket["preparation_id"],
                    "lifecycle_sha256": hashlib.sha256(canonical(record)).hexdigest(),
                    "outcome": "prepared_not_started",
                },
            )
            phase("completion_unconfirmed")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "prepared_not_started"
            }:
                raise ValueError("Core recovery completion unconfirmed")
            phase("prepared_not_started")
            # Same protected parent, fixed evidence targets; no deletion/replay.
            for marker in (source_marker, evidence):
                if marker is not None:
                    archived = instance / (".recovery-evidence-" + marker.name[1:])
                    if os.path.lexists(archived):
                        raise ValueError("Recovery evidence archive already exists")
                    marker.rename(archived)
                    _sync_directory(instance)
            return _RelationalPreparationResult.model_validate(result).model_dump(
                mode="json"
            )
        except Exception as exc:
            raise RelationalRecoveryError(
                "Recovery incomplete; evidence retained, explicit review required"
            ) from exc
