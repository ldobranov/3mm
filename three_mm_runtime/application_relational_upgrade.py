"""Protected forward upgrade of an existing prepared own database.

No namespace/key creation, service factory, automatic restart or public helper
dispatch. Uncertain finish/worker stop preserves blocking candidate evidence.
"""

import hashlib
import os
import stat
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from three_mm_application_sdk.relational_receipts import _RelationalReceiptStore
from three_mm_application_sdk.relational_upgrade_receipts import (
    receipt_metadata_digest,
    upgrade_receipt_lineage,
    validate_upgrade_history,
)
from three_mm_application_sdk.relational_upgrade_wire import (
    _RelationalUpgradeResult,
    _RelationalUpgradeTicket,
    upgrade_worker_profile_digest,
    upgraded_lifecycle,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    profile_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_runtime.application_activation import (
    SystemdApplicationSupervisor,
    _application_metadata,
    _require_no_pending_rollback,
    _set_owner,
    _stop_for_data,
    _write_atomic,
    application_instance_id,
)
from three_mm_runtime.application_database_snapshot import (
    _sync_directory,
    capture_database,
    restore_database,
    validate_database_restore,
)
from three_mm_runtime.application_files_snapshot import (
    capture_private_files,
    restore_private_files,
)
from three_mm_runtime.application_lifecycle import _release_lock, _runtime_lock
from three_mm_runtime.application_relational_migrations import (
    MigrationWorkerUnconfirmed,
    require_migration_worker_privileges,
    run_prepared_upgrade_migrations,
)
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


class RelationalUpgradeError(RuntimeError):
    pass


def _package(path, digest):
    path = Path(path)
    if _regular(path).st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Upgrade package exceeds budget")
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != digest:
        raise ValueError("Upgrade exact artifact changed")
    validated = validate_module_package(blob)
    if (
        validated.application_extension is None
        or validated.application_extension.storage.relational is None
    ):
        raise ValueError("Upgrade requires declared relational storage")
    return validated, blob


def _metadata(validated, configuration, instance, root):
    value = _application_metadata(validated, configuration, instance.name, root)
    value["storage"]["relational"] = (
        validated.application_extension.storage.relational.model_dump(mode="json")
    )
    return value


def _source_state(instance, source, ticket, secret, root):
    for name, limit in (("active.json", 131072), ("relational.json", 8192)):
        if not 0 < _regular(instance / name, protected=True).st_size <= limit:
            raise ValueError("Upgrade source metadata exceeds budget")
    previous_active = (instance / "active.json").read_bytes()
    previous_record = (instance / "relational.json").read_bytes()
    record = _PreparedLifecycle.model_validate(_decode(previous_record)).model_dump(
        mode="json"
    )
    verify_metadata(secret, "lifecycle", record)
    if (
        hashlib.sha256(canonical(record)).hexdigest()
        != ticket["source_lifecycle_sha256"]
        or record["lifecycle_id"] != ticket["source_preparation_id"]
        or any(
            record[name] != ticket[name]
            for name in ("instance_id", "owner_sha256", "recovery_generation")
        )
        or any(
            record[name] != ticket["source_" + name]
            for name in (
                "package_sha256",
                "service_sha256",
                "configuration_sha256",
                "profile_sha256",
                "schema_revision",
                "database_lineage",
            )
        )
    ):
        raise ValueError("Upgrade protected source changed")
    definition = source.application_extension
    old_active = _decode(previous_active, limit=131072)
    configuration = resolve_application_configuration(
        source.manifest.configuration_schema,
        source.manifest.configuration_defaults,
        definition,
        overrides=old_active.get("configuration"),
    )
    if (
        old_active != _metadata(source, configuration, instance, root)
        or hashlib.sha256(canonical(configuration)).hexdigest()
        != ticket["source_configuration_sha256"]
        or definition.service.artifact_sha256 != ticket["source_service_sha256"]
        or definition.storage.schema_revision != ticket["source_schema_revision"]
        or profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        )
        != ticket["source_profile_sha256"]
    ):
        raise ValueError("Upgrade source package/publication changed")
    wheel = instance / "releases" / source.sha256 / "service.whl"
    _protected_directory(wheel.parent)
    _regular(wheel, protected=True)
    with wheel.open("rb") as stream:
        if (
            hashlib.file_digest(stream, "sha256").hexdigest()
            != ticket["source_service_sha256"]
        ):
            raise ValueError("Upgrade source wheel changed")
    return previous_active, previous_record


def upgrade_prepared_relational_database(
    source_package_path,
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
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid <= 0
    ):
        raise RelationalUpgradeError("Protected upgrade helper unavailable")
    require_migration_worker_privileges()
    ticket = _RelationalUpgradeTicket.model_validate(ticket).model_dump(mode="json")
    if ticket["worker_profile_sha256"] != upgrade_worker_profile_digest():
        raise ValueError("Upgrade worker profile changed")
    root, key_root, state_root = map(Path, (root, key_root, state_root))
    source, _ = _package(source_package_path, ticket["source_package_sha256"])
    target, blob = _package(package_path, ticket["package_sha256"])
    definition = target.application_extension
    configuration = resolve_application_configuration(
        target.manifest.configuration_schema,
        target.manifest.configuration_defaults,
        definition,
        overrides=configuration,
    )
    if (
        source.application_extension.module_id != definition.module_id
        or ticket["instance_id"] != application_instance_id(definition.module_id)
        or ticket["service_sha256"] != definition.service.artifact_sha256
        or ticket["schema_revision"] != definition.storage.schema_revision
        or ticket["configuration_sha256"]
        != hashlib.sha256(canonical(configuration)).hexdigest()
        or ticket["profile_sha256"]
        != profile_digest(
            definition.storage.relational, definition.storage.schema_revision
        )
    ):
        raise RelationalUpgradeError("Upgrade target binding changed")
    instance = root / ticket["instance_id"]
    data, database = instance / "data", instance / "data" / "state.sqlite3"
    key_path = key_root / (instance.name + ".key")
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
                raise ValueError("Upgrade own namespace changed")
        from three_mm_runtime.application_relational_boot_policy import (
            require_no_boot_gate,
        )

        require_no_boot_gate(instance)
        _require_no_pending_rollback(instance)
        if _regular(database).st_uid != service_uid:
            raise ValueError("Upgrade database principal changed")
        secret = _key(key_path)
        if hashlib.sha256(secret).hexdigest() != ticket["transport_key_sha256"]:
            raise ValueError("Upgrade transport key changed")
        verify_metadata(secret, "database_upgrade", ticket)
        _live(ticket)
        previous_active, previous_record = _source_state(
            instance, source, ticket, secret, root
        )
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise ValueError("Core upgrade authorization unavailable")
        rollback = instance / (".database-" + ticket["preparation_id"] + ".rollback")
        rollback.mkdir(mode=0o700)

        def phase(value):
            _write_atomic(
                rollback / "upgrade.json",
                canonical({"version": 1, "ticket": ticket, "phase": value}),
                0o600,
                uid=0,
                gid=0,
            )

        preimage, mutated, finishing = False, False, False
        phase("preparing")
        try:
            _stop_for_data(selected, instance.name)
            _live(ticket)
            if not capture_database(database, rollback / "state.sqlite3"):
                raise ValueError("Prepared database disappeared")
            capture_private_files(data, rollback)
            _write_atomic(
                rollback / "previous-active.json", previous_active, 0o600, uid=0, gid=0
            )
            _write_atomic(
                rollback / "previous-relational.json",
                previous_record,
                0o600,
                uid=0,
                gid=0,
            )
            preimage = True
            phase("prepared")
            connection = _connection(
                database,
                ticket,
                source.application_extension.storage.relational,
                write=False,
            )
            try:
                connection.execute("BEGIN")
                _RelationalReceiptStore(
                    database_lineage=ticket["source_database_lineage"],
                    schema_revision=ticket["source_schema_revision"],
                    secret=secret,
                )._validate(connection)
                validate_upgrade_history(
                    connection,
                    schema_revision=ticket["source_schema_revision"],
                    secret=secret,
                )
                pinned = receipt_metadata_digest(connection)
            finally:
                connection.close()
            _auxiliary(database, definition.storage.relational)
            _stage_wheel(instance, target, blob, definition, service_gid, ticket)
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core upgrade begin unavailable")
            mutated = True
            phase("migrating_schema")
            run_prepared_upgrade_migrations(
                instance,
                ticket,
                definition,
                receipt_metadata_sha256=pinned,
                service_uid=service_uid,
                service_gid=service_gid,
            )
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core upgrade publication unavailable")
            if _key(key_path) != secret:
                raise ValueError("Upgrade key changed during migration")
            connection = _connection(
                database, ticket, definition.storage.relational, write=True
            )
            try:
                connection.execute("BEGIN IMMEDIATE")
                if receipt_metadata_digest(connection) != pinned:
                    raise ValueError("Upgrade altered historical receipt metadata")
                upgrade_receipt_lineage(
                    connection,
                    source_lineage=ticket["source_database_lineage"],
                    source_schema=ticket["source_schema_revision"],
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
                raise ValueError("Core upgrade publication unavailable")
            if _key(key_path) != secret:
                raise ValueError("Upgrade key changed before publication")
            _live(ticket)
            _stage_wheel(instance, target, blob, definition, service_gid, ticket)
            metadata = _metadata(target, configuration, instance, root)
            record = _PreparedLifecycle.model_validate(
                upgraded_lifecycle(ticket, secret)
            ).model_dump(mode="json")
            phase("publishing")
            _write_atomic(
                instance / "active.json",
                canonical(metadata),
                0o640,
                uid=0,
                gid=service_gid,
            )
            _write_atomic(
                instance / "relational.json",
                canonical(record),
                0o640,
                uid=0,
                gid=service_gid,
            )
            if (instance / "active.json").read_bytes() != canonical(metadata) or (
                instance / "relational.json"
            ).read_bytes() != canonical(record):
                raise ValueError("Upgrade publication verification failed")
            connection = _connection(
                database, ticket, definition.storage.relational, write=False
            )
            try:
                connection.execute("BEGIN")
                _RelationalReceiptStore(
                    database_lineage=ticket["database_lineage"],
                    schema_revision=ticket["schema_revision"],
                    secret=secret,
                )._validate(connection)
                validate_upgrade_history(
                    connection, schema_revision=ticket["schema_revision"], secret=secret
                )
            finally:
                connection.close()
            _set_owner(database, service_uid, service_gid)
            for suffix in ("-wal", "-shm", "-journal"):
                path = database.with_name(database.name + suffix)
                if os.path.lexists(path):
                    _regular(path)
                    _set_owner(path, service_uid, service_gid)
            if _key(key_path) != secret:
                raise ValueError("Upgrade key changed before completion")
            _auxiliary(database, definition.storage.relational)
            _live(ticket)
            result = _RelationalUpgradeResult.model_validate(
                sign_metadata(
                    secret,
                    "database_upgrade_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "lifecycle_sha256": hashlib.sha256(
                            canonical(record)
                        ).hexdigest(),
                        "outcome": "upgraded_not_started",
                    },
                )
            ).model_dump(mode="json")
            phase("completion_unconfirmed")
            finishing = True
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "upgraded_not_started"
            }:
                raise ValueError("Core upgrade completion unconfirmed")
            phase("upgraded_not_started")
            archived = instance / (".upgrade-evidence-" + ticket["preparation_id"])
            if os.path.lexists(archived):
                raise ValueError("Upgrade evidence archive already exists")
            rollback.rename(archived)
            _sync_directory(instance)
            return result
        except Exception as error:
            if (
                preimage
                and mutated
                and not finishing
                and not isinstance(error, MigrationWorkerUnconfirmed)
            ):
                try:
                    _stop_for_data(selected, instance.name)
                    if _key(key_path) != secret:
                        raise ValueError("Upgrade key drift requires explicit recovery")
                    phase("restoring")
                    validate_database_restore(
                        database, rollback / "state.sqlite3", True
                    )
                    restore_private_files(data, rollback, service_uid, service_gid)
                    restore_database(
                        database,
                        rollback / "state.sqlite3",
                        True,
                        service_uid,
                        service_gid,
                    )
                    _write_atomic(
                        instance / "active.json",
                        previous_active,
                        0o640,
                        uid=0,
                        gid=service_gid,
                    )
                    _write_atomic(
                        instance / "relational.json",
                        previous_record,
                        0o640,
                        uid=0,
                        gid=service_gid,
                    )
                    from three_mm_runtime.application_relational_upgrade_rollback import (
                        record_completed_rollback,
                    )

                    record_completed_rollback(
                        instance,
                        rollback,
                        ticket,
                        secret,
                        database_limit=source.application_extension.storage.relational.max_database_bytes,
                    )
                    phase("restored_not_started")
                except Exception as failure:
                    raise RelationalUpgradeError(
                        "Upgrade rollback unconfirmed; evidence retained"
                    ) from failure
            raise RelationalUpgradeError(
                "Upgrade incomplete; evidence retained, explicit review required"
            ) from error
