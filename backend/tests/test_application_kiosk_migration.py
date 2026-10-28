"""Additive ownership boundary; never adopt older unbound terminal secrets."""
import subprocess
import pytest
from sqlalchemy import create_engine,text
from backend.tests.test_migration_history import _alembic


def test_legacy_kiosk_rows_are_preserved_without_automatic_adoption(tmp_path):
    url=f"sqlite:///{tmp_path/'kiosks.db'}"
    _alembic(url,'upgrade','af85a6d71e75')
    engine=create_engine(url)
    with engine.begin() as db:
        # SQLite fixture insert retains historical rows without constructing a
        # current installation. The upgrade does not read/reissue credentials.
        db.execute(text("INSERT INTO application_kiosk_enrollments (id,application_installation_id,code_hash,label,expires_at) VALUES (3,7,'old-code-hash','Legacy','2099-01-01')"))
        db.execute(text("INSERT INTO application_kiosk_terminals (id,terminal_id,enrollment_id,application_installation_id,label,credential_hash,enabled) VALUES (4,:terminal,3,7,'Legacy','old-credential-hash',1)"),{'terminal':'a'*32})
    _alembic(url,'upgrade','head');_alembic(url,'check')
    with engine.connect() as db:
        assert db.execute(text('SELECT credential_hash,enabled,installation_incarnation FROM application_kiosk_terminals')).one()==('old-credential-hash',1,None)
        assert db.execute(text('SELECT code_hash,installation_incarnation FROM application_kiosk_enrollments')).one()==('old-code-hash',None)
    with pytest.raises(subprocess.CalledProcessError) as blocked:_alembic(url,'downgrade','af85a6d71e75')
    assert 'kiosk identities' in blocked.value.stderr
    with engine.connect() as db:assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='b096b7e82f86'
    engine.dispose()


def test_empty_kiosk_schema_round_trip(tmp_path):
    url=f"sqlite:///{tmp_path/'empty.db'}"
    _alembic(url,'upgrade','head');_alembic(url,'downgrade','af85a6d71e75')
    _alembic(url,'upgrade','head');_alembic(url,'check')
