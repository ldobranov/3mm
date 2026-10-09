"""Real populated migration preserves legacy data and adds no live grants."""

import re
import subprocess

import pytest
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

from backend.db.authority import CoreAuthorityGuard
from backend.tests.test_migration_history import _alembic


PREVIOUS = "a7bf06b7c8d9"
REVISION = "b8c017c8d9e0"


def snapshot(engine, columns=None):
    with engine.connect() as connection:
        metadata = MetaData()
        names = sorted(
            set(inspect(connection).get_table_names())
            - {"alembic_version", "core_authority_guard"}
        )
        tables = {
            name: Table(name, metadata, autoload_with=connection) for name in names
        }
        if columns is None:
            columns = {name: tuple(table.c.keys()) for name, table in tables.items()}
        return columns, {
            name: connection.execute(
                select(*(table.c[key] for key in columns[name])).order_by(
                    *table.primary_key.columns
                )
            ).fetchall()
            for name, table in tables.items()
        }


def seed(engine):
    with engine.begin() as connection:
        for index in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO module_packages(id,module_id,version,manifest,sha256,size_bytes,file_path,registrations) VALUES (:i,:m,'1.0.0','{}',:sha,1,'unused','[]')"
                ),
                {"i": index, "m": f"org.example.app{index}", "sha": str(index) * 64},
            )
            connection.execute(
                text(
                    "INSERT INTO application_extension_installations(id,module_id,module_package_id,instance_id,active_version,status,enabled,socket_path,configuration) VALUES (:i,:m,:i,:instance,'1.0.0',:status,:enabled,'unused',:config)"
                ),
                {
                    "i": index,
                    "m": f"org.example.app{index}",
                    "instance": str(index) * 24,
                    "status": "active" if index == 1 else "disabled",
                    "enabled": index == 1,
                    "config": '{"private":"preserved","DEVICE_ID":"dev_'
                    + str(index) * 32
                    + '"}',
                },
            )
            connection.execute(
                text(
                    "INSERT INTO devices(id,device_id,role,protocol_version,approved_at) VALUES (:i,:device,'node','1.0','2026-10-08')"
                ),
                {"i": index, "device": "dev_" + str(index) * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO device_credentials(device_id,credential_id,secret_hash) VALUES (:i,:credential,:hash)"
                ),
                {
                    "i": index,
                    "credential": "cred_" + str(index) * 32,
                    "hash": "unchanged-verifier",
                },
            )
        connection.execute(
            text(
                "INSERT INTO device_platform_states(device_id,authority_status,lifecycle,revision) VALUES (1,'released','unowned',7)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO device_states(device_id,desired_revision,desired_state,reported_revision,reported_state) VALUES (1,8,:state,6,'{}')"
            ),
            {"state": '{"x":1}'},
        )
        connection.execute(
            text(
                "INSERT INTO application_secret_references(id,secret_ref,application_installation_id,label,credential_kind,encrypted_value,version) VALUES (1,:ref,1,'private','basic','ciphertext-preserved',9)"
            ),
            {"ref": "secret_" + "a" * 32},
        )
        for index in (1, 2):
            connection.execute(
                text(
                    "INSERT INTO application_connector_bindings(id,application_installation_id,connector_id,destination_origin,secret_reference_id,enabled,last_outcome) VALUES (:i,1,:connector,'https://example.test',1,:enabled,'ambiguous')"
                ),
                {"i": index, "connector": f"api{index}", "enabled": index == 1},
            )
        connection.execute(
            text(
                "INSERT INTO application_command_epochs(installation_id,generation) VALUES (1,:generation)"
            ),
            {"generation": "c" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO device_commands(command_id,device_id,command_type,payload,idempotency_key,status,created_at,expires_at,delivery_attempts) VALUES ('cmd_one',1,'application.capability.invoke','{}','once','unknown','2026-10-08','2030-01-01',1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO application_command_requests(command_id,installation_id,generation,package_id,claimed) VALUES ('cmd_one',1,:generation,1,1)"
            ),
            {"generation": "c" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO application_job_states(application_installation_id,job_id,next_run_at,lease_token,last_outcome,last_error,run_count) VALUES (1,'sync','2030-01-01',:lease,'unknown','execution_unconfirmed',12)"
            ),
            {"lease": "d" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO application_event_cursors(application_installation_id,subscription_id,last_event_id,acknowledged_count,dead_letter_count,dropped_dead_letter_count) VALUES (1,'events','evt_old',17,2,1)"
            )
        )


def assert_legacy_preserved(engine, columns, original):
    actual = snapshot(engine, columns)[1]
    # The migration explicitly materializes one previously absent default state.
    # Every original row and column must remain byte/value-equivalent.
    actual["device_platform_states"] = [
        row for row in actual["device_platform_states"] if row[0] != 2
    ]
    assert actual == original


def test_populated_upgrade_repeat_and_unused_downgrade_preserve_all_legacy_columns(
    tmp_path,
):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    seed(engine)
    columns, original = snapshot(engine)
    engine.dispose()

    _alembic(url, "upgrade", REVISION)
    # Historical revision: current-model parity belongs to the latest migration
    # tests, not to this pre-policy-review schema.
    engine = create_engine(url)
    assert_legacy_preserved(engine, columns, original)
    with engine.connect() as connection:
        apps = connection.execute(
            text(
                "SELECT authority_incarnation,authority_epoch,authority_mode FROM application_extension_installations ORDER BY id"
            )
        ).fetchall()
        connectors = (
            connection.execute(
                text(
                    "SELECT authority_revision FROM application_connector_bindings ORDER BY id"
                )
            )
            .scalars()
            .all()
        )
        controls = connection.execute(
            text(
                "SELECT device_id,control_generation,revision,lifecycle FROM device_platform_states ORDER BY device_id"
            )
        ).fetchall()
        guard = connection.execute(
            text(
                "SELECT generation,revision FROM core_authority_guard WHERE singleton_id=1"
            )
        ).one()
        generations = (
            [value for row in apps for value in row[:2]]
            + connectors
            + [row[1] for row in controls] + [guard[0]]
        )
        assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in generations)
        assert len(set(generations)) == len(generations)
        assert [row[2] for row in apps] == ["compatibility", "compatibility"]
        assert [(row[0], row[2], row[3]) for row in controls] == [
            (1, 7, "unowned"), (2, 0, "active"),
        ]
        assert guard[1] == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    engine.dispose()

    _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT device_id,control_generation,revision,lifecycle FROM device_platform_states ORDER BY device_id"
        )).fetchall() == controls
        assert (
            connection.execute(
                text(
                    "SELECT authority_incarnation,authority_epoch,authority_mode FROM application_extension_installations ORDER BY id"
                )
            ).fetchall()
            == apps
        )
        assert (
            connection.execute(
                text(
                    "SELECT authority_revision FROM application_connector_bindings ORDER BY id"
                )
            )
            .scalars()
            .all()
            == connectors
        )
        assert (
            connection.execute(
                text(
                    "SELECT generation,revision FROM core_authority_guard WHERE singleton_id=1"
                )
            ).one()
            == guard
        )
    engine.dispose()

    _alembic(url, "downgrade", PREVIOUS)
    engine = create_engine(url)
    assert_legacy_preserved(engine, columns, original)
    # Downgrade must not destructively delete the additive legacy-default row.
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT authority_status,lifecycle,revision FROM device_platform_states WHERE device_id=2"
        )).one() == ("bound", "active", 0)
    assert "core_authority_guard" not in inspect(engine).get_table_names()
    engine.dispose()


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE core_authority_guard SET revision=2",
        "UPDATE application_extension_installations SET authority_mode='review_required'",
    ],
)
def test_used_metadata_cannot_silently_downgrade(tmp_path, change):
    url = f"sqlite:///{(tmp_path / 'used.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    seed(engine)
    engine.dispose()
    _alembic(url, "upgrade", REVISION)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(change))
    before = snapshot(engine)
    engine.dispose()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        _alembic(url, "downgrade", PREVIOUS)
    assert "Authority metadata has been used" in caught.value.stderr
    engine = create_engine(url)
    assert snapshot(engine) == before
    assert "core_authority_guard" in inspect(engine).get_table_names()
    engine.dispose()


@pytest.mark.parametrize("populated", [False, True])
def test_precreated_guard_is_initialized_or_preserved_not_replaced(tmp_path, populated):
    url = f"sqlite:///{(tmp_path / 'precreated.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS)
    engine = create_engine(url)
    assert "core_authority_guard" not in inspect(engine).get_table_names()
    CoreAuthorityGuard.__table__.create(engine)
    if populated:
        with engine.begin() as connection:
            connection.execute(
                CoreAuthorityGuard.__table__.insert().values(
                    singleton_id=1,
                    generation="e" * 32,
                    revision=9,
                )
            )
    engine.dispose()
    _alembic(url, "upgrade", REVISION)
    # Current-model parity is checked at head in the policy-review migration tests.
    engine = create_engine(url)
    with engine.connect() as connection:
        generation, revision = connection.execute(
            text(
                "SELECT generation,revision FROM core_authority_guard WHERE singleton_id=1"
            )
        ).one()
        if populated:
            assert (generation, revision) == ("e" * 32, 9)
        else:
            assert re.fullmatch(r"[0-9a-f]{32}", generation) and revision == 1
    engine.dispose()
