"""Additive populated upgrade/downgrade: no identity/credential/state loss."""

from sqlalchemy import create_engine, text
from backend.tests.test_migration_history import _alembic


def test_platform_upgrade_preserves_registered_devices_credentials_and_state(tmp_path):
    url = f"sqlite:///{(tmp_path / 'platform.db').as_posix()}"
    _alembic(url, "upgrade", "748cd3e4f5a6")
    engine = create_engine(url)
    with engine.begin() as connection:
        for index in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO devices(id,device_id,role,protocol_version,approved_at,revoked_at) VALUES (:i,:d,'node','1.0','2026-10-03',:r)"
                ),
                {
                    "i": index,
                    "d": "dev_" + str(index) * 32,
                    "r": "2026-10-03" if index == 2 else None,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO device_credentials(device_id,credential_id,secret_hash) VALUES (:i,:c,:h)"
                ),
                {"i": index, "c": "cred_" + str(index) * 32, "h": str(index) * 64},
            )
        connection.execute(
            text(
                "INSERT INTO device_states(device_id,desired_revision,desired_state,reported_revision,reported_state) VALUES (1,7,:state,7,'{}')"
            ),
            {"state": '{"inventory_generation":5}'},
        )
        original = [
            connection.execute(text("SELECT * FROM " + table)).fetchall()
            for table in ("devices", "device_credentials", "device_states")
        ]
    engine.dispose()
    _alembic(url, "upgrade", "head")
    _alembic(url, "check")
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT device_id,authority_status,lifecycle,revision FROM device_platform_states ORDER BY device_id"
            )
        ).fetchall() == [(1, "bound", "active", 0), (2, "bound", "revoked", 0)]
        assert [
            connection.execute(text("SELECT * FROM " + table)).fetchall()
            for table in ("devices", "device_credentials", "device_states")
        ] == original
    engine.dispose()
    _alembic(url, "downgrade", "748cd3e4f5a6")
    engine = create_engine(url)
    with engine.connect() as connection:
        assert [
            connection.execute(text("SELECT * FROM " + table)).fetchall()
            for table in ("devices", "device_credentials", "device_states")
        ] == original
    engine.dispose()
