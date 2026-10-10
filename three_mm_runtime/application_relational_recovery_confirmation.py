"""Root-only readonly reconciliation of a fully published recovery.

No SQL writes, migrations, restore, key rotation or normal-startup bypass. The
fresh Core ticket fences older helpers; failure retains blocking evidence. Only
verified matching markers are archived after durable exact Core confirmation.
"""

import hashlib
import os
import sqlite3
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_receipts import (
    _RelationalReceiptStore,
    _validate_receipt_history,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalPreparationResult,
    _RelationalRecoveryConfirmationTicket,
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
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_database_snapshot import _preimage, _sync_directory
from three_mm_runtime.application_files_snapshot import LIMITS, _manifest
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_preparation import _auxiliary, _key, _live
from three_mm_runtime.application_relational_recovery import (
    RelationalRecoveryError,
    _published_source_checkpoint,
    _recovery_connection,
)
from three_mm_runtime.application_relational_session import (
    _clock,
    _decode,
    _PreparedLifecycle,
    _protected_directory,
    _regular,
)

MAX_CONFIRMATION_MARKERS = 32


def _json(path, limit=8192):
    if _regular(path, protected=True).st_size > limit:
        raise ValueError("Confirmation evidence exceeds metadata budget")
    return _decode(path.read_bytes(), limit=limit)


def _record(path, secret):
    record = _PreparedLifecycle.model_validate(_json(path)).model_dump(mode="json")
    verify_metadata(secret, "lifecycle", record)
    return record


def _files_preimage(marker):
    _regular(marker / "files.json", protected=True)
    manifest = _manifest(marker)
    storage = ApplicationFileStorage(marker, mode="read", limits=LIMITS)
    if manifest["present"]:
        _protected_directory(marker / "sdk-files")
    with storage._locked(write=False) as directory:
        if manifest["present"] != (directory is not None):
            raise ValueError("Confirmation files preimage incomplete")
        if directory is not None:
            if storage._entries(directory) != [
                (item["file_id"], item["size_bytes"]) for item in manifest["files"]
            ]:
                raise ValueError("Confirmation files preimage changed")
            for item in manifest["files"]:
                entry = storage._read(directory, item["file_id"])
                if entry is None or entry.sha256 != item["sha256"]:
                    raise ValueError("Confirmation files preimage corrupt")


def _snapshot_connection(preimage, ticket):
    """Only a checksum-verified CLOSED backup, never the live candidate/WAL.

    A snapshot copied from WAL retains WAL header flags. Ordinary mode=ro could
    create sidecars beside evidence and invalidate its closed-backup manifest.
    This private call site is after _preimage; no client-selectable immutable URI.
    """
    _live(ticket)
    connection = sqlite3.connect(
        preimage.absolute().as_uri() + "?mode=ro&immutable=1",
        uri=True,
        timeout=0,
        isolation_level=None,
    )
    try:
        connection.enable_load_extension(False)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.set_progress_handler(
            lambda: int(_clock()[1] >= ticket["deadline_ms"]), 1000
        )
        return connection
    except BaseException:
        connection.close()
        raise


def _markers(instance, ticket, source, secret):
    pending = []
    for pattern in (".activation-*.rollback", ".database-*.rollback"):
        for marker in instance.glob(pattern):
            pending.append(marker)
            if len(pending) > MAX_CONFIRMATION_MARKERS:
                raise ValueError("Confirmation checkpoint budget exceeded")
    recovery = instance / (".database-" + source["preparation_id"] + ".rollback")
    archived = instance / (".recovery-evidence-" + recovery.name[1:])
    if os.path.lexists(recovery) == os.path.lexists(archived):
        raise ValueError("Confirmation recovery evidence unavailable")
    evidence = recovery if os.path.lexists(recovery) else archived
    _protected_directory(evidence)
    value = _json(evidence / "recovery.json", 4096)
    if (
        value
        not in [
            {
                "version": 1,
                "recovery_id": source["preparation_id"],
                "source_preparation_id": source["source_preparation_id"],
                "source_lifecycle_sha256": source["source_lifecycle_sha256"],
                "database_lineage": source["database_lineage"],
                "phase": phase,
            }
            for phase in ("completion_unconfirmed", "prepared_not_started")
        ]
        or type(value["version"]) is not int
    ):
        raise ValueError("Recovery publication is not confirmed by exact evidence")
    preparation = instance / (
        ".activation-" + source["source_preparation_id"] + ".rollback"
    )
    if os.path.lexists(preparation):
        _published_source_checkpoint(preparation, source)
    for marker in pending:
        if marker in {recovery, preparation}:
            continue
        _protected_directory(marker)
        proof = _json(marker / "confirmation.json")
        if (
            type(proof) is not dict
            or set(proof) != {"version", "ticket", "phase"}
            or type(proof["version"]) is not int
            or proof["version"] != 1
            or proof["phase"]
            not in {"checking", "completion_unconfirmed", "prepared_not_started"}
        ):
            raise ValueError("Unknown confirmation checkpoint")
        old = _RelationalRecoveryConfirmationTicket.model_validate(
            proof["ticket"]
        ).model_dump(mode="json")
        verify_metadata(secret, "recovery_confirmation", old)
        if (
            marker.name != ".database-" + old["preparation_id"] + ".rollback"
            or old["action"] != ticket["action"]
            or any(
                old[name] != ticket[name]
                for name in (
                    "source_recovery_id",
                    "source_ticket_sha256",
                    "published_lifecycle_sha256",
                    "database_lineage",
                    "instance_id",
                    "owner_sha256",
                    "package_sha256",
                    "service_sha256",
                    "configuration_sha256",
                    "profile_sha256",
                    "schema_revision",
                    "recovery_generation",
                    "grant_record_revision",
                    "binding_sha256",
                )
            )
        ):
            raise ValueError("Foreign confirmation checkpoint")
    return pending, evidence


def confirm_published_relational_recovery(
    package_path,
    ticket,
    source_ticket,
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
    """Trusted helper, no application-supplied paths or key and no SQL replay."""
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid <= 0
    ):
        raise RelationalRecoveryError("Protected recovery confirmation unavailable")
    ticket = _RelationalRecoveryConfirmationTicket.model_validate(ticket).model_dump(
        mode="json"
    )
    source = _RelationalRecoveryTicket.model_validate(source_ticket).model_dump(
        mode="json"
    )
    root, key_root, state_root, package_path = map(
        Path, (root, key_root, state_root, package_path)
    )
    if _regular(package_path).st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Confirmation package too large")
    blob = package_path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != ticket["package_sha256"]:
        raise ValueError("Confirmation artifact changed")
    validated = validate_module_package(blob)
    definition = validated.application_extension
    if definition is None or definition.storage.relational is None:
        raise ValueError("Confirmation declaration unavailable")
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
    if any(ticket[name] != value for name, value in expected.items()):
        raise ValueError("Confirmation candidate changed")
    instance = root / ticket["instance_id"]
    database = instance / "data" / "state.sqlite3"
    key_path = key_root / (instance.name + ".key")
    selected = supervisor or SystemdApplicationSupervisor()
    with _release_lock(), _runtime_lock(state_root):
        for path in (root, instance, instance / "releases", key_root):
            _protected_directory(path)
        for path in (instance / "data", instance / "run"):
            info = path.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != service_uid
                or info.st_mode & 0o022
            ):
                raise ValueError("Confirmation own namespace changed")
        secret = _key(key_path)
        verify_metadata(secret, "recovery_confirmation", ticket)
        verify_metadata(secret, "recovery", source)
        record = recovered_lifecycle(source, secret)
        if (
            ticket["source_recovery_id"] != source["preparation_id"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(source)).hexdigest()
            or ticket["published_lifecycle_sha256"]
            != hashlib.sha256(canonical(record)).hexdigest()
            or any(
                ticket[name] != record[name]
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
                )
            )
        ):
            raise ValueError("Confirmation source changed")
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Core confirmation authorization unavailable")
        pending, evidence = _markers(instance, ticket, source, secret)
        if not pending:
            raise ValueError("No interrupted recovery requires confirmation")
        marker = instance / (".database-" + ticket["preparation_id"] + ".rollback")
        marker.mkdir(mode=0o700)

        def phase(value):
            _write_atomic(
                marker / "confirmation.json",
                canonical({"version": 1, "ticket": ticket, "phase": value}),
                0o600,
            )

        phase("checking")
        try:
            _stop_for_data(selected, instance.name)
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core confirmation begin unavailable")
            metadata = _application_metadata(
                validated, configuration, instance.name, root
            )
            metadata["storage"]["relational"] = (
                definition.storage.relational.model_dump(mode="json")
            )
            if (
                _json(instance / "active.json", 131072) != metadata
                or _record(instance / "relational.json", secret) != record
            ):
                raise ValueError("Confirmation publication incomplete")
            release = instance / "releases" / ticket["package_sha256"]
            _protected_directory(release)
            wheel = release / "service.whl"
            _regular(wheel, protected=True)
            with wheel.open("rb") as stream:
                if (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    != ticket["service_sha256"]
                ):
                    raise ValueError("Confirmation wheel changed")
            if _regular(database).st_uid != service_uid:
                raise ValueError("Confirmation database owner changed")
            _auxiliary(database, definition.storage.relational)
            preimage = evidence / "state.sqlite3"
            _regular(evidence / "database.json", protected=True)
            if (
                _regular(preimage, protected=True).st_size
                > definition.storage.relational.max_database_bytes
            ):
                raise ValueError("Confirmation preimage exceeds profile")
            _preimage(preimage, True)
            previous = _record(evidence / "previous-relational.json", secret)
            if (
                hashlib.sha256(canonical(previous)).hexdigest()
                != source["source_lifecycle_sha256"]
            ):
                raise ValueError("Confirmation preimage lineage changed")
            if _json(evidence / "previous-active.json", 131072) != metadata:
                raise ValueError("Confirmation preimage publication changed")
            _files_preimage(evidence)
            for path, lineage in (
                (preimage, previous["database_lineage"]),
                (database, ticket["database_lineage"]),
            ):
                connection = (
                    _snapshot_connection(preimage, ticket)
                    if path == preimage
                    else _recovery_connection(
                        database, ticket, definition.storage.relational, write=False
                    )
                )
                try:
                    connection.execute("BEGIN")
                    _RelationalReceiptStore(
                        database_lineage=lineage,
                        schema_revision=ticket["schema_revision"],
                        secret=secret,
                    )._validate(connection)
                    _validate_receipt_history(
                        connection,
                        schema_revision=ticket["schema_revision"],
                        secret=secret,
                    )
                finally:
                    connection.close()
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core confirmation changed")
            if _key(key_path) != secret:
                raise ValueError("Confirmation transport key changed")
            _live(ticket)
            result = sign_metadata(
                secret,
                "recovery_confirmation_result",
                {
                    "version": 1,
                    "preparation_id": ticket["preparation_id"],
                    "lifecycle_sha256": ticket["published_lifecycle_sha256"],
                    "outcome": "prepared_not_started",
                },
            )
            phase("completion_unconfirmed")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "prepared_not_started"
            }:
                raise ValueError("Core confirmation completion unconfirmed")
            if _key(key_path) != secret:
                raise ValueError("Confirmation transport key changed before archive")
            _live(ticket)
            phase("prepared_not_started")
            for path in (*pending, marker):
                archived = instance / (".recovery-evidence-" + path.name[1:])
                if os.path.lexists(archived):
                    raise ValueError("Confirmation archive already exists")
                path.rename(archived)
                _sync_directory(instance)
            return _RelationalPreparationResult.model_validate(result).model_dump(
                mode="json"
            )
        except Exception as exc:
            raise RelationalRecoveryError(
                "Confirmation incomplete; evidence retained, explicit review required"
            ) from exc
