"""Durable cleanup catalog migration preserves history and never infers grants."""
import hashlib
import subprocess
from pathlib import Path
import pytest
from sqlalchemy import create_engine,inspect,text
from backend.db.module import ApplicationRetainedData
from backend.tests.test_migration_history import _alembic

PREVIOUS='2c078e3546f7'
RETAINED='3e189f465708'


def previous(tmp_path):
    url='sqlite:///'+(tmp_path/'retained-migration.db').as_posix()
    _alembic(url,'upgrade',PREVIOUS)
    engine=create_engine(url)
    assert 'application_retained_data' not in inspect(engine).get_table_names()
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,username,role) VALUES(1,'migration-admin','admin')"))
    return url,engine


def audit(db,module,action):
    db.execute(text('INSERT INTO audit_logs(user_id,action,entity_type,entity_name,changes) VALUES(1,:a,:t,:m,:c)'),
        {'a':action,'t':'application_extension','m':module,'c':'{}'})


def test_history_backfill_is_generic_latest_outcome_and_preserves_other_rows(tmp_path):
    url,engine=previous(tmp_path)
    uninstall='APPLICATION_EXTENSION_UNINSTALLED';erase='APPLICATION_EXTENSION_DATA_ERASED'
    with engine.begin() as db:
        audit(db,'org.example.keep',uninstall)
        audit(db,'org.example.erased',uninstall);audit(db,'org.example.erased',erase)
        audit(db,'org.example.again',erase);audit(db,'org.example.again',uninstall)
        audit(db,'../unsafe',uninstall)
        audit(db,'org.example.installed',uninstall)
        db.execute(text("INSERT INTO module_packages(id,module_id,version,manifest,sha256,size_bytes,file_path,registrations) VALUES(1,'org.example.installed','1.0.0','{}',:sha,0,'old.zip','[]')"),{'sha':'b'*64})
        db.execute(text("INSERT INTO application_extension_installations(module_id,module_package_id,instance_id,configuration,authority_incarnation,authority_epoch,authority_mode,status,enabled,socket_path) VALUES('org.example.installed',1,:instance,'{}',:inc,:epoch,'compatibility','active',1,'pending')"),{'instance':'c'*24,'inc':'d'*32,'epoch':'e'*32})
        history=db.execute(text('SELECT id,action,entity_name,changes FROM audit_logs ORDER BY id')).all()
    # Exercise this migration's backfill/downgrade guard directly. Later stable
    # user subjects deliberately forbid populated downgrades of their own.
    # The clean/precreated tests below still check the complete head schema.
    engine.dispose();_alembic(url,'upgrade',RETAINED)
    engine=create_engine(url)
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))==RETAINED
        rows=db.execute(text('SELECT module_id,instance_id,name FROM application_retained_data ORDER BY module_id')).all()
        assert rows==[(module,hashlib.sha256(module.encode()).hexdigest()[:24],module) for module in ['org.example.again','org.example.keep']]
        assert db.execute(text('SELECT id,action,entity_name,changes FROM audit_logs ORDER BY id')).all()==history
        assert db.scalar(text('SELECT COUNT(*) FROM application_extension_installations'))==1
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):_alembic(url,'downgrade',PREVIOUS)
    engine=create_engine(url)
    with engine.begin() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM application_retained_data'))==2
        db.execute(text('DELETE FROM application_retained_data'))  # Disposable SQL-only fixture, no application files.
    engine.dispose();_alembic(url,'downgrade',PREVIOUS)
    engine=create_engine(url);assert 'application_retained_data' not in inspect(engine).get_table_names();engine.dispose()


def test_clean_upgrade_model_registration_and_reversible_empty_catalog(tmp_path):
    url='sqlite:///'+(tmp_path/'clean.db').as_posix();_alembic(url,'upgrade','head');_alembic(url,'check')
    engine=create_engine(url)
    assert 'application_retained_data' in ApplicationRetainedData.metadata.tables
    assert set(c['name'] for c in inspect(engine).get_columns('application_retained_data'))=={'module_id','instance_id','name'}
    engine.dispose();_alembic(url,'downgrade',PREVIOUS)


def test_complete_precreated_model_is_preserved_and_partial_schema_refused(tmp_path):
    url,engine=previous(tmp_path);ApplicationRetainedData.__table__.create(engine)
    with engine.begin() as db:db.execute(ApplicationRetainedData.__table__.insert().values(module_id='org.example.recorded',instance_id='a'*24,name='Recorded'))
    engine.dispose();_alembic(url,'upgrade','head');_alembic(url,'check')
    engine=create_engine(url)
    with engine.connect() as db:assert db.execute(text('SELECT module_id,instance_id,name FROM application_retained_data')).all()==[('org.example.recorded','a'*24,'Recorded')]
    engine.dispose()
    other=tmp_path/'partial';other.mkdir();partial,engine=previous(other)
    with engine.begin() as db:db.execute(text('CREATE TABLE application_retained_data(module_id TEXT PRIMARY KEY,instance_id TEXT NOT NULL)'))
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):_alembic(partial,'upgrade','head')
