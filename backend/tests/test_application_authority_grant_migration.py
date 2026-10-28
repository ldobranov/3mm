"""Sealed authority migration: no inferred grants, no history loss."""

import subprocess

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.db.application_authority_grant import (
    ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native,
    ApplicationAuthorityPlan as Plan, ApplicationAuthorityAction as Action,
)
from backend.tests.test_authority_metadata_migration import seed
from backend.tests.test_migration_history import _alembic, _head_revision
from backend.tests.test_policy_review_migration import snapshot


PREVIOUS = 'c9d128d9e0f1'
REVISION = _head_revision()
TABLES = ('application_native_reviews', 'application_authority_plans',
    'application_authority_grants', 'application_authority_actions')
PRODUCTS = {'extension_projects', 'extension_project_files', 'extension_project_builds',
    'automation_proposals', 'automation_revisions', 'automation_audit_events',
    'ai_credit_accounts', 'ai_jobs', 'ai_usage_ledger', 'displays', 'widgets', 'role_dashboard_grants', 'runtime_extension_definitions', 'runtime_entity_records','pages','extensions','extension_tables','extension_fields','table_translations','migration_history','setting_translations','language_packs'}
EMPTY_RETIREMENT = {'retired_ai_settings', 'retired_ai_setting_translations',
    'retired_dashboard_permissions', 'retired_dashboard_role_permissions',
    'retired_dashboard_group_permissions', 'module_package_retained_references','language_extension_installations','retired_content_permissions','retired_content_role_permissions','retired_content_group_permissions'}


def retired(expected):
    # Current head retires product data without altering its values. These
    # authority fixtures contain no provider settings; populated setting/secret
    # retirement has its own migration/recovery acceptance.
    assert not any(row[1] in {'ai_provider', 'ai_groq_api_key', 'ai_openrouter_api_key'}
        for row in expected['settings'])
    return {**{('retired_' + name if name in PRODUCTS else name): rows
        for name, rows in expected.items()}, **{name: [] for name in EMPTY_RETIREMENT}}


def recovered(expected):
    assert all(expected[name] == [] for name in EMPTY_RETIREMENT)
    return {(name.removeprefix('retired_') if name.removeprefix('retired_') in PRODUCTS else name): rows
        for name, rows in expected.items()
        if name not in EMPTY_RETIREMENT}


def test_populated_upgrade_has_model_parity_no_auto_grants_and_empty_downgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'grant-migration.db').as_posix()}"
    _alembic(url, 'upgrade', 'a7bf06b7c8d9')
    engine = create_engine(url)
    seed(engine)
    engine.dispose()
    _alembic(url, 'upgrade', PREVIOUS)
    engine = create_engine(url)
    before = snapshot(engine)
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    expected=retired({**before,"application_command_requests":[(*row,None) for row in before["application_command_requests"]]})
    assert snapshot(engine, list(expected)) == expected
    assert all(not rows for rows in snapshot(engine, list(TABLES)).values())
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == REVISION
        assert not db.execute(text('PRAGMA foreign_key_check')).all()
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'downgrade', PREVIOUS)
    engine = create_engine(url)
    assert snapshot(engine) == before
    assert not set(TABLES) & set(inspect(engine).get_table_names())
    engine.dispose()


@pytest.mark.parametrize('retained', ['history', 'enforced'])
def test_used_state_cannot_be_destructively_downgraded(tmp_path, retained):
    url = f"sqlite:///{(tmp_path / 'used.db').as_posix()}"
    _alembic(url, 'upgrade', 'a7bf06b7c8d9')
    engine = create_engine(url)
    seed(engine)
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    with engine.begin() as db:
        if retained == 'history':
            db.execute(Grant.__table__.insert().values(installation_id=1, revision=1, payload='{}', key_id='review_' + '1' * 32, seal='2' * 64))
        else:
            db.execute(text("UPDATE application_extension_installations SET authority_mode='enforced' WHERE id=1"))
    before = snapshot(engine)
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'downgrade', PREVIOUS)
    engine = create_engine(url)
    # Later retained-data/task revisions may remove their EMPTY catalogs before the
    # authority downgrade reaches this historical guard. No owned data is lost.
    assert before["application_retained_data"] == []
    assert before["application_task_runs"] == []
    assert before["application_task_schedules"] == []
    expected={name:rows for name,rows in before.items()
        if name not in {"application_retained_data","application_task_runs","application_task_schedules"}}
    assert all(row[-1] is None for row in expected["application_command_requests"])
    expected["application_command_requests"]=[row[:-1] for row in expected["application_command_requests"]]
    expected=recovered(expected)
    assert snapshot(engine) == expected
    assert "application_retained_data" not in inspect(engine).get_table_names()
    with engine.connect() as db:
        # Later reversible revisions complete; authority history stops at its guard.
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'fcd45b0213c4'
    engine.dispose()


def test_partial_precreated_schema_is_not_auto_repaired(tmp_path):
    url = f"sqlite:///{(tmp_path / 'partial.db').as_posix()}"
    _alembic(url, 'upgrade', PREVIOUS)
    engine = create_engine(url)
    Native.__table__.create(engine)
    before = snapshot(engine)
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, 'upgrade', 'head')
    engine = create_engine(url)
    assert snapshot(engine) == before
    engine.dispose()


def test_complete_precreated_orm_schema_is_validated_without_losing_history(tmp_path):
    url = f"sqlite:///{(tmp_path / 'precreated.db').as_posix()}"
    _alembic(url, 'upgrade', PREVIOUS)
    engine = create_engine(url)
    for model in (Native, Plan, Grant, Action):
        model.__table__.create(engine)
    with engine.begin() as db:
        db.execute(Native.__table__.insert().values(review_id='1' * 32, installation_id=1,
            payload='{}', key_id='review_' + '2' * 32, seal='3' * 64))
    before = snapshot(engine)
    engine.dispose()
    _alembic(url, 'upgrade', 'head')
    _alembic(url, 'check')
    engine = create_engine(url)
    after = snapshot(engine)
    # Current head adds empty retained-data/task catalogs to these precreated
    # authority tables; every pre-existing table and history row stays identical.
    assert after == retired({**before, "application_retained_data": [], "application_task_runs": [], "application_task_schedules": []})
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == REVISION
    engine.dispose()
