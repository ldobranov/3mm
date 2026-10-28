"""Descriptor denial and an additive migration over existing Core records."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest

from backend.services.module_packages import validate_module_package, ModulePackageError
from backend.tests.test_module_packages import application_package
from backend.tests.test_application_tasks import load_builder
from three_mm_protocol.application_tasks import TaskSubmitV1, TaskStatusV1


def test_task_consent_is_admitted_by_the_public_api_request_contract():
    from backend.routes.application_authority import ConsentAllowRequest, ReviewRequest
    body = {"request_id": "a" * 32, "preview_id": "b" * 32,
        "expected_revision": "c" * 32, "fingerprint": "d" * 64,
        "scopes": ["task:calculate"], "user_permissions": [], "accept_native_code": True}
    assert ConsentAllowRequest.model_validate(body).scopes == ["task:calculate"]
    assert ReviewRequest(request_id="a" * 32, native_review_id="b" * 32,
        scopes=["task:calculate"]).scopes == ["task:calculate"]
    with pytest.raises(ValueError):
        ConsentAllowRequest.model_validate({**body, "scopes": ["task:calculate:all"]})


@pytest.mark.parametrize("fault", ["job", "missing_handler", "public", "unbounded", "resource", "duplicate", "timeout"])
def test_task_profile_never_admits_legacy_or_broader_work(fault):
    builder = load_builder(); manifest, definition = builder.descriptors()
    if fault == "job": definition["operations"][1]["kind"] = "job"
    if fault == "missing_handler": definition["tasks"] = []
    if fault == "public": definition["operations"][1]["audiences"] = ["public"]
    if fault == "unbounded": definition["operations"][1]["input_schema"]["properties"]["upper"].pop("maximum")
    if fault == "resource": definition["platform_permissions"] = ["installation.identity.read"]
    if fault == "duplicate": definition["tasks"].append(deepcopy(definition["tasks"][0]))
    if fault == "timeout": definition["tasks"][0]["max_runtime_seconds"] = 3
    with pytest.raises(ModulePackageError): validate_module_package(application_package(definition=definition, manifest_value=manifest))


@pytest.mark.parametrize("payload", [{"nested": {}}, {"value": [1]}, {"value": float("nan")}, {"value": 2**54}, {"value": "x" * 513}])
def test_task_wire_refuses_unbounded_or_non_scalar_input(payload):
    from datetime import UTC, datetime, timedelta
    instant = datetime.now(UTC)
    with pytest.raises(ValueError): TaskSubmitV1(task_id="calculate", request_id="a" * 32,
        payload=payload, due_at=instant, not_after=instant + timedelta(seconds=5))


def test_unconfirmed_status_cannot_contain_a_successful_result():
    with pytest.raises(ValueError): TaskStatusV1(task_id="calculate", request_id="a" * 32,
        task_run_id="task_" + "b" * 32, status="unknown", progress=100, result={"total": 5050}, error_code="execution_unconfirmed")


def test_additive_task_migration_and_downgrade_preserve_existing_rows(tmp_path):
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "upgrade.db"))
    path = Path("backend/alembic/versions/4f29a071b819_application_result_tasks.py")
    spec = importlib.util.spec_from_file_location("task_migration", path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users(id INTEGER PRIMARY KEY, marker TEXT)")
        connection.exec_driver_sql("INSERT INTO users VALUES (1,'existing-owner')")
        connection.exec_driver_sql("CREATE TABLE module_packages(id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE application_extension_installations(id INTEGER PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            inspector = sa.inspect(connection)
            assert "application_task_runs" in inspector.get_table_names()
            columns = {item["name"] for item in inspector.get_columns("application_task_runs")}
            assert {"started", "dispatched", "incarnation", "grant_revision", "request_hash"} <= columns
            assert connection.exec_driver_sql("SELECT marker FROM users WHERE id=1").scalar_one() == "existing-owner"
            connection.exec_driver_sql("INSERT INTO module_packages VALUES (1)")
            connection.exec_driver_sql("INSERT INTO application_extension_installations VALUES (1)")
            from backend.db.application_task import ApplicationTaskRun
            from datetime import UTC, datetime, timedelta
            instant = datetime.now(UTC)
            connection.execute(ApplicationTaskRun.__table__.insert().values(task_run_id="task_" + "a" * 32,
                installation_id=1, package_id=1, incarnation="b" * 32, authority_epoch="c" * 32, grant_revision=1,
                task_id="calculate", request_id="d" * 32, request_hash="e" * 64, state="succeeded", payload={"upper": 100},
                due_at=instant, not_after=instant + timedelta(seconds=5), dispatched=True, started=True,
                progress=100, result={"total": 5050}))
            with pytest.raises(RuntimeError, match="history"):
                migration.downgrade()
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM application_task_runs").scalar_one() == 1
            # Explicit disposal of this disposable test row, then empty downgrade.
            connection.exec_driver_sql("DELETE FROM application_task_runs")
            migration.downgrade()
        assert "application_task_runs" not in sa.inspect(connection).get_table_names()
        assert connection.exec_driver_sql("SELECT marker FROM users WHERE id=1").scalar_one() == "existing-owner"
    engine.dispose()


def test_schedule_migration_preserves_one_shot_results_and_guards_retained_history(tmp_path):
    engine=sa.create_engine("sqlite:///"+str(tmp_path/"schedules.db"))
    def load(revision):
        path=next(Path("backend/alembic/versions").glob(revision+"_*.py"))
        spec=importlib.util.spec_from_file_location("migration_"+revision,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    one_shot=load("4f29a071b819");schedule=load("5a30b182c920")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE application_extension_installations(id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE module_packages(id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE application_command_requests(command_id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO application_extension_installations VALUES(1)")
        connection.exec_driver_sql("INSERT INTO module_packages VALUES(1)")
        with Operations.context(MigrationContext.configure(connection)):
            one_shot.upgrade()
            connection.exec_driver_sql("INSERT INTO application_task_runs(task_run_id,installation_id,package_id,incarnation,authority_epoch,grant_revision,task_id,request_id,request_hash,state,payload,due_at,not_after,dispatched,started,progress,result) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("task_"+"a"*32,1,1,"b"*32,"c"*32,1,"calculate","d"*32,"e"*64,"succeeded",'{}',"2026-10-25","2026-10-26",1,1,100,'{"total":5050}'))
            old=connection.exec_driver_sql("SELECT request_id,state,progress,result FROM application_task_runs").fetchall()
            schedule.upgrade()
            assert connection.exec_driver_sql("SELECT request_id,state,progress,result FROM application_task_runs").fetchall()==old
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM application_task_schedules").scalar_one()==0
            assert "task_run_id" in {c["name"] for c in sa.inspect(connection).get_columns("application_command_requests")}
            connection.exec_driver_sql("UPDATE application_task_runs SET schedule_id=?",("schedule_"+"f"*32,))
            with pytest.raises(RuntimeError,match="history"):schedule.downgrade()
            connection.exec_driver_sql("UPDATE application_task_runs SET schedule_id=NULL")
            schedule.downgrade()
            assert connection.exec_driver_sql("SELECT request_id,state,progress,result FROM application_task_runs").fetchall()==old
    engine.dispose()
