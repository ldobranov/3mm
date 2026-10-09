"""Inactive metadata foundation: ownership, CAS, rollback and real connections."""

from dataclasses import replace
from datetime import UTC, datetime
import threading

import backend.database  # noqa: F401 - complete ORM metadata
import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard, MAX_AUTHORITY_REVISION
from backend.db.base import Base
from backend.db.device import Device, DevicePlatformState
from backend.db.module import (
    ApplicationConnectorBinding,
    ApplicationExtensionInstallation,
    ModulePackage,
)
from backend.services.authority_metadata import (
    AuthorityMetadataError,
    authority_transaction,
    read_application_authority,
    read_authority_guard,
    read_connector_authority,
    read_device_control,
)


@pytest.fixture
def metadata_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'authority.db').as_posix()}",
        connect_args={"timeout": 3},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(
        engine,
        tables=[
            Base.metadata.tables[name]
            for name in (
                "core_authority_guard",
                "module_packages",
                "devices",
                "application_extension_installations",
                "application_secret_references",
                "application_connector_bindings",
                "device_platform_states",
            )
        ],
    )
    with Session(engine) as db, db.begin():
        db.add(CoreAuthorityGuard(singleton_id=1))
        package = ModulePackage(
            id=1,
            module_id="org.example.authority",
            version="1.0.0",
            manifest={},
            sha256="a" * 64,
            size_bytes=1,
            file_path="unused",
        )
        db.add(package)
        db.flush()
        for index in (1, 2):
            db.add(
                ApplicationExtensionInstallation(
                    id=index,
                    module_id=f"org.example.app{index}",
                    module_package_id=1,
                    instance_id=str(index) * 24,
                    active_version="1.0.0",
                    status="active",
                    enabled=True,
                    socket_path="unused",
                    configuration={"private": "do-not-disclose"},
                )
            )
            db.add(
                Device(
                    id=index,
                    device_id="dev_" + str(index) * 32,
                    role="node",
                    protocol_version="1.0",
                    approved_at=datetime.now(UTC),
                )
            )
        db.flush()
        db.add(
            ApplicationConnectorBinding(
                id=1,
                application_installation_id=1,
                connector_id="api",
                destination_origin="https://example.test",
            )
        )
        db.add(DevicePlatformState(device_id=1, revision=7))
    yield engine
    engine.dispose()


def snapshots(engine):
    with Session(engine) as db:
        return (
            read_authority_guard(db),
            read_application_authority(db, 1),
            read_connector_authority(db, installation_id=1, binding_id=1),
            read_device_control(db, 1),
        )


def test_persistent_generations_and_compatibility_survive_reopen(metadata_engine):
    before = snapshots(metadata_engine)
    assert snapshots(metadata_engine) == before
    assert before[1].mode == "compatibility"
    assert (
        len(
            {
                before[0].generation,
                before[1].incarnation,
                before[1].epoch,
                before[2].revision,
                before[3].generation,
            }
        )
        == 5
    )
    assert "do-not-disclose" not in repr(before)


def test_advance_is_atomic_and_does_not_change_runtime_or_lifecycle_revision(
    metadata_engine,
):
    guard, app, binding, device = snapshots(metadata_engine)
    with Session(metadata_engine) as db:
        with authority_transaction(db, expected_guard=guard) as mutation:
            changed_binding = mutation.advance_connector_revision(binding)
            changed_device = mutation.advance_device_control(device)
        with pytest.raises(AuthorityMetadataError):
            mutation.advance_application_epoch(changed_binding.application)
        row = db.get(ApplicationExtensionInstallation, 1)
        assert (row.status, row.enabled, row.module_package_id, row.configuration) == (
            "active",
            True,
            1,
            {"private": "do-not-disclose"},
        )
        assert db.get(DevicePlatformState, 1).revision == 7
    after = snapshots(metadata_engine)
    assert after[0] == replace(guard, revision=guard.revision + 2)
    assert after[1] == changed_binding.application
    assert after[1].incarnation == app.incarnation and after[1].epoch != app.epoch
    assert after[2] == changed_binding and changed_binding.revision != binding.revision
    assert after[3] == changed_device and changed_device.generation != device.generation


def test_failed_and_caught_cas_roll_back_all_metadata(metadata_engine):
    before = snapshots(metadata_engine)
    with Session(metadata_engine) as db:
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as mutation:
                mutation.advance_device_control(before[3])
                # Application epoch changes first; stale binding must roll it back.
                with pytest.raises(AuthorityMetadataError):
                    mutation.advance_connector_revision(
                        replace(before[2], revision="0" * 32)
                    )
    assert snapshots(metadata_engine) == before


def test_caller_failure_rolls_back_everything(metadata_engine):
    before = snapshots(metadata_engine)
    with Session(metadata_engine) as db:
        with pytest.raises(RuntimeError, match="abort"):
            with authority_transaction(db) as mutation:
                db.get(ApplicationConnectorBinding, 1).destination_origin = (
                    "https://changed.test"
                )
                mutation.advance_connector_revision(before[2])
                raise RuntimeError("abort")
    assert snapshots(metadata_engine) == before
    with Session(metadata_engine) as db:
        assert (
            db.get(ApplicationConnectorBinding, 1).destination_origin
            == "https://example.test"
        )


def test_stale_and_foreign_application_or_connector_cannot_advance(metadata_engine):
    before = snapshots(metadata_engine)
    bad_apps = [
        replace(before[1], incarnation="0" * 32),
        replace(before[1], module_id="org.example.foreign"),
        replace(before[1], mode="review_required"),
    ]
    with Session(metadata_engine) as db:
        for app in bad_apps:
            with pytest.raises(AuthorityMetadataError):
                with authority_transaction(db) as mutation:
                    mutation.advance_application_epoch(app)
        foreign = read_application_authority(db, 2)
        db.rollback()
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as mutation:
                mutation.advance_connector_revision(
                    replace(before[2], application=foreign)
                )
    assert snapshots(metadata_engine) == before


def test_stale_resource_and_guard_cannot_be_replayed(metadata_engine):
    guard, app, _, _ = snapshots(metadata_engine)
    with Session(metadata_engine) as db:
        with authority_transaction(db, expected_guard=guard) as mutation:
            current = mutation.advance_application_epoch(app)
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db, expected_guard=guard):
                pytest.fail("stale guard admitted")
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as mutation:
                mutation.advance_application_epoch(app)
        with authority_transaction(db) as mutation:
            later = mutation.advance_application_epoch(current)
    assert len({app.epoch, current.epoch, later.epoch}) == 3


def test_noop_scope_does_not_advance_guard(metadata_engine):
    before = snapshots(metadata_engine)
    with Session(metadata_engine) as db, authority_transaction(db):
        assert read_application_authority(db, 1) == before[1]
    assert snapshots(metadata_engine) == before


def test_readers_bypass_stale_identity_map_and_never_autoflush(metadata_engine):
    with Session(metadata_engine, expire_on_commit=False) as db:
        cached = db.get(ApplicationExtensionInstallation, 1)
        old = read_application_authority(db, 1)
        db.commit()
        with (
            Session(metadata_engine) as writer,
            authority_transaction(writer) as mutation,
        ):
            current = mutation.advance_application_epoch(old)
        assert cached.authority_epoch == old.epoch
        cached.configuration = {"private": "pending-only"}
        db.add(ApplicationExtensionInstallation(module_id="org.example.pending"))
        statements = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(metadata_engine, "before_cursor_execute", capture)
        try:
            assert read_application_authority(db, 1) == current
            read_connector_authority(db, installation_id=1, binding_id=1)
            read_device_control(db, 1)
            read_authority_guard(db)
        finally:
            event.remove(metadata_engine, "before_cursor_execute", capture)
        assert statements and all(
            sql.lstrip().startswith("SELECT") for sql in statements
        )
        assert all(
            "configuration" not in sql and "encrypted_value" not in sql
            for sql in statements
        )
        db.rollback()


@pytest.mark.parametrize("bad_id", [0, -1, True, "1", 999])
def test_missing_or_invalid_owner_never_initializes_state(metadata_engine, bad_id):
    with Session(metadata_engine) as db:
        with pytest.raises(AuthorityMetadataError):
            read_application_authority(db, bad_id)
        with pytest.raises(AuthorityMetadataError):
            read_device_control(db, bad_id)
    with Session(metadata_engine) as db:
        with pytest.raises(AuthorityMetadataError):
            read_connector_authority(db, installation_id=2, binding_id=1)
        with pytest.raises(AuthorityMetadataError):
            read_device_control(db, 2)  # No platform row: never invent “bound”.
        assert db.get(DevicePlatformState, 2) is None


def test_transaction_requires_clean_first_write_and_existing_guard(metadata_engine):
    with Session(metadata_engine) as db:
        read_authority_guard(db)
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db):
                pytest.fail("nested transaction admitted")
        db.rollback()
        db.add(CoreAuthorityGuard(singleton_id=2))
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db):
                pytest.fail("pending write admitted")
        db.rollback()
        db.execute(CoreAuthorityGuard.__table__.delete())
        db.commit()
        with pytest.raises(AuthorityMetadataError):
            read_authority_guard(db)
        db.rollback()
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db):
                pytest.fail("missing guard initialized")


def test_revision_overflow_is_not_wrapped(metadata_engine):
    before = snapshots(metadata_engine)
    with Session(metadata_engine) as db, db.begin():
        db.execute(update(CoreAuthorityGuard).values(revision=MAX_AUTHORITY_REVISION))
    with Session(metadata_engine) as db:
        with pytest.raises(AuthorityMetadataError):
            with authority_transaction(db) as mutation:
                mutation.advance_application_epoch(before[1])
    assert snapshots(metadata_engine)[1:] == before[1:]


def test_uninstall_reinstall_same_pk_and_runtime_locator_gets_new_incarnation(
    metadata_engine,
):
    original = snapshots(metadata_engine)[1]
    with Session(metadata_engine) as db, db.begin():
        db.delete(db.get(ApplicationExtensionInstallation, 1))
        db.flush()
        db.add(
            ApplicationExtensionInstallation(
                id=1,
                module_id=original.module_id,
                module_package_id=1,
                instance_id="1" * 24,
                socket_path="unused",
            )
        )
    assert snapshots_app(metadata_engine).incarnation != original.incarnation


def snapshots_app(engine):
    with Session(engine) as db:
        return read_application_authority(db, 1)


@pytest.mark.parametrize("roll_back_first", [False, True])
def test_guard_serializes_real_connections_and_rechecks_after_wait(
    metadata_engine, roll_back_first
):
    guard, app, _, _ = snapshots(metadata_engine)
    attempted, done = threading.Event(), threading.Event()
    results = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if (
            threading.current_thread().name == "authority-writer"
            and statement.startswith("UPDATE core_authority_guard")
        ):
            attempted.set()

    def writer():
        try:
            with (
                Session(metadata_engine) as db,
                authority_transaction(db, expected_guard=guard) as mutation,
            ):
                mutation.advance_application_epoch(app)
            results.append("committed")
        except AuthorityMetadataError:
            results.append("stale")
        except BaseException as exc:
            results.append(exc)
        finally:
            done.set()

    event.listen(metadata_engine, "before_cursor_execute", capture)
    thread = threading.Thread(target=writer, name="authority-writer")
    try:
        with Session(metadata_engine) as first:
            try:
                with authority_transaction(first) as mutation:
                    mutation.advance_application_epoch(app)
                    thread.start()
                    assert attempted.wait(2)
                    assert not done.wait(0.05)
                    if roll_back_first:
                        raise RuntimeError("rollback first")
            except RuntimeError:
                if not roll_back_first:
                    raise
        assert done.wait(4)
        thread.join(1)
    finally:
        thread.join(4) if thread.ident is not None else None
        event.remove(metadata_engine, "before_cursor_execute", capture)
    assert results == ["committed" if roll_back_first else "stale"]
    assert snapshots(metadata_engine)[0].revision == guard.revision + 1


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()])
def test_guard_lock_statement_compiles_for_supported_dialects(dialect):
    statement = (
        update(CoreAuthorityGuard)
        .where(CoreAuthorityGuard.singleton_id == 1)
        .values(revision=CoreAuthorityGuard.revision)
    )
    sql = str(statement.compile(dialect=dialect))
    assert (
        "UPDATE core_authority_guard SET revision=core_authority_guard.revision" in sql
    )
    assert "WHERE core_authority_guard.singleton_id =" in sql
