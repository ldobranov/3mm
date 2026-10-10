"""Private root preparation of fixed SDK metadata in an EXISTING own schema.

The metadata-only entrypoint never imports package code. Separate explicit
migration authority runs exact package migrations ONLY in a non-root child.
No automatic start or public helper action. Current LOCAL human authority is
checked by Core between SQL/process work. Existing locks/preimages fence publication.
Cooperative reviewed-native boundary, not hostile native-code isolation.
"""

import hashlib
import io
import os
import shutil
import sqlite3
import stat
import zipfile
from pathlib import Path

from backend.services.application_configuration import resolve_application_configuration
from backend.services.module_packages import MAX_PACKAGE_BYTES, validate_module_package
from three_mm_application_sdk.relational_receipts import (
    _prepare_receipt_metadata,
    _RelationalReceiptStore,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalPreparationResult,
    _RelationalPreparationTicket,
    canonical,
    migration_worker_profile_digest,
    prepared_lifecycle,
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
    run_business_migrations,
)
from three_mm_runtime.application_relational_session import (
    _clock,
    _decode,
    _PreparedLifecycle,
    _protected_directory,
    _regular,
)


class RelationalPreparationError(RuntimeError):
    pass


def _live(ticket):
    boot, now = _clock()
    if (
        boot != ticket["boot_id"]
        or not ticket["issued_at_ms"] <= now < ticket["deadline_ms"]
    ):
        raise ValueError("Relational preparation expired")
    return ticket["deadline_ms"] - now


def _key(path):
    if _regular(path, protected=True).st_size != 32:
        raise ValueError("Relational preparation key unavailable")
    return path.read_bytes()


def _schema(connection, revision, *, require_target=True):
    # Existing or partial metadata is recovery, never permission to relineage.
    if connection.execute(
        "SELECT name FROM sqlite_schema WHERE name IN "
        "('three_mm_relational_lineage', 'three_mm_relational_commits')"
    ).fetchone():
        raise ValueError("Existing receipt metadata requires recovery review")
    if not require_target:
        return
    row = connection.execute(
        "SELECT revision FROM three_mm_schema_migrations ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    if row is None or row[0] != revision:
        raise ValueError("Application business migration is required")


def _connection(database, ticket, declaration, *, write):
    remaining = _live(ticket)
    connection = sqlite3.connect(
        database.absolute().as_uri() + ("?mode=rw" if write else "?mode=ro"),
        uri=True,
        timeout=0,
        isolation_level=None,
    )
    try:
        connection.enable_load_extension(False)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(
            f"PRAGMA busy_timeout={min(declaration.max_busy_ms, remaining)}"
        )
        connection.set_progress_handler(
            lambda: int(_clock()[1] >= ticket["deadline_ms"]), 1000
        )
        if not write:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA synchronous=FULL")
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        maximum = declaration.max_database_bytes // page_size
        if connection.execute("PRAGMA page_count").fetchone()[0] > maximum:
            raise ValueError("Application database exceeds preparation profile")
        if (
            write
            and connection.execute(f"PRAGMA max_page_count={maximum}").fetchone()[0]
            != maximum
        ):
            raise ValueError("Application database budget unavailable")
        return connection
    except BaseException:
        connection.close()
        raise


def _auxiliary(database, declaration):
    total = 0
    for suffix in ("-wal", "-shm", "-journal"):
        path = database.with_name(database.name + suffix)
        if os.path.lexists(path):
            total += _regular(path).st_size
    if total > declaration.auxiliary_pause_bytes:
        raise ValueError("Preparation auxiliary storage is paused")


def prepare_existing_relational_database(
    package_path,
    ticket,
    **kwargs,
):
    """Metadata only: cannot accept a business-migration ticket or missing DB."""
    return _prepare_relational_database(package_path, ticket, migrate=False, **kwargs)


def prepare_migrated_relational_database(package_path, ticket, **kwargs):
    """Explicit initial schema creation/forward migrations in an owned namespace.

    Not prepared-DB upgrade, namespace/key creation, production dispatch or a
    public install action. Existing metadata-only ticket is ALWAYS refused.
    """
    return _prepare_relational_database(package_path, ticket, migrate=True, **kwargs)


def _stage_wheel(instance, validated, blob, definition, service_gid, ticket):
    release = instance / "releases" / validated.sha256
    if not os.path.lexists(release):
        release.mkdir(mode=0o750)
        _set_owner(release, 0, service_gid)
    _protected_directory(release)
    wheel = release / "service.whl"
    if not os.path.lexists(wheel):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            payload = archive.read(definition.service.artifact)
        _write_atomic(wheel, payload, 0o440)
        _set_owner(wheel, 0, service_gid)
    _regular(wheel, protected=True)
    with wheel.open("rb") as stream:
        if (
            hashlib.file_digest(stream, "sha256").hexdigest()
            != ticket["service_sha256"]
        ):
            raise ValueError("Prepared wheel changed")


def _prepare_relational_database(
    package_path,
    ticket,
    *,
    migrate,
    configuration,
    root,
    key_root,
    state_root,
    service_uid,
    service_gid,
    checkpoint,
    supervisor=None,
):
    """Initial preparation only; callers cannot supply paths via the ticket.

    ``checkpoint`` is the trusted Core coordinator, not an application callback.
    There is deliberately no permissive default, CLI or production dispatch.
    Failure retains evidence and never restarts; unconfirmed stop stays unknown.
    Once finish is attempted,
    a lost ACK MUST NOT roll back or replay a possibly recorded publication.
    """
    if (
        os.name != "posix"
        or os.geteuid() != 0
        or not callable(checkpoint)
        or type(service_uid) is not int
        or service_uid <= 0
        or type(service_gid) is not int
        or service_gid < 0
    ):
        raise RelationalPreparationError("Protected relational helper unavailable")
    if migrate and service_gid == 0:
        raise RelationalPreparationError("Migration service group must be non-root")
    model = (
        _RelationalMigrationPreparationTicket
        if migrate
        else _RelationalPreparationTicket
    )
    ticket = model.model_validate(ticket).model_dump(mode="json")
    purpose = "migration_preparation" if migrate else "preparation"
    root, key_root, state_root = map(Path, (root, key_root, state_root))
    package_path = Path(package_path)
    if _regular(package_path).st_size > MAX_PACKAGE_BYTES:
        raise RelationalPreparationError("Preparation package too large")
    blob = package_path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != ticket["package_sha256"]:
        raise RelationalPreparationError("Preparation artifact changed")
    validated = validate_module_package(blob)
    definition = validated.application_extension
    if definition is None or definition.storage.relational is None:
        raise RelationalPreparationError(
            "Relational preparation declaration unavailable"
        )
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
        raise RelationalPreparationError("Preparation identity changed")
    if migrate and ticket["worker_profile_sha256"] != migration_worker_profile_digest():
        raise RelationalPreparationError("Migration worker profile changed")
    instance = root / ticket["instance_id"]
    data = instance / "data"
    database = data / "state.sqlite3"
    key_path = key_root / (ticket["instance_id"] + ".key")
    active = instance / "active.json"
    record_path = instance / "relational.json"
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
                raise RelationalPreparationError(
                    "Application own namespace unavailable"
                )
        if not migrate or os.path.lexists(database):
            _regular(database)
        _require_no_pending_rollback(instance)
        if os.path.lexists(record_path):
            raise RelationalPreparationError(
                "Prepared lineage requires explicit recovery"
            )
        previous = None
        if os.path.lexists(active):
            if _regular(active, protected=True).st_size > 131072:
                raise RelationalPreparationError("Active metadata too large")
            previous = active.read_bytes()
            if (
                _decode(previous, limit=131072).get("storage", {}).get("relational")
                is not None
            ):
                raise RelationalPreparationError(
                    "Partial publication requires recovery"
                )
        secret = _key(key_path)
        verify_metadata(secret, purpose, ticket)
        _live(ticket)
        if checkpoint(ticket, "authorize") != {"state": "authorized_not_started"}:
            raise RelationalPreparationError(
                "Core preparation authorization unavailable"
            )
        rollback = instance / (".activation-" + ticket["preparation_id"] + ".rollback")
        rollback.mkdir(mode=0o700)
        evidence = {
            "schema_version": 1,
            "candidate_sha256": validated.sha256,
            "previous_present": previous is not None,
            "previous_was_enabled": False,
            "database_present": None,
            "operation": ticket["action"],
            "preparation_id": ticket["preparation_id"],
        }

        def phase(value):
            _write_atomic(
                rollback / "activation.json",
                canonical(dict(evidence, phase=value)),
                0o600,
            )

        phase("preparing")
        if previous is not None:
            _write_atomic(rollback / "previous-active.json", previous, 0o600)
        preimage = False
        mutated = False
        completion_started = False
        try:
            _stop_for_data(selected, ticket["instance_id"])
            existed = capture_database(database, rollback / "state.sqlite3")
            if not existed and not migrate:
                raise ValueError("Existing database disappeared")
            capture_private_files(data, rollback)
            evidence["database_present"] = existed
            preimage = True
            phase("prepared")
            if existed:
                connection = _connection(
                    database, ticket, definition.storage.relational, write=False
                )
                try:
                    connection.execute("BEGIN")
                    _schema(
                        connection,
                        ticket["schema_revision"],
                        require_target=not migrate,
                    )
                finally:
                    connection.close()
            _stage_wheel(instance, validated, blob, definition, service_gid, ticket)
            if checkpoint(ticket, "begin") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core preparation begin unavailable")
            phase("preparing_metadata")
            _auxiliary(database, definition.storage.relational)
            mutated = True  # Includes pragma/commit uncertainty, never replayed.
            if migrate:
                phase("migrating_schema")
                if existed:
                    _set_owner(database, service_uid, service_gid)
                    for suffix in ("-wal", "-shm", "-journal"):
                        path = database.with_name(database.name + suffix)
                        if os.path.lexists(path):
                            _regular(path)
                            _set_owner(path, service_uid, service_gid)
                run_business_migrations(
                    instance,
                    ticket,
                    definition,
                    database_present=existed,
                    service_uid=service_uid,
                    service_gid=service_gid,
                )
                # Recheck current human/native/grants after package code, with
                # all SQL connections and the migration process closed.
                if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                    raise ValueError("Core migration publication unavailable")
                if _key(key_path) != secret:
                    raise ValueError("Preparation transport key changed")
                phase("preparing_metadata")
            connection = _connection(
                database, ticket, definition.storage.relational, write=True
            )
            try:
                connection.execute("BEGIN IMMEDIATE")
                _schema(connection, ticket["schema_revision"])
                _prepare_receipt_metadata(
                    connection,
                    database_lineage=ticket["database_lineage"],
                    schema_revision=ticket["schema_revision"],
                    secret=secret,
                )
                _auxiliary(database, definition.storage.relational)
                _live(ticket)
                connection.commit()
            finally:
                connection.close()
            _auxiliary(database, definition.storage.relational)
            if checkpoint(ticket, "check") != {"state": "execution_unconfirmed"}:
                raise ValueError("Core preparation publication unavailable")
            if _key(key_path) != secret:
                raise ValueError("Preparation transport key changed")
            _live(ticket)
            _stage_wheel(instance, validated, blob, definition, service_gid, ticket)
            metadata = _application_metadata(
                validated, configuration, ticket["instance_id"], root
            )
            metadata["storage"]["relational"] = (
                definition.storage.relational.model_dump(mode="json")
            )
            record = _PreparedLifecycle.model_validate(
                prepared_lifecycle(ticket, secret)
            ).model_dump(mode="json")
            phase("publishing")
            _write_atomic(active, canonical(metadata), 0o640)
            _set_owner(active, 0, service_gid)
            _write_atomic(record_path, canonical(record), 0o640)
            _set_owner(record_path, 0, service_gid)
            for path, expected_payload in (
                (active, canonical(metadata)),
                (record_path, canonical(record)),
            ):
                if (
                    _regular(path, protected=True).st_size != len(expected_payload)
                    or path.read_bytes() != expected_payload
                ):
                    raise ValueError("Preparation publication verification failed")
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
            finally:
                connection.close()
            _set_owner(database, service_uid, service_gid)
            for suffix in ("-wal", "-shm", "-journal"):
                path = database.with_name(database.name + suffix)
                if os.path.lexists(path):
                    _regular(path)
                    _set_owner(path, service_uid, service_gid)
            if _key(key_path) != secret:
                raise ValueError("Preparation transport key changed")
            _live(ticket)
            result = _RelationalPreparationResult.model_validate(
                sign_metadata(
                    secret,
                    "preparation_result",
                    {
                        "version": 1,
                        "preparation_id": ticket["preparation_id"],
                        "lifecycle_sha256": hashlib.sha256(
                            canonical(record)
                        ).hexdigest(),
                        "outcome": "prepared_not_started",
                    },
                )
            ).model_dump(mode="json")
            phase("completion_unconfirmed")
            completion_started = True
            if checkpoint(ticket, "finish", receipt=result) != {
                "state": "prepared_not_started"
            }:
                raise ValueError("Core preparation completion unconfirmed")
            phase("prepared_not_started")
            shutil.rmtree(
                rollback
            )  # Only this exact helper-created, confirmed checkpoint.
            return result
        except Exception as exc:
            if (
                preimage
                and mutated
                and not completion_started
                and not isinstance(exc, MigrationWorkerUnconfirmed)
            ):
                try:
                    _stop_for_data(selected, ticket["instance_id"])
                    phase("restoring")
                    validate_database_restore(
                        database, rollback / "state.sqlite3", existed
                    )
                    restore_private_files(data, rollback, service_uid, service_gid)
                    restore_database(
                        database,
                        rollback / "state.sqlite3",
                        existed,
                        service_uid,
                        service_gid,
                    )
                    if previous is None:
                        active.unlink(missing_ok=True)
                    else:
                        _write_atomic(active, previous, 0o640)
                        _set_owner(active, 0, service_gid)
                    record_path.unlink(missing_ok=True)
                    phase("restored_not_started")
                except Exception as rollback_error:
                    raise RelationalPreparationError(
                        "Preparation rollback unconfirmed; recovery review required"
                    ) from rollback_error
            raise RelationalPreparationError(
                "Preparation incomplete; runtime state requires recovery review"
            ) from exc
