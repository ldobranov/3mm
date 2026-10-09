"""Real migration/retention checks on populated disposable SQLite databases."""

import importlib
import subprocess

import pytest
from sqlalchemy import CheckConstraint, MetaData, Table, UniqueConstraint, create_engine, inspect, select, text

from backend.db.application_policy_review import ApplicationPolicyReview, ApplicationPolicyReviewDecision
from backend.tests.test_authority_metadata_migration import seed
from backend.tests.test_migration_history import _alembic


PREVIOUS = "b8c017c8d9e0"
REVISION = "c9d128d9e0f1"
TABLES = ("application_policy_reviews", "application_policy_review_decisions")


def snapshot(engine, names=None):
    with engine.connect() as db:
        names = names or sorted(set(inspect(db).get_table_names()) - {"alembic_version"})
        result = {}
        for name in names:
            table = Table(name, MetaData(), autoload_with=db)
            result[name] = db.execute(select(table).order_by(*table.primary_key.columns)).all()
        return result


def insert_history(engine):
    with engine.begin() as db:
        db.execute(ApplicationPolicyReview.__table__.insert().values(
            review_id="1" * 32, core_installation_id="inst_" + "2" * 32,
            recovery_generation="3" * 32, application_installation_id=7,
            incarnation="4" * 32, module_id="org.example.reference", artifact_sha256="5" * 64,
            subject_json="{}", subject_sha256="6" * 64, state="review_required", revision="7" * 32))
        db.execute(ApplicationPolicyReviewDecision.__table__.insert().values(
            decision_id="8" * 32, review_id="1" * 32, request_id="9" * 32,
            request_sha256="a" * 64, actor_user_id=42, actor_session_id=43,
            actor_session_sha256="b" * 64, recovery_generation="3" * 32,
            previous_revision=None, revision="7" * 32, decision="recorded", reason="review_required"))


def test_populated_historical_upgrade_repeat_and_empty_downgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    _alembic(url, "upgrade", "a7bf06b7c8d9")
    engine = create_engine(url)
    seed(engine)
    engine.dispose()
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    before = snapshot(engine)
    engine.dispose()
    _alembic(url, "upgrade", REVISION)
    # Current-model parity is checked by the latest grant migration tests.
    engine = create_engine(url)
    assert snapshot(engine, list(before)) == before  # Includes the guard unchanged.
    assert all(not rows for rows in snapshot(engine, list(TABLES)).values())
    with engine.connect() as db:
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
        assert not inspect(db).get_foreign_keys(TABLES[0])
        assert {fk["referred_table"] for fk in inspect(db).get_foreign_keys(TABLES[1])} == {TABLES[0]}
    engine.dispose()
    _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    assert snapshot(engine, list(before)) == before
    engine.dispose()
    _alembic(url, "downgrade", PREVIOUS)
    engine = create_engine(url)
    assert not set(TABLES) & set(inspect(engine).get_table_names())
    assert snapshot(engine) == before
    engine.dispose()


def test_history_cannot_be_silently_downgraded_or_cascade_deleted(tmp_path):
    url = f"sqlite:///{(tmp_path / 'used.db').as_posix()}"
    _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    insert_history(engine)
    before = snapshot(engine)
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        _alembic(url, "downgrade", PREVIOUS)
    assert "Policy review history exists" in caught.value.stderr
    engine = create_engine(url)
    assert snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
    engine.dispose()


@pytest.mark.parametrize("populated", [False, True])
def test_precreated_complete_schema_is_preserved_not_replaced(tmp_path, populated):
    url = f"sqlite:///{(tmp_path / 'precreated.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    ApplicationPolicyReview.__table__.create(engine)
    ApplicationPolicyReviewDecision.__table__.create(engine)
    if populated:
        insert_history(engine)
    before = snapshot(engine)
    engine.dispose()
    _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    assert snapshot(engine) == before
    engine.dispose()


@pytest.mark.parametrize("malformed", [False, True])
def test_partial_or_unexpected_schema_is_not_repaired_or_erased(tmp_path, malformed):
    url = f"sqlite:///{(tmp_path / 'partial.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE application_policy_reviews (unexpected TEXT)"))
        if malformed:
            db.execute(text("CREATE TABLE application_policy_review_decisions (unexpected TEXT)"))
    before = snapshot(engine)
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError):
        _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    assert snapshot(engine) == before
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
    engine.dispose()


@pytest.mark.parametrize("defect", ["state_check", "request_unique", "cascade", "nullable_actor"])
def test_matching_column_names_cannot_hide_weakened_constraints(monkeypatch, defect):
    migration = importlib.import_module("backend.alembic.versions.c9d128d9e0f1_policy_review_store")
    metadata = MetaData()
    review = ApplicationPolicyReview.__table__.to_metadata(metadata)
    decision = ApplicationPolicyReviewDecision.__table__.to_metadata(metadata)
    if defect == "state_check":
        review.constraints.remove(next(constraint for constraint in review.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name == "ck_policy_review_state"))
    elif defect == "request_unique":
        decision.constraints.remove(next(constraint for constraint in decision.constraints
            if isinstance(constraint, UniqueConstraint) and tuple(constraint.columns.keys()) == ("request_id",)))
    elif defect == "cascade":
        next(iter(decision.foreign_key_constraints)).ondelete = "CASCADE"
    else:
        decision.c.actor_user_id.nullable = True
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    insert_history(engine)
    before = snapshot(engine)
    with engine.begin() as db:
        monkeypatch.setattr(migration.op, "get_bind", lambda: db)
        with pytest.raises(RuntimeError, match="Unexpected policy review schema"):
            migration.upgrade()
    assert snapshot(engine) == before
    engine.dispose()
