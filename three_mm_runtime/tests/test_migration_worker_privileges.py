"""Capability prerequisite + opt-in real systemd launcher regression.

Live cases use only fresh disposable test directories outside production state.
They prove process privilege drop
and owned migration SQL, not Core grants/transport, boot or recovery acceptance.
They never change an installed service, account, key or application namespace.
"""

import hashlib
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from three_mm_runtime import application_relational_installation as installation
from three_mm_runtime import application_relational_migrations as worker
from three_mm_runtime import application_relational_preparation as preparation

ROOT = Path(__file__).parents[2]
HELPER = ROOT / "deployment/systemd/3mm-update-helper.service"


@pytest.mark.parametrize(
    "contents, allowed",
    [
        ("CapEff:\t00000000000000c0\n", True),
        ("CapEff:\t000001fffffeff7f\nCapBnd:\t000001fffffeffff\n", False),
        ("CapEff:\t0000000000000080\n", False),
        ("CapEff:\t0000000000000000\n", False),
        ("CapBnd:\t00000000000000c0\n", False),
        ("CapEff:\t00000000000000c0\n" * 2, False),
        ("CapEff:\t00000000000000cz\n", False),
        ("CapEff:\t00000000000000c0 extra\n", False),
        ("x" * 8193, False),
    ],
)
def test_only_effective_uid_and_gid_switch_capabilities_allow_preparation(
    contents, allowed, monkeypatch
):
    monkeypatch.setattr(worker, "os", SimpleNamespace(name="posix", geteuid=lambda: 0))
    monkeypatch.setattr(
        worker,
        "Path",
        lambda *a: SimpleNamespace(open=lambda *a, **kw: io.StringIO(contents)),
    )
    if allowed:
        worker.require_migration_worker_privileges()
    else:
        with pytest.raises(worker.MigrationWorkerPrivilegesUnavailable):
            worker.require_migration_worker_privileges()


@pytest.mark.parametrize("name, uid", [("nt", 0), ("posix", 1200)])
def test_nonroot_or_unsupported_helper_fails_before_proc_access(name, uid, monkeypatch):
    monkeypatch.setattr(worker, "os", SimpleNamespace(name=name, geteuid=lambda: uid))
    monkeypatch.setattr(
        worker, "Path", lambda *a: pytest.fail("Unexpected proc access")
    )
    with pytest.raises(worker.MigrationWorkerPrivilegesUnavailable):
        worker.require_migration_worker_privileges()


def test_failed_capability_prerequisite_precedes_any_ticket_key_or_namespace(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        installation, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)
    )

    def unavailable():
        raise worker.MigrationWorkerPrivilegesUnavailable("UID switch unavailable")

    def forbidden(*a, **kw):
        pytest.fail("Preparation effect occurred before prerequisite check")

    monkeypatch.setattr(
        installation, "require_migration_worker_privileges", unavailable
    )
    monkeypatch.setattr(installation.secrets, "token_bytes", forbidden)
    monkeypatch.setattr(installation, "_roots", forbidden)
    with pytest.raises(worker.MigrationWorkerPrivilegesUnavailable):
        installation.prepare_fresh_relational_installation(
            tmp_path / "unused.zip",
            configuration={},
            root=tmp_path / "runtime",
            key_root=tmp_path / "keys",
            state_root=tmp_path / "state",
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
            confirm_fresh_owned_namespace=True,
            confirm_owned_business_migrations=True,
            issue_namespace=forbidden,
            issue_migration=forbidden,
            checkpoint=forbidden,
        )
    assert list(tmp_path.iterdir()) == []


def test_failed_capability_prerequisite_precedes_existing_schema_checkpoints(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        preparation, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)
    )

    def unavailable():
        raise worker.MigrationWorkerPrivilegesUnavailable("UID switch unavailable")

    def forbidden(*a, **kw):
        pytest.fail("Preparation reached paths/checkpoints without UID prerequisite")

    monkeypatch.setattr(preparation, "require_migration_worker_privileges", unavailable)
    monkeypatch.setattr(preparation, "_regular", forbidden)
    with pytest.raises(worker.MigrationWorkerPrivilegesUnavailable):
        preparation.prepare_migrated_relational_database(
            tmp_path / "unused.zip",
            {},
            configuration={},
            root=tmp_path / "runtime",
            key_root=tmp_path / "keys",
            state_root=tmp_path / "state",
            service_uid=1200,
            service_gid=1201,
            checkpoint=forbidden,
        )
    assert list(tmp_path.iterdir()) == []


def _directives():
    return dict(
        line.split("=", 1)
        for line in HELPER.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(("#", "["))
    )


LIVE = pytest.mark.skipif(
    os.name != "posix"
    or not hasattr(os, "geteuid")
    or os.geteuid() != 0
    or not Path("/run/systemd/system").is_dir()
    or os.environ.get("THREE_MM_RUN_SYSTEMD_MIGRATION_TESTS") != "1",
    reason="Explicit disposable root/systemd integration run required",
)

PARENT = """
import json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from three_mm_runtime import application_relational_migrations as worker
from three_mm_protocol.application_extension import ApplicationRelationalStorageV1
frame = json.loads(sys.argv[2])
boot, now = worker._clock()
definition = SimpleNamespace(storage=SimpleNamespace(
    migration_entrypoint='systemd_migration_probe.migrations:get_migrations',
    relational=ApplicationRelationalStorageV1.model_validate(frame['declaration'])))
ticket = dict(action='prepare_migrated_schema',
    worker_profile_sha256=worker.migration_worker_profile_digest(),
    boot_id=boot, issued_at_ms=now, deadline_ms=now + 300000,
    package_sha256=frame['package_sha256'], service_sha256=frame['service_sha256'],
    schema_revision='0001')
try:
    worker.run_business_migrations(Path(frame['instance']), ticket, definition,
        database_present=False, service_uid=1200, service_gid=1201)
except worker.MigrationWorkerPrivilegesUnavailable:
    print(json.dumps({'status':'prerequisite_refused', 'database_exists':
        (Path(frame['instance']) / 'data/state.sqlite3').exists()}))
else:
    print(json.dumps({'status':'migrated_as_nonroot'}))
"""

MIGRATION = """
import os
from pathlib import Path
from three_mm_application_sdk import ApplicationMigration
def first(db):
    assert os.getuid() == os.geteuid() == 1200
    assert os.getgid() == os.getegid() == 1201
    assert not os.getgroups()
    fields = dict(line.split(':', 1) for line in
        Path('/proc/self/status').read_text().splitlines() if ':' in line)
    assert int(fields['CapEff'], 16) == int(fields['CapAmb'], 16) == 0
    assert fields['NoNewPrivs'].strip() == '1'
    db.execute('CREATE TABLE proof(uid INTEGER, gid INTEGER, no_new_privileges INTEGER)')
    db.execute('INSERT INTO proof VALUES (?, ?, ?)', (os.getuid(), os.getgid(), 1))
def get_migrations():
    return [ApplicationMigration('0001', first)]
"""


@LIVE
@pytest.mark.parametrize("retain_setuid", [False, True])
def test_actual_helper_hardening_preserves_uid_switch_but_child_has_no_capabilities(
    retain_setuid,
):
    import grp

    try:
        grp.getgrnam("3mm")
    except KeyError:
        pytest.skip(
            "Installer-created helper group is required; test creates no account"
        )
    unit = _directives()
    assert unit["AmbientCapabilities"] == "CAP_SETUID"
    python = Path("/opt/3mm/current/.venv/bin/python")
    if not python.is_file():
        pytest.skip("Installed interpreter outside protected home/private tmp required")
    # PrivateTmp hides BOTH /tmp and /var/tmp, including a temporary test venv.
    # Never use /var/lib/3mm: a fresh sibling is visible to PID 1 but isolated
    # from production. TemporaryDirectory owns and cleans only this exact root.
    with tempfile.TemporaryDirectory(
        prefix="3mm-worker-systemd-test-", dir="/var/lib"
    ) as name:
        root = Path(name)
        root.chmod(0o755)
        instance = root / "instance"
        package_digest = "b" * 64
        release = instance / "releases" / package_digest
        release.mkdir(parents=True)
        data = instance / "data"
        data.mkdir()
        for directory in (instance, instance / "releases", release):
            directory.chmod(0o750)
            os.chown(directory, 0, 1201)
        data.chmod(0o750)
        os.chown(data, 1200, 1201)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as wheel:
            wheel.writestr("systemd_migration_probe/__init__.py", "")
            wheel.writestr("systemd_migration_probe/migrations.py", MIGRATION)
        wheel_path = release / "service.whl"
        wheel_path.write_bytes(stream.getvalue())
        wheel_path.chmod(0o440)
        os.chown(wheel_path, 0, 1201)
        frame = {
            "instance": str(instance),
            "package_sha256": package_digest,
            "service_sha256": hashlib.sha256(stream.getvalue()).hexdigest(),
            "declaration": {
                "contract_version": 1,
                "mode": "read_write",
                "limit_class": "cooperative_v1",
                "max_database_bytes": 1048576,
                "auxiliary_pause_bytes": 262144,
                "max_statement_bytes": 2048,
                "max_value_bytes": 1024,
                "max_result_bytes": 4096,
                "max_result_rows": 16,
                "max_transaction_ms": 5000,
                "max_busy_ms": 500,
            },
        }
        properties = [
            "User",
            "Group",
            "NoNewPrivileges",
            "PrivateTmp",
            "ProtectSystem",
            "ProtectHome",
            "ProtectKernelTunables",
            "ProtectKernelModules",
            "ProtectControlGroups",
            "RestrictSUIDSGID",
            "RestrictAddressFamilies",
            "LockPersonality",
        ]
        arguments = [
            "/usr/bin/systemd-run",
            "--quiet",
            "--pipe",
            "--wait",
            "--collect",
            "--property=Type=exec",
            "--property=RuntimeMaxSec=45s",
            "--property=TimeoutStopSec=5s",
            "--property=KillMode=control-group",
            "--property=ReadWritePaths=" + str(data),
        ]
        arguments.extend("--property=" + key + "=" + unit[key] for key in properties)
        if retain_setuid:
            arguments.append(
                "--property=AmbientCapabilities=" + unit["AmbientCapabilities"]
            )
        arguments.extend(
            [str(python), "-B", "-c", PARENT, str(ROOT), json.dumps(frame)]
        )
        process = subprocess.run(
            arguments, capture_output=True, timeout=55, check=False
        )
        assert process.returncode == 0, process.stderr.decode(errors="replace")
        result = json.loads(process.stdout)
        database = data / "state.sqlite3"
        if not retain_setuid:
            assert result == {
                "status": "prerequisite_refused",
                "database_exists": False,
            }
            assert not database.exists()
        else:
            assert result == {"status": "migrated_as_nonroot"}
            assert database.stat().st_uid == 1200
            with closing(
                sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
            ) as db:
                db.execute("PRAGMA query_only=ON")
                assert db.execute("SELECT * FROM proof").fetchall() == [(1200, 1201, 1)]
                assert db.execute(
                    "SELECT revision FROM three_mm_schema_migrations"
                ).fetchall() == [("0001",)]
