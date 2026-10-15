"""Protected acceptance of a witnessed rollback, with separate restore consent.

No backup replay, SQL write, code import, key rotation, package switch or start.
Readonly consent cannot repair a partial restore. Only a distinct fresh restore
ticket may finish the fixed preimage restore, retaining intermediate evidence.
"""

import hashlib
import os
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from three_mm_application_sdk.files import ApplicationFileStorage
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeRollbackProof,
    _RelationalUpgradeRollbackResult,
    _RelationalUpgradeTicket,
    _rollback_ticket,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_database_snapshot import (
    _preimage,
    _sync_directory,
    capture_database,
)
from three_mm_runtime.application_files_snapshot import LIMITS, _manifest
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_boot_policy import require_no_boot_gate
from three_mm_runtime.application_relational_preparation import _auxiliary, _key, _live
from three_mm_runtime.application_relational_recovery_confirmation import (
    MAX_CONFIRMATION_MARKERS,
    _files_preimage,
    _json,
    _snapshot_connection,
)
from three_mm_runtime.application_relational_session import (
    _protected_directory,
    _regular,
)
from three_mm_runtime.application_relational_upgrade import (
    RelationalUpgradeError,
    _package,
    _source_state,
)
from three_mm_runtime.application_relational_upgrade_confirmation import (
    _history,
    _preimage_metadata,
    _wheel,
)

FIELDS = (
    "source_upgrade_id",
    "source_ticket_sha256",
    "restored_lifecycle_sha256",
    "database_lineage",
    "instance_id",
    "owner_sha256",
    "package_sha256",
    "service_sha256",
    "configuration_sha256",
    "profile_sha256",
    "schema_revision",
    "recovery_generation",
    "transport_key_sha256",
    "grant_record_revision",
    "binding_sha256",
)


def _hash(path, *, protected=False, limit=None):
    size = _regular(path, protected=protected).st_size
    if limit is not None and size > limit:
        raise ValueError("Rollback proof exceeds byte budget")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _coherent_snapshot(database, directory, limit):
    # A normal readonly source connection includes committed WAL; never mark
    # the LIVE database immutable or delete its sidecars. The fixed backup API
    # writes only this newly created protected proof directory.
    _hash(database, limit=limit)
    directory.mkdir(mode=0o700)
    snapshot = directory / "state.sqlite3"
    if not capture_database(database, snapshot):
        raise ValueError("Restored database disappeared")
    return _hash(snapshot, protected=True, limit=limit)


def record_completed_rollback(instance, evidence, source, secret, *, database_limit):
    """Called only at the END of the original verified restore under its locks.

    Bind exact restored bytes to this attempt, before the restored phase becomes
    durable. We do not later infer coherence from schema/receipts alone (which
    would miss changed business rows), or normalize away SQLite header bytes.
    """
    _preimage(evidence / "state.sqlite3", True)
    proof = _RelationalUpgradeRollbackProof.model_validate(
        sign_metadata(
            secret,
            "database_upgrade_rollback_proof",
            {
                "version": 1,
                "preparation_id": source["preparation_id"],
                "source_ticket_sha256": hashlib.sha256(canonical(source)).hexdigest(),
                "lifecycle_sha256": source["source_lifecycle_sha256"],
                "outcome": "restored_not_started",
                "database_sha256": _coherent_snapshot(
                    instance / "data/state.sqlite3",
                    evidence / "restored-proof",
                    database_limit,
                ),
                "preimage_sha256": _hash(
                    evidence / "state.sqlite3", protected=True, limit=database_limit
                ),
                "files_manifest_sha256": _hash(
                    evidence / "files.json", protected=True, limit=256 * 1024
                ),
            },
        )
    ).model_dump(mode="json")
    _write_atomic(
        evidence / "rollback-proof.json", canonical(proof), 0o600, uid=0, gid=0
    )


def _markers(instance, ticket, source, secret):
    pending = []
    for pattern in (".activation-*.rollback", ".database-*.rollback"):
        for path in instance.glob(pattern):
            pending.append(path)
            if len(pending) >= MAX_CONFIRMATION_MARKERS:
                raise ValueError("Rollback confirmation checkpoint budget exceeded")
    original = instance / (".database-" + source["preparation_id"] + ".rollback")
    archived = instance / (".upgrade-rollback-evidence-" + source["preparation_id"])
    if os.path.lexists(original) == os.path.lexists(archived):
        raise ValueError("Rollback evidence unavailable or archive collision")
    evidence = original if os.path.lexists(original) else archived
    _protected_directory(evidence)
    value = _json(evidence / "upgrade.json")
    if (
        type(value) is not dict
        or type(value.get("version")) is not int
        or value
        != {
            "version": 1,
            "ticket": source,
            "phase": (
                "restoring"
                if ticket["action"] == "finish_interrupted_upgrade_restore"
                else "restored_not_started"
            ),
        }
    ):
        raise ValueError("Upgrade rollback is not a completed restore")
    embedded = _RelationalUpgradeTicket.model_validate(value["ticket"]).model_dump(
        mode="json"
    )
    verify_metadata(secret, "database_upgrade", embedded)
    for path in pending:
        if path == original:
            continue
        _protected_directory(path)
        proof = _json(path / "rollback-confirmation.json")
        if (
            type(proof) is not dict
            or set(proof) != {"version", "ticket", "phase"}
            or type(proof["version"]) is not int
            or proof["version"] != 1
            or proof["phase"]
            not in {
                "checking",
                "restoring",
                "completion_unconfirmed",
                "restored_not_started",
            }
        ):
            raise ValueError("Unknown rollback confirmation checkpoint")
        old, purpose = _rollback_ticket(proof["ticket"])
        verify_metadata(secret, purpose, old)
        if (
            proof["phase"] == "restoring"
            and old["action"] != "finish_interrupted_upgrade_restore"
        ):
            raise ValueError("Invalid readonly rollback phase")
        if path.name != ".database-" + old["preparation_id"] + ".rollback" or any(
            old[name] != ticket[name] for name in FIELDS
        ):
            raise ValueError("Foreign rollback confirmation checkpoint")
    return pending, evidence


def _live_files(data, evidence):
    manifest = _manifest(evidence)
    storage = ApplicationFileStorage(data, mode="read", limits=LIMITS)
    with storage._locked(write=False) as directory:
        if manifest["present"] != (directory is not None):
            raise ValueError("Restored private files presence changed")
        if directory is not None:
            if storage._entries(directory) != [
                (item["file_id"], item["size_bytes"]) for item in manifest["files"]
            ]:
                raise ValueError("Restored private files changed")
            for item in manifest["files"]:
                entry = storage._read(directory, item["file_id"])
                if entry is None or entry.sha256 != item["sha256"]:
                    raise ValueError("Restored private file content changed")


def confirm_restored_relational_upgrade(
    source_package_path,
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
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid <= 0
    ):
        raise RelationalUpgradeError("Protected rollback confirmation unavailable")
    ticket, purpose = _rollback_ticket(ticket)
    source = _RelationalUpgradeTicket.model_validate(source_ticket).model_dump(
        mode="json"
    )
    root, key_root, state_root = map(Path, (root, key_root, state_root))
    previous, _ = _package(source_package_path, source["source_package_sha256"])
    target, _ = _package(package_path, ticket["package_sha256"])
    definition = target.application_extension
    configuration = resolve_application_configuration(
        target.manifest.configuration_schema,
        target.manifest.configuration_defaults,
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
    if previous.application_extension.module_id != definition.module_id or any(
        ticket[name] != value for name, value in expected.items()
    ):
        raise ValueError("Rollback confirmation target changed")
    instance = root / ticket["instance_id"]
    database = instance / "data/state.sqlite3"
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
                raise ValueError("Rollback confirmation namespace changed")
        require_no_boot_gate(instance)
        secret = _key(key_path)
        verify_metadata(secret, purpose, ticket)
        verify_metadata(secret, "database_upgrade", source)
        if (
            ticket["source_upgrade_id"] != source["preparation_id"]
            or ticket["source_ticket_sha256"]
            != hashlib.sha256(canonical(source)).hexdigest()
            or ticket["restored_lifecycle_sha256"] != source["source_lifecycle_sha256"]
            or ticket["database_lineage"] != source["source_database_lineage"]
            or ticket["transport_key_sha256"] != hashlib.sha256(secret).hexdigest()
            or any(
                ticket[name] != source[name]
                for name in FIELDS
                if name in source
                and name
                not in {
                    "source_ticket_sha256",
                    "database_lineage",
                    "grant_record_revision",
                    "binding_sha256",
                }
            )
        ):
            raise ValueError("Rollback confirmation source changed")
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Core rollback confirmation authorization unavailable")
        pending, evidence = _markers(instance, ticket, source, secret)
        if not pending:
            raise ValueError("No interrupted rollback requires confirmation")
        marker = instance / (".database-" + ticket["preparation_id"] + ".rollback")
        marker.mkdir(mode=0o700)

        def phase(value):
            _write_atomic(
                marker / "rollback-confirmation.json",
                canonical({"version": 1, "ticket": ticket, "phase": value}),
                0o600,
                uid=0,
                gid=0,
            )

        phase("checking")
        try:
            _stop_for_data(selected, instance.name)
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core rollback confirmation begin unavailable")
            if ticket["action"] == "finish_interrupted_upgrade_restore":
                from three_mm_runtime.application_relational_upgrade_restore import (
                    finish_partial_restore,
                )

                def current():
                    _live(ticket)
                    if _key(key_path) != secret or checkpoint(ticket, "check") != {
                        "state": "execution_unconfirmed"
                    }:
                        raise ValueError("Partial restore consent changed")

                phase("restoring")
                finish_partial_restore(
                    instance,
                    evidence,
                    marker,
                    source,
                    previous,
                    target,
                    configuration,
                    secret,
                    root=root,
                    service_uid=service_uid,
                    service_gid=service_gid,
                    check=current,
                    ticket=ticket,
                )
            active, record = _source_state(instance, previous, source, secret, root)
            _preimage_metadata(instance, evidence, previous, source, secret, root)
            if (
                active != (evidence / "previous-active.json").read_bytes()
                or record != (evidence / "previous-relational.json").read_bytes()
            ):
                raise ValueError("Restored publication changed")
            _wheel(instance, ticket["package_sha256"], ticket["service_sha256"])
            _files_preimage(evidence)
            _live_files(instance / "data", evidence)
            proof = _RelationalUpgradeRollbackProof.model_validate(
                _json(evidence / "rollback-proof.json")
            ).model_dump(mode="json")
            verify_metadata(secret, "database_upgrade_rollback_proof", proof)
            limit = previous.application_extension.storage.relational.max_database_bytes
            _regular(evidence / "database.json", protected=True)
            _preimage(evidence / "state.sqlite3", True)
            verified = evidence / "restored-proof"
            _protected_directory(verified)
            _regular(verified / "database.json", protected=True)
            _preimage(verified / "state.sqlite3", True)
            actual = marker / "current-proof"
            _auxiliary(database, previous.application_extension.storage.relational)
            actual_digest = _coherent_snapshot(database, actual, limit)
            if (
                proof["preparation_id"] != source["preparation_id"]
                or proof["source_ticket_sha256"] != ticket["source_ticket_sha256"]
                or proof["lifecycle_sha256"] != ticket["restored_lifecycle_sha256"]
                or proof["preimage_sha256"]
                != _hash(evidence / "state.sqlite3", protected=True, limit=limit)
                or proof["files_manifest_sha256"]
                != _hash(evidence / "files.json", protected=True, limit=256 * 1024)
                or _regular(database).st_uid != service_uid
                or proof["database_sha256"]
                != _hash(verified / "state.sqlite3", protected=True, limit=limit)
                or proof["database_sha256"] != actual_digest
            ):
                raise ValueError("Restored rollback proof changed")
            histories = []
            for path in (evidence / "state.sqlite3", actual / "state.sqlite3"):
                _preimage(path, True)
                connection = _snapshot_connection(path, ticket)
                try:
                    connection.execute("BEGIN")
                    histories.append(
                        _history(
                            connection,
                            source["source_database_lineage"],
                            source["source_schema_revision"],
                            secret,
                        )
                    )
                finally:
                    connection.close()
            if histories[0] != histories[1]:
                raise ValueError("Restored history changed")
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core rollback confirmation changed")
            if _key(key_path) != secret:
                raise ValueError("Rollback confirmation key changed")
            _live(ticket)
            result = _RelationalUpgradeRollbackResult.model_validate(
                sign_metadata(
                    secret,
                    "database_upgrade_rollback_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "source_upgrade_id": source["preparation_id"],
                        "lifecycle_sha256": ticket["restored_lifecycle_sha256"],
                        "rollback_proof_sha256": hashlib.sha256(
                            canonical(proof)
                        ).hexdigest(),
                        "outcome": "restored_not_started",
                    },
                )
            ).model_dump(mode="json")
            phase("completion_unconfirmed")
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "restored_not_started"
            }:
                raise ValueError("Core rollback confirmation completion unconfirmed")
            if _key(key_path) != secret:
                raise ValueError("Rollback confirmation key changed before archive")
            _live(ticket)
            phase("restored_not_started")
            for path in (*pending, marker):
                destination = instance / (
                    ".upgrade-rollback-evidence-"
                    + path.name.removeprefix(".database-").removesuffix(".rollback")
                )
                if os.path.lexists(destination):
                    raise ValueError("Rollback confirmation archive already exists")
                path.rename(destination)
                _sync_directory(instance)
            return result
        except Exception as error:
            raise RelationalUpgradeError(
                "Rollback confirmation incomplete; evidence retained, explicit review required"
            ) from error
