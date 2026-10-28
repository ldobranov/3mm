import pytest
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "backend" / "alembic.ini"


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option('script_location', str(REPOSITORY_ROOT / 'backend/alembic'))
    return ScriptDirectory.from_config(config).get_current_head()


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_CONFIG),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_clean_database_migrates_to_head_and_back_to_base(tmp_path):
    database_path = tmp_path / "clean-migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "check")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"retired_pages","retired_extensions","retired_language_packs","language_extension_installations"} <= tables
    assert not {"pages","extensions","language_packs","setting_translations","extension_tables","extension_fields","table_translations","migration_history"} & tables
    assert "settings" in tables
    assert "devices" in tables
    product_tables = {"automation_proposals", "automation_revisions", "ai_jobs",
        "ai_usage_ledger", "extension_projects", "extension_project_files", "extension_project_builds"}
    assert not product_tables & tables
    assert {"retired_" + name for name in product_tables} <= tables
    assert {"retired_runtime_extension_definitions", "retired_runtime_entity_records"} <= tables
    assert not {"runtime_extension_definitions", "runtime_entity_records"} & tables
    assert "application_extension_installations" in tables
    assert {'application_command_epochs', 'application_command_requests'} <= tables
    installation_columns = {
        column["name"]
        for column in inspector.get_columns("application_extension_installations")
    }
    assert "configuration" in installation_columns
    assert "application_permission_grants" in tables
    assert {'group_roles', 'role_application_grants', 'module_package_retained_references'} <= tables
    assert not {'displays', 'widgets', 'role_dashboard_grants'} & tables
    assert {'retired_displays', 'retired_widgets', 'retired_role_dashboard_grants'} <= tables
    assert "application_kiosk_enrollments" in tables
    assert "application_kiosk_terminals" in tables
    assert "application_event_deliveries" in tables
    assert "application_event_cursors" in tables
    assert "application_secret_references" in tables
    assert "application_connector_bindings" in tables
    assert "application_connector_attempts" in tables
    assert "application_job_states" in tables
    assert {'lease_token', 'last_scheduled_at', 'last_duration_ms', 'last_lateness_ms'} <= {
        column['name'] for column in inspector.get_columns('application_job_states')}
    assert "application_sync_checkpoints" in tables
    build_columns = {column["name"] for column in inspector.get_columns("retired_extension_project_builds")}
    assert {"artifact_path", "package_kind", "installed_at"} <= build_columns
    engine.dispose()

    _alembic(database_url, "upgrade", "head")
    _alembic(database_url, "downgrade", "base")
    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()


def test_scoped_grants_upgrade_from_previous_release(tmp_path):
    url = f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    _alembic(url, 'upgrade', 'fc04b5c6d7e8')
    engine = create_engine(url)
    assert 'role_application_grants' not in inspect(engine).get_table_names()
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    _alembic(url, 'downgrade', 'fc04b5c6d7e8')
    engine = create_engine(url)
    assert 'role_application_grants' not in inspect(engine).get_table_names()
    engine.dispose()


def test_job_claim_upgrade_preserves_and_quarantines_legacy_inflight(tmp_path):
    url = f"sqlite:///{(tmp_path / 'job-upgrade.db').as_posix()}"
    _alembic(url, 'upgrade', '1e26d7e8f9a0')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO module_packages (id,module_id,version,manifest,sha256,size_bytes,file_path,registrations) VALUES (1,'org.example.jobs','1.0.0','{}',:sha,1,'unused','[]')"), {'sha': 'a'*64})
        connection.execute(text("INSERT INTO application_extension_installations (id,module_id,module_package_id,instance_id,status,enabled,socket_path,configuration) VALUES (1,'org.example.jobs',1,:instance,'active',1,'unused','{}')"), {'instance': 'a'*24})
        connection.execute(text("INSERT INTO application_job_states (application_installation_id,job_id,next_run_at,lease_until,last_outcome,run_count) VALUES (1,'sync','2026-09-15 10:00:00','2026-09-15 10:00:05','running',7)"))
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    with engine.connect() as connection:
        row = connection.execute(text('SELECT lease_token,last_outcome,last_error,run_count,next_run_at FROM application_job_states')).one()
        assert len(row[0]) == 32
        assert row[1:4] == ('unknown', 'legacy_inflight', 7)
        assert row[4].startswith('2026-09-15 10:00:00')
    engine.dispose()


def test_node_enrollment_upgrade_and_downgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'enrollment.db').as_posix()}"
    _alembic(url, 'upgrade', '2f37e8f9a0b1')
    engine = create_engine(url)
    assert next(c for c in inspect(engine).get_columns('device_pairing_requests')
                if c['name'] == 'created_by_user_id')['nullable'] is False
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    assert next(c for c in inspect(engine).get_columns('device_pairing_requests')
                if c['name'] == 'created_by_user_id')['nullable'] is True
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO device_pairing_requests (code_hash,requested_device_id,requested_metadata,expires_at) VALUES (:hash,:device,'{}','2030-01-01')"),
                           {'hash': 'e' * 64, 'device': 'dev_' + 'e' * 32})
    engine.dispose()
    _alembic(url, 'downgrade', '2f37e8f9a0b1')
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM device_pairing_requests')).scalar() == 0
    engine.dispose()


def test_event_claim_migration_preserves_queue_and_refuses_unresolved_downgrade(tmp_path):
    url=f"sqlite:///{(tmp_path/'event-claims.db').as_posix()}"
    _alembic(url,'upgrade','0ae56c1324d5')
    engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO module_packages (id,module_id,version,manifest,sha256,size_bytes,file_path,registrations) VALUES (1,'org.example.events','1.0.0','{}',:sha,1,'unused','[]')"),{'sha':'a'*64})
        db.execute(text("INSERT INTO application_extension_installations (id,module_id,module_package_id,instance_id,status,enabled,socket_path,configuration,authority_incarnation,authority_epoch) VALUES (1,'org.example.events',1,:instance,'active',1,'unused','{}',:instance32,:instance32)"),{'instance':'a'*24,'instance32':'a'*32})
        db.execute(text("INSERT INTO devices (id,device_id,role,protocol_version,approved_at) VALUES (1,:device,'node','1.0','2026-10-23')"),{'device':'dev_'+'a'*32})
        db.execute(text("INSERT INTO device_events (id,device_id,event_id,event_type,payload,occurred_at,producer_kind) VALUES (1,1,'evt_existing','device.changed.v1','{}','2026-10-23','device')"))
        db.execute(text("INSERT INTO application_event_deliveries (id,application_installation_id,subscription_id,device_event_id,status,attempts,authority_epoch) VALUES (1,1,'changes',1,'pending',3,:epoch)"),{'epoch':'b'*32})
        db.execute(text("INSERT INTO application_event_cursors (application_installation_id,subscription_id,acknowledged_count,dead_letter_count,dropped_dead_letter_count) VALUES (1,'changes',2,1,0)"))
    engine.dispose()
    _alembic(url,'upgrade','head');_alembic(url,'check')
    engine=create_engine(url)
    with engine.begin() as db:
        assert db.execute(text('SELECT status,attempts,authority_epoch,dispatch_id,dispatch_metadata FROM application_event_deliveries')).one()==('pending',3,'b'*32,None,None)
        assert db.execute(text('SELECT acknowledged_count,dead_letter_count FROM application_event_cursors')).one()==(2,1)
        db.execute(text("UPDATE application_event_deliveries SET status='delivering',dispatch_id=:token,dispatch_metadata='{}'"),{'token':'c'*32})
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError) as blocked:_alembic(url,'downgrade','0ae56c1324d5')
    assert 'Resolve in-flight' in blocked.value.stderr
    engine=create_engine(url)
    with engine.begin() as db:db.execute(text("UPDATE application_event_deliveries SET status='pending'"))
    engine.dispose();_alembic(url,'downgrade','0ae56c1324d5')
    engine=create_engine(url)
    assert 'dispatch_id' not in {c['name'] for c in inspect(engine).get_columns('application_event_deliveries')}
    engine.dispose()


def test_connector_claim_migration_preserves_receipt_and_refuses_unresolved_downgrade(tmp_path):
    url=f"sqlite:///{(tmp_path/'connector-claims.db').as_posix()}"
    _alembic(url,'upgrade','1bf67d2435e6')
    engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO module_packages (id,module_id,version,manifest,sha256,size_bytes,file_path,registrations) VALUES (1,'org.example.connector','1.0.0','{}',:sha,1,'unused','[]')"),{'sha':'a'*64})
        db.execute(text("INSERT INTO application_extension_installations (id,module_id,module_package_id,instance_id,status,enabled,socket_path,configuration,authority_incarnation,authority_epoch) VALUES (1,'org.example.connector',1,:instance,'active',1,'unused','{}',:instance32,:instance32)"),{'instance':'a'*24,'instance32':'a'*32})
        db.execute(text("INSERT INTO application_connector_attempts (id,request_id,application_installation_id,connector_id,method,path_hash,outcome) VALUES (1,'connector_old',1,'api','POST',:hash,'ambiguous')"),{'hash':'b'*64})
    engine.dispose();_alembic(url,'upgrade','head');_alembic(url,'check')
    engine=create_engine(url)
    with engine.begin() as db:
        assert db.execute(text('SELECT request_id,outcome,dispatch_metadata FROM application_connector_attempts')).one()==('connector_old','ambiguous',None)
        db.execute(text("UPDATE application_connector_attempts SET outcome='in_progress',dispatch_metadata='{}'"))
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError) as blocked:_alembic(url,'downgrade','1bf67d2435e6')
    assert 'Resolve in-flight' in blocked.value.stderr
    engine=create_engine(url)
    assert 'dispatch_metadata' in {c['name'] for c in inspect(engine).get_columns('application_connector_attempts')}
    with engine.begin() as db:db.execute(text("UPDATE application_connector_attempts SET outcome='ambiguous'"))
    engine.dispose();_alembic(url,'downgrade','1bf67d2435e6')
    engine=create_engine(url)
    assert 'dispatch_metadata' not in {c['name'] for c in inspect(engine).get_columns('application_connector_attempts')}
    engine.dispose()
