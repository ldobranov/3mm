from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
import shutil

import backend.database  # noqa: F401 - register existing ORM relationship targets
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, select, func
from sqlalchemy.orm import Session

from backend.db.installation_identity import CoreInstallationIdentity
from backend.services import installation_identity as service
from three_mm_protocol.installation_identity import verify_installation_proof
from three_mm_protocol.tests.test_installation_identity import NOW, proof_request


@pytest.fixture
def identity_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    engine = create_engine(f"sqlite:///{(tmp_path / 'core.db').as_posix()}")
    CoreInstallationIdentity.__table__.create(engine)
    yield engine
    engine.dispose()


def test_restart_update_and_independent_installations(
    identity_engine, tmp_path, monkeypatch
):
    with Session(identity_engine) as db:
        first = service.installation_identity(db)
    monkeypatch.setattr(service, "core_version", lambda: "0.3.0-beta.31")
    with Session(identity_engine) as db:
        after_restart_update = service.installation_identity(db)
        proof = service.prove_installation_identity(db, proof_request(), now=NOW)
        row = db.get(CoreInstallationIdentity, 1)
        assert "encrypted_private_key" not in first.model_dump()
        assert row.encrypted_private_key.startswith("gAAAA")
    assert after_restart_update.identity == first.identity
    assert after_restart_update.core_version == "0.3.0-beta.31"
    assert (
        verify_installation_proof(
            proof,
            expected_identity=first.identity,
            expected_request=proof_request(),
            now=NOW,
        )
        == first.identity
    )

    second_engine = create_engine(
        f"sqlite:///{(tmp_path / 'independent.db').as_posix()}"
    )
    try:
        CoreInstallationIdentity.__table__.create(second_engine)
        with Session(second_engine) as db:
            second = service.installation_identity(db)
        assert second.identity.installation_id != first.identity.installation_id
        assert second.identity.key_id != first.identity.key_id
    finally:
        second_engine.dispose()


def test_concurrent_creators_converge_without_overwriting(identity_engine):
    def read(_):
        with Session(identity_engine) as db:
            return service.installation_identity(db).identity

    with ThreadPoolExecutor(max_workers=4) as workers:
        identities = list(workers.map(read, range(8)))
    assert all(identity == identities[0] for identity in identities)
    with Session(identity_engine) as db:
        assert (
            db.scalar(select(func.count()).select_from(CoreInstallationIdentity)) == 1
        )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_master",
        "wrong_master",
        "ciphertext",
        "public_binding",
        "private_binding",
    ],
)
def test_corrupt_or_unavailable_keys_fail_closed_without_rotation(
    identity_engine, monkeypatch, failure
):
    with Session(identity_engine) as db:
        original = service.installation_identity(db).identity
        row = db.get(CoreInstallationIdentity, 1)
        if failure == "missing_master":
            monkeypatch.delenv("AI_SETTINGS_MASTER_KEY")
        elif failure == "wrong_master":
            monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
        elif failure == "ciphertext":
            row.encrypted_private_key = "corrupt"
        elif failure == "public_binding":
            row.key_id = "0" * 64
        else:
            row.encrypted_private_key = service._cipher().encrypt(b"z" * 32).decode()
        db.commit()
        with pytest.raises(service.InstallationIdentityError):
            service.installation_identity(db)
        db.expire_all()
        assert (
            db.get(CoreInstallationIdentity, 1).installation_id
            == original.installation_id
        )


def test_invalid_expired_proof_never_creates_an_identity(identity_engine):
    with Session(identity_engine) as db:
        with pytest.raises(ValueError, match="expired"):
            service.prove_installation_identity(
                db, proof_request(), now=NOW + timedelta(seconds=120)
            )
        assert db.get(CoreInstallationIdentity, 1) is None


def test_database_clone_is_the_same_identity_not_collision_detection(
    identity_engine, tmp_path
):
    with Session(identity_engine) as db:
        original = service.installation_identity(db).identity
    identity_engine.dispose()
    clone = tmp_path / "clone.db"
    shutil.copyfile(tmp_path / "core.db", clone)
    engine = create_engine(f"sqlite:///{clone.as_posix()}")
    try:
        with Session(engine) as db:
            assert service.installation_identity(db).identity == original
    finally:
        engine.dispose()


def test_identity_migration_upgrade_downgrade_and_existing_state(tmp_path):
    migration = import_module(
        "backend.alembic.versions.4159a0b1c2d3_core_installation_identity"
    )
    engine = create_engine(f"sqlite:///{(tmp_path / 'migrate.db').as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE existing_state (value TEXT)")
            connection.exec_driver_sql(
                "INSERT INTO existing_state VALUES ('preserved')"
            )
            operations = Operations(MigrationContext.configure(connection))
            previous = migration.op
            migration.op = operations
            try:
                migration.upgrade()
                assert (
                    "core_installation_identity"
                    in inspect(connection).get_table_names()
                )
                assert (
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM core_installation_identity"
                    ).scalar_one()
                    == 0
                )
                assert (
                    connection.exec_driver_sql(
                        "SELECT value FROM existing_state"
                    ).scalar_one()
                    == "preserved"
                )
                migration.downgrade()
                assert (
                    "core_installation_identity"
                    not in inspect(connection).get_table_names()
                )
            finally:
                migration.op = previous
    finally:
        engine.dispose()
