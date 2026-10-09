"""Sealed authority migration: no inferred grants, no history loss."""

import subprocess

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.db.application_authority_grant import (
    ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native,
    ApplicationAuthorityPlan as Plan, ApplicationAuthorityAction as Action,
)
from backend.tests.test_authority_metadata_migration import seed
from backend.tests.test_migration_history import _alembic
from backend.tests.test_policy_review_migration import snapshot


PREVIOUS = 'c9d128d9e0f1'
REVISION = 'fcd45b0213c4'  # Current head also preserves application event producers.
TABLES = ('application_native_reviews', 'application_authority_plans',
    'application_authority_grants', 'application_authority_actions')


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
    assert snapshot(engine, list(before)) == before
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
    assert snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == REVISION
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
    assert snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == REVISION
    engine.dispose()
