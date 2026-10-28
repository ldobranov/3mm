"""Core boot/admin and retained-data retirement, without product imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, UTC

import pytest
import sqlalchemy as sa
from backend.tests.test_migration_history import _alembic

PRODUCTS = ("extension_projects", "extension_project_files", "extension_project_builds",
    "automation_proposals", "automation_revisions", "automation_audit_events",
    "ai_credit_accounts", "ai_jobs", "ai_usage_ledger")


def table(engine, name):
    return sa.Table(name, sa.MetaData(), autoload_with=engine)


def snapshot(engine, name):
    with engine.connect() as connection:
        target = table(engine, name)
        # Compare every pre-existing value across the additive subject migration;
        # its new identity values/non-reuse are checked in test_application_user_subjects.
        columns = [c for c in target.c if name != 'users' or c.name != 'subject_id']
        return connection.execute(sa.select(*columns).order_by(target.c.id)).all()


def seed(connection, table_name, /, **overrides):
    target = table(connection, table_name)
    values = {}
    for column in target.c:
        if column.nullable or column.server_default is not None:
            continue
        if isinstance(column.type, sa.Boolean): value = True
        elif isinstance(column.type, sa.Integer): value = 7
        elif isinstance(column.type, sa.JSON): value = {"preserved": ["данни", 7]}
        elif isinstance(column.type, sa.DateTime): value = datetime(2026, 10, 26, tzinfo=UTC)
        else: value = table_name + "_" + column.name
        values[column.name] = value
    values.update(overrides)
    connection.execute(target.insert().values(**values))


@pytest.fixture(params=['6b41c293da31','head'])
def retired(tmp_path,request):
    url = "sqlite:///" + str(tmp_path / "retirement.db")
    _alembic(url, "upgrade", "5a30b182c920")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        seed(connection, "users", username="owner", email="owner@example.test", hashed_password="opaque-password")
        for name in PRODUCTS: seed(connection, name)
        seed(connection, "settings", id=81, key="ai_groq_api_key", value="opaque-encrypted-fixture")
        seed(connection, "settings", id=82, key="ai_provider", value="groq", language_code="bg")
        seed(connection, "settings", id=83, key="default_theme", value="dark")
        seed(connection, "setting_translations", id=91, setting_id=81, translated_value="opaque-translation")
        seed(connection, "setting_translations", id=92, setting_id=83, translated_value="тъмна")
    before = {name: snapshot(engine, name) for name in (*PRODUCTS, "users", "settings", "setting_translations")}
    _alembic(url, "upgrade", request.param)
    yield engine, url, before, request.param
    engine.dispose()


def test_retirement_preserves_all_product_values_and_scoped_settings(retired):
    engine, url, before, target = retired
    names = set(sa.inspect(engine).get_table_names())
    assert not set(PRODUCTS) & names
    for name in PRODUCTS:
        assert snapshot(engine, "retired_" + name) == before[name]
    assert snapshot(engine, "retired_ai_settings") == before["settings"][:2]
    assert snapshot(engine, "settings") == before["settings"][2:]
    assert snapshot(engine, "retired_ai_setting_translations") == before["setting_translations"][:1]
    assert snapshot(engine, "retired_setting_translations" if target=="head" else "setting_translations") == before["setting_translations"][1:]
    assert snapshot(engine, "users") == before["users"]
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    if target=="head":_alembic(url, "check")
    _alembic(url, "upgrade", target)
    assert snapshot(engine, "retired_ai_settings") == before["settings"][:2]
    if target=="head":
        with pytest.raises(subprocess.CalledProcessError):_alembic(url,"downgrade","5a30b182c920")
        assert snapshot(engine,"retired_setting_translations")==before["setting_translations"][1:]
        return
    _alembic(url, "downgrade", "5a30b182c920")
    for name, expected in before.items(): assert snapshot(engine, name) == expected


def test_recovery_refuses_to_overwrite_current_settings(retired):
    engine, url, before, target = retired
    with engine.begin() as connection:
        seed(connection, "settings", id=81, key="new-current-setting", value="keep")
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, "downgrade", "5a30b182c920")
    assert snapshot(engine, "retired_ai_settings") == before["settings"][:2]
    assert not set(PRODUCTS) & set(sa.inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == ("b096b7e82f86" if target=="head" else "6b41c293da31")
        assert connection.exec_driver_sql("SELECT value FROM settings WHERE id=81").scalar() == "keep"


def test_core_boot_and_admin_without_product_or_ai_modules(tmp_path):
    script = r'''
import importlib.abc,sys,json
class NoProductImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('three_mm_ai', 'backend.utils.ai_extension_builder',
                'backend.routes.ai_', 'backend.routes.extension_projects',
                'backend.db.automation', 'backend.db.extension_project',
                'backend.services.ai_', 'backend.services.automation_',
                'backend.schemas.ai_extension_builder', 'backend.schemas.extension_project',
                'backend.db.page', 'backend.db.extension', 'backend.db.universal_translation', 'backend.db.language_pack', 'backend.routes.page_routes', 'backend.routes.universal_translations', 'backend.utils.universal_translation_engine', 'backend.utils.extension_table_creator',
                'three_mm_crud', 'backend.db.runtime_extension', 'backend.routes.runtime_extensions', 'backend.services.runtime_extensions', 'three_mm_protocol.runtime_extension',
                'backend.db.display', 'backend.db.widget', 'backend.routes.display_routes', 'backend.schemas.display')):
            raise AssertionError('Core imported product code: '+fullname)
sys.meta_path.insert(0,NoProductImports())
from backend import main
from backend.database import Base,SessionLocal
from backend.db.user import User
from backend.utils.auth import hash_password
from fastapi.testclient import TestClient
def unavailable(): raise RuntimeError('optional service absent')
main._runtime_authority=unavailable
main._language_packages=unavailable
main.system_update_check_manager=None
with TestClient(main.app) as client:
    assert client.get('/health').status_code==200
    assert client.get('/ready').status_code==200
    assert main.app.state.core_components.snapshot()['status']=='degraded'
    for path in ('/api/ai/extensions/capabilities','/api/ai/automations/proposals',
            '/api/extension-projects','/api/admin/ai-settings','/api/admin/ai-settings/debug',
            '/display/read','/api/displays/my','/api/displays/1/widgets','/api/public/@owner/example'):
        assert client.get(path).status_code==404,path
    with SessionLocal() as db:
        db.add(User(username='admin',email='admin@example.test',hashed_password=hash_password('test'),role='admin'))
        db.add(User(username='viewer',email='viewer@example.test',hashed_password=hash_password('test'),role='registered'))
        db.commit()
    for email,expected in [('admin@example.test',200),('viewer@example.test',403)]:
        login=client.post('/api/user/login',json={'email':email,'password':'test'})
        assert login.status_code==200,login.text
        data=login.json();token=data.get('access_token') or data.get('token')
        assert token,data.keys()
        headers={'Authorization':'Bearer '+token}
        assert client.get('/api/v1/application-extensions',headers=headers).status_code==expected
        assert client.get('/api/admin/session-settings',headers=headers).status_code==expected
    assert not any(name.startswith(('ai_', 'automation_', 'extension_project')) for name in Base.metadata.tables)
    assert not {'displays','widgets','role_dashboard_grants'} & set(Base.metadata.tables)
print(json.dumps({'boot':'ready','optional_services':'degraded','admin':'allowed','viewer':'denied'}))
'''
    environment = {**os.environ, "DATABASE_URL": "sqlite:///" + str(tmp_path / "core.db"),
        "UPLOADS_DIR": str(tmp_path / "uploads"), "JWT_SECRET_KEY": "local-core-test-key-long-enough-for-hmac"}
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
        env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["admin"] == "allowed"
