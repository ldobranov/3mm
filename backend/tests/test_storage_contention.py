"""Explicit SQLite observation: bounded, metadata-only, never a replay or a lock owner claim."""
import json

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from backend.db.user import User
from backend.storage import contention
from backend.tests.test_diagnostics import _client, use_test_jwt_secret


def test_real_sqlite_sample_excludes_old_connections_and_raw_values(tmp_path):
    engine = create_engine("sqlite:///" + (tmp_path / "test.db").as_posix())
    now = [100.]
    observer = contention.SQLiteWriteObserver(clock=lambda: now[0])
    observer.install(engine)
    metadata = MetaData()
    table = Table("private_test_table", metadata, Column("id", Integer, primary_key=True), Column("value", String))
    metadata.create_all(engine)
    old = engine.connect()
    ongoing = []
    def work(_seconds):
        with old.begin():
            old.execute(table.insert().values(value="unobserved old connection"))
        with engine.connect() as conn:
            conn.execute(table.insert().values(value="private value")); now[0] += .5
            conn.execute(table.update().values(value="another private value"))
            conn.commit()
            conn.execute(table.select())
            conn.rollback()
        # A raw read or untyped raw write is not interpreted as an ORM write.
        with engine.begin() as conn:
            conn.exec_driver_sql("UPDATE private_test_table SET value='private'")
        conn = engine.connect()
        ongoing.append(conn)
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        now[0] += 1
        with pytest.raises(contention.ObservationBusy):
            observer.observe(wait=lambda _: pytest.fail("nested sample"))
    try:
        sample = observer.observe(wait=work)
        assert sample == {"kind": "sqlite_write_sample", "schema_version": 1,
            "coverage": "new_core_engine_connections", "window_ms": 1500, "limited": False,
            "families": [{"source": "other", "observed": 2, "open_at_end": 1, "longest_ms": 1000}]}
        assert "private" not in json.dumps(sample)
        ongoing[0].rollback()
        with pytest.raises(contention.ObservationBusy) as exc:
            observer.observe(wait=work)
        assert 1 <= exc.value.retry_after <= 31
        now[0] += 32
        assert observer.observe(wait=lambda _: None)["families"] == []
    finally:
        for conn in ongoing:
            conn.close()
        old.close()
        engine.dispose()


def test_failed_or_unavailable_sample_releases_gate(tmp_path):
    observer = contention.SQLiteWriteObserver()
    with pytest.raises(RuntimeError):
        observer.observe()
    engine = create_engine("sqlite://")
    observer.install(engine)
    def interrupt(_):
        raise ValueError("interrupted")
    try:
        with pytest.raises(ValueError):
            observer.observe(wait=interrupt)
        assert observer.window is None and not observer.gate.locked()
    finally:
        engine.dispose()


def test_sample_denies_without_collecting_and_rechecks_current_admin(monkeypatch):
    http, db, admin, viewer = _client()
    url = "/api/v1/diagnostics/storage-sample"
    user = {"Authorization": f"Bearer {viewer}"}
    privileged = {"Authorization": f"Bearer {admin}"}
    calls = []
    def collect():
        assert not db.in_transaction()
        calls.append(1)
        return {"families": []}
    monkeypatch.setattr(contention.write_observer, "observe", collect)
    try:
        with http:
            assert http.post(url).status_code == 401
            assert http.post(url, headers=user).status_code == 403
            assert not calls
            ok = http.post(url, headers=privileged)
            assert ok.status_code == 200 and ok.headers["Cache-Control"] == "no-store"
            def busy():
                raise contention.ObservationBusy(9)
            monkeypatch.setattr(contention.write_observer, "observe", busy)
            refused = http.post(url, headers=privileged)
            assert refused.status_code == 429 and refused.headers["Retry-After"] == "9"
            def downgrade():
                result = collect()
                db.query(User).filter_by(username="admin").update({"role": "user"})
                db.commit()
                return result
            monkeypatch.setattr(contention.write_observer, "observe", downgrade)
            lost = http.post(url, headers=privileged)
            assert lost.status_code == 403 and "families" not in lost.json()
    finally:
        db.close()
