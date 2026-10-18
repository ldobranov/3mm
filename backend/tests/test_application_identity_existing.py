"""A public-only existing identity read is not key initialization or signing."""

import base64
import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.services import installation_identity as service


PUBLIC_KEY = base64.b64encode(b"p" * 32).decode("ascii")
PUBLIC_IDENTITY = {
    "installation_id": "inst_" + "1" * 32,
    "identity_version": 1,
    "key_generation": 1,
    "key_id": hashlib.sha256(b"p" * 32).hexdigest(),
    "public_key": PUBLIC_KEY,
    "created_at": "2026-10-16 09:10:11.123456",
}


class PendingBase(DeclarativeBase):
    pass


class PendingRow(PendingBase):
    __tablename__ = "untouched"
    value: Mapped[str] = mapped_column(primary_key=True)


@pytest.fixture
def public_database():
    engine = create_engine("sqlite://")
    # Deliberately NO private column: ORM entity/deferred/lazy key reads fail.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE core_installation_identity ("
            "singleton_id INTEGER PRIMARY KEY, installation_id TEXT, "
            "identity_version INTEGER, key_generation INTEGER, key_id TEXT, "
            "public_key TEXT, created_at DATETIME)"
        )
        connection.exec_driver_sql("CREATE TABLE untouched(value TEXT)")
    statements = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    try:
        yield engine, statements
    finally:
        engine.dispose()


def seed(engine, **changes):
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core_installation_identity "
                "(singleton_id, installation_id, identity_version, key_generation, "
                "key_id, public_key, created_at) VALUES "
                "(1, :installation_id, :identity_version, :key_generation, "
                ":key_id, :public_key, :created_at)"
            ),
            {**PUBLIC_IDENTITY, **changes},
        )


def forbid_key_and_transaction_work(monkeypatch, db):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Public identity read touched private keys, writes or transaction control")

    for name in ("_cipher", "_load_or_create", "_decode_identity"):
        monkeypatch.setattr(service, name, forbidden)
    monkeypatch.setattr(service.Ed25519PrivateKey, "generate", forbidden)
    for name in ("get", "add", "flush", "commit", "rollback"):
        monkeypatch.setattr(db, name, forbidden)


def test_existing_public_identity_reads_only_explicit_public_columns_without_keys(
    public_database, monkeypatch
):
    engine, statements = public_database
    seed(engine)
    monkeypatch.delenv("AI_SETTINGS_MASTER_KEY", raising=False)
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            forbid_key_and_transaction_work(patch, db)
            statements.clear()
            result = service.read_existing_installation_identity(db)
            assert result.installation_id == PUBLIC_IDENTITY["installation_id"]
            assert result.public_key == PUBLIC_KEY
            assert result.created_at == datetime(2026, 10, 16, 9, 10, 11, 123456, UTC)
            assert result.algorithm == "ed25519"
            assert set(result.model_dump()) == {
                "identity_version", "installation_id", "algorithm", "key_id",
                "public_key", "key_generation", "created_at",
            }
            assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT ")
            assert "encrypted_private_key" not in statements[0]
            assert "*" not in statements[0]


def test_missing_existing_identity_is_not_initialized_or_committed(
    public_database, monkeypatch
):
    engine, statements = public_database
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            forbid_key_and_transaction_work(patch, db)
            statements.clear()
            with pytest.raises(service.InstallationIdentityError, match="public identity is unavailable"):
                service.read_existing_installation_identity(db)
            assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT ")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM core_installation_identity").scalar_one() == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"installation_id": "foreign"},
        {"identity_version": 2},
        {"key_generation": 2},
        {"public_key": "invalid"},
        {"public_key": base64.b64encode(b"q" * 32).decode("ascii")},
        {"key_id": "0" * 64},
        {"created_at": None},
        {"created_at": "invalid timestamp"},
    ],
)
def test_corrupt_public_binding_is_refused_without_repair_or_private_key_access(
    public_database, monkeypatch, changes
):
    engine, statements = public_database
    seed(engine, **changes)
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            forbid_key_and_transaction_work(patch, db)
            statements.clear()
            with pytest.raises(service.InstallationIdentityError, match="public identity is unavailable"):
                service.read_existing_installation_identity(db)
            assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT ")


def test_existing_reader_never_flushes_or_commits_the_callers_pending_work(
    public_database, monkeypatch
):
    engine, statements = public_database
    seed(engine)
    with Session(engine) as db:
        pending = PendingRow(value="not flushed or committed")
        db.add(pending)
        with monkeypatch.context() as patch:
            forbid_key_and_transaction_work(patch, db)
            statements.clear()
            result = service.read_existing_installation_identity(db)
            assert result.installation_id == PUBLIC_IDENTITY["installation_id"]
            assert pending in db.new and len(statements) == 1
        db.expunge(pending)


def test_existing_reader_normalizes_aware_timestamps_without_changing_stored_data(
    public_database,
):
    engine, _ = public_database
    timestamp = "2026-10-16 12:10:11.123456+03:00"
    seed(engine, created_at=timestamp)
    with Session(engine) as db:
        result = service.read_existing_installation_identity(db)
        assert result.created_at == datetime(2026, 10, 16, 9, 10, 11, 123456, UTC)
        assert db.execute(text("SELECT created_at FROM core_installation_identity")).scalar_one() == timestamp
