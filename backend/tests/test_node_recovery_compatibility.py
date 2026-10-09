"""C8 real migrations + encrypted/portable recovery on disposable state only."""

import sqlite3
import secrets
from contextlib import closing
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, create_engine, inspect
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register complete related ORM metadata
from agent.core_client import (
    CommandJournal,
    DeviceCredential as AgentCredential,
    DeviceCredentialStore,
    OutboxEntry,
    OutboxStore,
)
from backend.db.device import Device, DeviceCredential, DeviceState
from backend.db.module import ModuleInstallation, ModulePackage
from backend.services.backups import build_backup_preview, read_backup_operation_status
from backend.services.device_capability_registry import (
    registered_capabilities,
)
from backend.services.device_runtime_features import (
    runtime_features_snapshot,
)
from backend.tests.test_backup_preview import DEVICE_ID, _settings
from backend.tests.test_migration_history import _alembic
from deployment.backup_compatibility import (
    BackupCompatibilityError,
    validate_release_path,
)
from deployment.create_backup import create_backup
from deployment.portable_backup import create_portable_export, import_portable_backup
from deployment.restore_backup import restore_backup
from three_mm_protocol import (
    AgentCommandResult,
    DeviceRuntimeFeaturesReportV1,
)
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = "526ab1c2d3e4"
C8_HEAD = "748cd3e4f5a6"
HEAD = ScriptDirectory(str(ROOT / "backend/alembic")).get_current_head()
TABLES = (
    "devices",
    "device_credentials",
    "device_states",
    "module_packages",
    "module_installations",
    "device_capability_providers",
    "device_runtime_features",
)


def snapshot(database):
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: [
                dict(row)
                for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")
            ]
            for table in TABLES
            if table in existing
        }


def seed(url, with_firmware):
    engine = create_engine(url)
    with Session(engine) as db:
        device = Device(
            device_id=DEVICE_ID,
            role="standalone",
            protocol_version="1.0",
            approved_at=datetime.now(UTC),
        )
        package = ModulePackage(
            module_id="org.example.generic",
            version="1.0.0",
            manifest={},
            registrations=[
                {"kind": "capability", "registration_id": "gpio.digital.control"}
            ],
            sha256="a" * 64,
            size_bytes=1,
            file_path="unused",
        )
        db.add_all([device, package])
        db.flush()
        db.add(
            DeviceCredential(
                device_id=device.id,
                credential_id="cred_" + "a" * 32,
                secret_hash="test-hash-unchanged",
            )
        )
        db.add(
            DeviceState(
                device_id=device.id,
                desired_revision=7,
                desired_state={"inventory_generation": 3},
                reported_revision=6,
            )
        )
        db.add(
            ModuleInstallation(
                device_id=device.id,
                module_package_id=package.id,
                module_id=package.module_id,
                installed_version=package.version,
                desired_version=package.version,
                status="succeeded",
                enabled=True,
            )
        )
        if with_firmware:
            embedded = Device(
                device_id="dev_" + "b" * 32,
                role="node",
                protocol_version="1.0",
                approved_at=datetime.now(UTC),
            )
            db.add(embedded)
            db.flush()
            db.add(
                DeviceCredential(
                    device_id=embedded.id,
                    credential_id="cred_" + "b" * 32,
                    secret_hash="test-firmware-hash",
                )
            )
            # Seed the historical schema, not today's ORM/service: an old
            # backup must not acquire columns that did not exist at creation.
            providers = Table(
                "device_capability_providers", MetaData(), autoload_with=db.connection()
            )
            values = dict(
                device_id=embedded.id,
                provider_type="embedded_firmware",
                provider_id="reference.runtime",
                provider_version="0.1",
                revision=1,
                enabled=False,  # Core-owned disable must survive recovery.
                capabilities=[{"capability_id": "gpio.digital.control", "metadata": {}}],
                reported_at=datetime.now(UTC),
            )
            if "configured_capability_ids" in providers.c:
                values["configured_capability_ids"] = ["gpio.digital.control"]
            db.execute(providers.insert().values(**values))
            features = DeviceRuntimeFeaturesReportV1(
                device_id=embedded.device_id,
                runtime_name="reference",
                runtime_version="0.1",
                features=tuple(sorted(MANDATORY_NODE_FEATURES)),
                command_types=("capability.invoke",),
                expected_revision=0,
            )
            # Historical backups must not run today's guarded writer or acquire
            # metadata/columns absent in the original release.
            runtime_features = Table(
                "device_runtime_features", MetaData(), autoload_with=db.connection()
            )
            db.execute(runtime_features.insert().values(
                device_id=embedded.id, revision=1,
                declaration=features.model_dump(mode="json", exclude={"expected_revision"}),
                received_at=datetime.now(UTC),
            ))
        db.commit()
        # Current-schema seed represents approved devices, which now create
        # platform metadata explicitly; historical backups retain their schema.
        platform = (Table("device_platform_states", MetaData(), autoload_with=db.connection())
                    if inspect(db.connection()).has_table("device_platform_states") else None)
        if platform is not None and "control_generation" in platform.c:
            for device_id in db.query(Device.id).all():
                db.execute(platform.insert().values(
                    device_id=device_id[0], authority_status="bound", lifecycle="active",
                    revision=0, control_generation=secrets.token_hex(16),
                ))
            db.commit()
    engine.dispose()


@pytest.mark.parametrize(
    "source_revision, fail_health",
    [(PREVIOUS, False), (C8_HEAD, False), (C8_HEAD, True), (HEAD, False), (HEAD, True)],
    ids=[
        "old-backup-upgrade",
        "mixed-runtime-upgrade",
        "old-backup-health-rollback",
        "mixed-runtime-restore",
        "failed-health-rollback",
    ],
)
def test_portable_restore_preserves_device_trust_providers_and_agent_evidence(
    tmp_path, monkeypatch, source_revision, fail_health
):
    settings = _settings(tmp_path)
    database = tmp_path / "core/3mm.db"
    database.unlink()  # Disposable fixture's placeholder database only.
    url = f"sqlite:///{database.as_posix()}"
    _alembic(url, "upgrade", source_revision)
    seed(url, with_firmware=source_revision != PREVIOUS)
    agent = settings.backups.agent_data_dir
    credential = AgentCredential(
        device_id=DEVICE_ID,
        credential_id="cred_" + "a" * 32,
        credential_secret="test-secret-" + "x" * 32,
        hub_endpoint="http://core.test",
        api_endpoint="http://core.test/api/v1",
    )
    DeviceCredentialStore(agent).save(credential)
    # These files are not added to an allowlist: the existing Agent area must
    # already archive every durable receipt/binding/outbox sidecar.
    receipt = AgentCommandResult(
        device_id=DEVICE_ID,
        command_id="cmd_" + "a" * 32,
        status="succeeded",
        completed_at=datetime.now(UTC),
    )
    CommandJournal(agent).save("legacy-receipt", receipt)
    (agent / "command-journal-proofs.json").write_text("{}", encoding="utf-8")
    pending = OutboxEntry(
        suffix="events", payload={"pending": True}, deduplication_key="stable-event"
    )
    OutboxStore(agent).enqueue(pending)
    expected = snapshot(database)
    expected_files = {
        path.name: path.read_bytes() for path in agent.iterdir() if path.is_file()
    }
    preview = build_backup_preview(settings)
    assert preview.ready
    assert {("agent", name) for name in expected_files} <= {
        (entry.area, entry.path) for entry in preview.manifest.entries
    }

    class Runtime:
        fail_once = fail_health
        generations = []

        def stop(self, _services):
            pass

        def start(self, _services):
            pass

        def migrate(self):
            _alembic(url, "upgrade", "head")

        def activate_and_verify(self):
            with closing(sqlite3.connect(database)) as connection:
                generation, revision = connection.execute(
                    "SELECT generation, revision FROM core_authority_guard"
                ).fetchone()
                assert revision == 2
                assert generation != live_generation
                assert generation not in self.generations
                self.generations.append(generation)
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("injected health failure")
            with closing(sqlite3.connect(database)) as connection:
                assert (
                    connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                )
                assert (
                    connection.execute(
                        "SELECT version_num FROM alembic_version"
                    ).fetchone()[0]
                    == HEAD
                )

    runtime = Runtime()
    key = tmp_path / "original.key"
    backup = create_backup(
        settings, key_file=key, requested_by_user_id=1, controller=runtime
    )
    portable = create_portable_export(
        settings.backups.storage_dir, key, backup.backup_id, "test-export-password"
    )
    imported_root = tmp_path / "fresh-recovery"
    new_key = tmp_path / "fresh.key"
    imported = import_portable_backup(
        portable.path,
        imported_root,
        new_key,
        "test-export-password",
        max_archive_bytes=32 * 1024 * 1024,
    )
    _alembic(url, "upgrade", "head")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE device_states SET desired_revision=9")
        connection.commit()
    DeviceCredentialStore(agent).save(
        credential.model_copy(
            update={
                "hub_endpoint": "http://live-core.test",
                "api_endpoint": "http://live-core.test/api/v1",
            }
        )
    )
    live = snapshot(database)
    with closing(sqlite3.connect(database)) as connection:
        live_generation = connection.execute("SELECT generation FROM core_authority_guard").fetchone()[0]
    live_files = {
        path.name: path.read_bytes() for path in agent.iterdir() if path.is_file()
    }
    target = settings.model_copy(
        update={
            "backups": settings.backups.model_copy(
                update={"storage_dir": imported_root}
            )
        }
    )
    arguments = dict(
        backup_id=imported,
        key_file=new_key,
        requested_by_user_id=1,
        runtime=runtime,
        service_ids=(1000, 1000),
        state_root=tmp_path,
        host_config=settings.backups.host_config_file,
        apply_ownership=False,
    )
    if fail_health:
        with pytest.raises(RuntimeError, match="injected health failure"):
            restore_backup(target, **arguments)
        assert snapshot(database) == live
        assert {
            path.name: path.read_bytes() for path in agent.iterdir() if path.is_file()
        } == live_files
        assert (
            read_backup_operation_status(imported_root / "status.json").state
            == "rolled_back"
        )
        return
    assert restore_backup(target, **arguments).state == "completed"
    restored = snapshot(database)
    for table, rows in expected.items():
        assert len(restored[table]) == len(rows)
        for original, current in zip(rows, restored[table], strict=True):
            # Migration may add columns, but every original value must survive.
            assert {column: current[column] for column in original} == original
    assert {
        path.name: path.read_bytes() for path in agent.iterdir() if path.is_file()
    } == expected_files
    assert DeviceCredentialStore(agent).load() == credential
    assert OutboxStore(agent).load() == [pending]
    assert CommandJournal(agent).get("legacy-receipt") == receipt
    engine = create_engine(url)
    with Session(engine) as db:
        local = db.query(Device).filter_by(device_id=DEVICE_ID).one()
        assert registered_capabilities(db, local)[0]["provider_type"] == "agent_module"
        assert runtime_features_snapshot(db, local).source == "legacy_unadvertised"
        if source_revision != PREVIOUS:
            embedded = db.query(Device).filter_by(device_id="dev_" + "b" * 32).one()
            assert registered_capabilities(db, embedded) == []
            assert runtime_features_snapshot(db, embedded).revision == 1
    engine.dispose()

    if source_revision == HEAD:
        # Repeating the exact same encrypted backup cannot restore its former
        # review identity, nor the identity of the first successful restore.
        assert restore_backup(target, **arguments).state == "completed"
        assert len(runtime.generations) == 2


def test_old_release_rejects_new_schema_backup_even_if_version_matches(tmp_path):
    # Build an isolated script catalog ending at the old revision; no live
    # downgrade/drop is used to simulate an older installed release.
    import shutil

    source = ScriptDirectory(str(ROOT / "backend/alembic"))
    versions = tmp_path / "backend/alembic/versions"
    versions.mkdir(parents=True)
    for revision in source.walk_revisions(base="base", head=PREVIOUS):
        shutil.copyfile(revision.path, versions / Path(revision.path).name)
    validate_release_path("0.3.0-beta.32", "0.3.0-beta.32", PREVIOUS, tmp_path)
    with pytest.raises(BackupCompatibilityError, match="no supported migration path"):
        validate_release_path("0.3.0-beta.32", "0.3.0-beta.32", HEAD, tmp_path)
