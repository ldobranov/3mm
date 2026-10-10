"""Real POSIX data rollback; no systemd, Core, device or external effects."""

import hashlib
import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from three_mm_application_sdk import ApplicationFileLimits, ApplicationFileStorage
from three_mm_runtime import application_activation as activation
from three_mm_runtime import application_files_snapshot as snapshots
from three_mm_runtime.tests.test_application_activation import (
    EnabledSupervisor,
    ReadyClient,
    Supervisor,
    service_package,
)


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX application runtime")


@pytest.fixture
def installed(tmp_path):
    blob = service_package()
    digest = hashlib.sha256(blob).hexdigest()
    package = tmp_path / "package.zip"
    package.write_bytes(blob)
    options = dict(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        sleep=lambda _: None,
    )
    result = activation.activate_application_package(
        package,
        digest,
        supervisor=Supervisor(),
        client_factory=ReadyClient,
        **options,
    )
    instance = options["root"] / result.instance_id
    data = instance / "data"
    return SimpleNamespace(
        package=package,
        digest=digest,
        options=options,
        instance=instance,
        data=data,
        files=ApplicationFileStorage(data),
        previous=(instance / "active.json").read_bytes(),
    )


def run_candidate(installed, mutation, *, ready=False, supervisor=None):
    class CandidateClient(ReadyClient):
        mutated = False

        def invoke(self, *_args):
            if not self.mutated:
                mutation()
                self.mutated = True
            if not ready:
                # A terminal application failure avoids pointless health retries.
                raise RuntimeError("candidate failed after local mutation")
            return {"status": "ready"}

    return activation.activate_application_package(
        installed.package,
        installed.digest,
        supervisor=supervisor or EnabledSupervisor(),
        client_factory=CandidateClient,
        **installed.options,
    )


def rollbacks(installed):
    return list(installed.instance.glob(".activation-*.rollback"))


@pytest.mark.parametrize("ready", [False, True])
def test_files_and_sqlite_share_the_failed_activation_boundary(installed, ready):
    files = installed.files
    original = files.put("logo", b"previous", expected_sha256=None)
    removed = files.put("removed", b"keep", expected_sha256=None)
    (installed.data / "legacy.txt").write_bytes(b"unrelated native data")
    database = installed.data / "state.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE records(value TEXT)")
        db.execute("INSERT INTO records VALUES ('previous')")

    def mutate():
        assert rollbacks(installed)[0].stat().st_mode & 0o777 == 0o700
        files.put("logo", b"candidate", expected_sha256=original.sha256)
        files.delete("removed", expected_sha256=removed.sha256)
        files.put("added", b"new", expected_sha256=None)
        with sqlite3.connect(database) as db:
            db.execute("UPDATE records SET value = 'candidate'")

    supervisor = EnabledSupervisor()
    if ready:
        run_candidate(installed, mutate, ready=True, supervisor=supervisor)
    else:
        with pytest.raises(
            activation.ApplicationActivationError, match="previous version was restored"
        ):
            run_candidate(installed, mutate, supervisor=supervisor)
    assert files.get("logo").content == (b"candidate" if ready else b"previous")
    assert (files.get("added") is not None) == ready
    assert (files.get("removed") is None) == ready
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT value FROM records").fetchall() == [
            ("candidate" if ready else "previous",)
        ]
    assert (installed.data / "legacy.txt").read_bytes() == b"unrelated native data"
    assert (installed.instance / "active.json").read_bytes() == installed.previous
    assert not rollbacks(installed)
    assert supervisor.calls[-1][0] == "restart"


@pytest.mark.parametrize("namespace_present", [False, True])
def test_empty_or_absent_namespace_is_restored_exactly(installed, namespace_present):
    if namespace_present:
        entry = installed.files.put("temporary", b"x", expected_sha256=None)
        installed.files.delete("temporary", expected_sha256=entry.sha256)
    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(
            installed, lambda: installed.files.put("new", b"x", expected_sha256=None)
        )
    assert (installed.data / "sdk-files").exists() == namespace_present
    assert installed.files.list_entries() == []
    assert not rollbacks(installed)


def test_failed_first_activation_removes_only_candidate_sdk_namespace(tmp_path):
    blob = service_package()
    digest = hashlib.sha256(blob).hexdigest()
    package = tmp_path / "package.zip"
    package.write_bytes(blob)
    instance = (
        tmp_path
        / "apps"
        / activation.application_instance_id("org.3mm.workflow-reference")
    )

    class Client(ReadyClient):
        def invoke(self, *_args):
            ApplicationFileStorage(instance / "data").put(
                "first", b"candidate", expected_sha256=None
            )
            raise RuntimeError("failed first install")

    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        activation.activate_application_package(
            package,
            digest,
            root=tmp_path / "apps",
            key_root=tmp_path / "keys",
            supervisor=Supervisor(),
            client_factory=Client,
        )
    assert not (instance / "active.json").exists()
    assert not (instance / "data/sdk-files").exists()
    assert not list(instance.glob(".activation-*.rollback"))


def test_disabled_previous_installation_is_quiesced_and_not_reenabled(installed):
    supervisor = Supervisor()
    installed.files.put("previous", b"x", expected_sha256=None)
    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(installed, lambda: None, supervisor=supervisor)
    assert [call[0] for call in supervisor.calls] == [
        "is_enabled",
        "stop",
        "restart",
        "stop",
    ]
    assert installed.files.get("previous").content == b"x"


def test_metadata_write_failure_enters_rollback_before_any_candidate_start(
    installed, monkeypatch
):
    installed.files.put("previous", b"x", expected_sha256=None)
    real_write = activation._write_atomic
    failed = False

    def write(path, *args):
        nonlocal failed
        if path.name == "active.json" and not failed:
            failed = True
            raise OSError("metadata write failure")
        return real_write(path, *args)

    monkeypatch.setattr(activation, "_write_atomic", write)
    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(
            installed, lambda: pytest.fail("candidate started"), supervisor=supervisor
        )
    assert [call[0] for call in supervisor.calls] == [
        "is_enabled",
        "stop",
        "stop",
        "restart",
    ]
    assert (installed.instance / "active.json").read_bytes() == installed.previous
    assert installed.files.get("previous").content == b"x"


@pytest.mark.parametrize("failed_stop", [1, 2])
def test_unconfirmed_stop_never_restores_or_restarts_and_preserves_evidence(
    installed, failed_stop
):
    original = installed.files.put("logo", b"previous", expected_sha256=None)

    class FailingSupervisor(EnabledSupervisor):
        stops = 0

        def stop(self, instance_id):
            super().stop(instance_id)
            self.stops += 1
            if self.stops == failed_stop:
                raise RuntimeError("stop unconfirmed")

    supervisor = FailingSupervisor()
    with pytest.raises(activation.ApplicationActivationError, match="unconfirmed"):
        run_candidate(
            installed,
            lambda: installed.files.put(
                "logo", b"candidate", expected_sha256=original.sha256
            ),
            supervisor=supervisor,
        )
    assert installed.files.get("logo").content == (
        b"previous" if failed_stop == 1 else b"candidate"
    )
    assert len(rollbacks(installed)) == 1
    assert supervisor.calls[-1][0] == "stop"
    assert sum(call[0] == "restart" for call in supervisor.calls) == failed_stop - 1


@pytest.mark.parametrize("failure", ["files", "database", "missing_database"])
def test_failed_restore_keeps_preimages_and_blocks_next_lifecycle(
    installed, monkeypatch, failure
):
    original = installed.files.put("logo", b"previous", expected_sha256=None)
    database = installed.data / "state.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE records(value TEXT)")
        db.execute("INSERT INTO records VALUES ('previous')")

    def mutate():
        installed.files.put("logo", b"candidate", expected_sha256=original.sha256)
        if failure == "missing_database":
            (rollbacks(installed)[0] / "state.sqlite3").unlink()

    def fail(*_args):
        raise OSError("restore failure")

    if failure != "missing_database":
        monkeypatch.setattr(
            activation,
            "restore_private_files" if failure == "files" else "_restore_database",
            fail,
        )
    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="rollback is unconfirmed"
    ):
        run_candidate(installed, mutate, supervisor=supervisor)
    snapshot = rollbacks(installed)[0]
    assert (snapshot / "sdk-files/blob_logo").read_bytes() == b"previous"
    assert (snapshot / "previous-active.json").read_bytes() == installed.previous
    assert (
        json.loads((snapshot / "activation.json").read_text())["database_present"]
        is True
    )
    assert supervisor.calls[-1][0] == "stop"
    assert sum(call[0] == "restart" for call in supervisor.calls) == 1
    for action in (
        lambda: run_candidate(installed, lambda: pytest.fail("replayed activation")),
        lambda: activation.uninstall_application_instance(
            installed.instance.name,
            **{k: v for k, v in installed.options.items() if k != "sleep"},
            supervisor=Supervisor(),
        ),
        lambda: activation.erase_application_instance_data(
            installed.instance.name,
            root=installed.options["root"],
            supervisor=Supervisor(),
        ),
    ):
        with pytest.raises(
            activation.ApplicationActivationError, match="unfinished rollback"
        ):
            action()
    assert snapshot.is_dir()


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "pending"])
def test_unsafe_source_files_fail_before_candidate_and_leave_foreign_data_untouched(
    installed, tmp_path, unsafe
):
    entry = installed.files.put("logo", b"previous", expected_sha256=None)
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"foreign data")
    namespace = installed.data / "sdk-files"
    if unsafe == "symlink":
        (namespace / "blob_unsafe").symlink_to(foreign)
    elif unsafe == "hardlink":
        os.link(foreign, namespace / "blob_unsafe")
    else:
        (namespace / ".pending_crash").write_bytes(b"uncertain write")
    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="could not be staged"
    ):
        run_candidate(
            installed,
            lambda: pytest.fail("unsafe snapshot started candidate"),
            supervisor=supervisor,
        )
    assert installed.files.get("logo").sha256 == entry.sha256
    assert foreign.read_bytes() == b"foreign data"
    assert supervisor.calls[-1][0] == "stop"
    assert len(rollbacks(installed)) == 1


def test_corrupt_snapshot_is_rejected_before_live_namespace_switch(installed):
    original = installed.files.put("logo", b"previous", expected_sha256=None)

    def mutate():
        installed.files.put("logo", b"candidate", expected_sha256=original.sha256)
        (rollbacks(installed)[0] / "sdk-files/blob_logo").write_bytes(b"tampered")

    with pytest.raises(
        activation.ApplicationActivationError, match="rollback is unconfirmed"
    ):
        run_candidate(installed, mutate)
    assert installed.files.get("logo").content == b"candidate"
    assert not (rollbacks(installed)[0] / "candidate-sdk-files").exists()


def test_snapshot_accepts_explicit_sdk_limits_above_the_default(installed):
    files = ApplicationFileStorage(
        installed.data, limits=ApplicationFileLimits(2 * 1024 * 1024)
    )
    original = files.put("large", b"x" * (1024 * 1024 + 1), expected_sha256=None)
    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(
            installed, lambda: files.delete("large", expected_sha256=original.sha256)
        )
    assert files.get("large") == original
    assert (installed.data / "sdk-files").stat().st_mode & 0o777 == 0o700
    assert (installed.data / "sdk-files/blob_large").stat().st_mode & 0o777 == 0o600


def test_candidate_namespace_symlink_never_touches_its_target(installed, tmp_path):
    installed.files.put("logo", b"previous", expected_sha256=None)
    foreign = tmp_path / "foreign-directory"
    foreign.mkdir()
    (foreign / "keep").write_bytes(b"foreign data")

    def mutate():
        namespace = installed.data / "sdk-files"
        namespace.rename(installed.data / "native-candidate-copy")
        namespace.symlink_to(foreign, target_is_directory=True)

    with pytest.raises(
        activation.ApplicationActivationError, match="previous version was restored"
    ):
        run_candidate(installed, mutate)
    assert installed.files.get("logo").content == b"previous"
    assert (foreign / "keep").read_bytes() == b"foreign data"
    # Arbitrary native data outside sdk-files is deliberately not rolled back.
    assert (
        installed.data / "native-candidate-copy/blob_logo"
    ).read_bytes() == b"previous"


def test_busy_sdk_writer_blocks_snapshot_before_candidate(installed):
    installed.files.put("logo", b"previous", expected_sha256=None)
    with installed.files._locked(write=True):
        with pytest.raises(
            activation.ApplicationActivationError, match="could not be staged"
        ):
            run_candidate(installed, lambda: pytest.fail("writer was not quiescent"))
    assert installed.files.get("logo").content == b"previous"
    assert len(rollbacks(installed)) == 1


@pytest.mark.parametrize(
    "damage", ["missing", "wrong_schema", "traversal", "duplicate", "digest"]
)
def test_invalid_snapshot_manifest_leaves_candidate_untouched(installed, damage):
    original = installed.files.put("logo", b"previous", expected_sha256=None)

    def mutate():
        installed.files.put("logo", b"candidate", expected_sha256=original.sha256)
        manifest_path = rollbacks(installed)[0] / "files.json"
        manifest = json.loads(manifest_path.read_text())
        if damage == "missing":
            manifest_path.unlink()
            return
        if damage == "wrong_schema":
            manifest["schema_version"] = True
        elif damage == "traversal":
            manifest["files"][0]["file_id"] = "../../other"
        elif damage == "duplicate":
            manifest["files"] *= 2
        else:
            manifest["files"][0]["sha256"] = "unknown"
        manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(
        activation.ApplicationActivationError, match="rollback is unconfirmed"
    ):
        run_candidate(installed, mutate)
    assert installed.files.get("logo").content == b"candidate"
    assert not (rollbacks(installed)[0] / "candidate-sdk-files").exists()


def test_uninstall_preserves_sdk_files_without_snapshot_artifacts(installed):
    installed.files.put("logo", b"retained", expected_sha256=None)
    activation.uninstall_application_instance(
        installed.instance.name,
        root=installed.options["root"],
        key_root=installed.options["key_root"],
        supervisor=Supervisor(),
    )
    assert installed.files.get("logo").content == b"retained"
    assert not (installed.instance / "active.json").exists()


def test_legacy_or_interrupted_snapshot_is_not_overwritten(installed):
    marker = installed.instance / (".database-" + "a" * 64 + ".rollback")
    marker.write_bytes(b"keep for explicit recovery")
    with pytest.raises(
        activation.ApplicationActivationError, match="unfinished rollback"
    ):
        run_candidate(installed, lambda: pytest.fail("overwrote uncertain recovery"))
    assert marker.read_bytes() == b"keep for explicit recovery"


def test_production_stop_uses_positive_systemd_evidence(monkeypatch):
    calls = []

    def run(command, **kwargs):
        assert kwargs["check"] is True
        calls.append(command)
        return SimpleNamespace(
            stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nUnitFileState=disabled\nMainPID=0\nJob=\n"
        )

    monkeypatch.setattr(activation.subprocess, "run", run)
    activation._stop_for_data(activation.SystemdApplicationSupervisor(), "a" * 24)
    assert [command[1] for command in calls] == ["disable", "show"]


def test_restore_mid_switch_failure_keeps_original_and_candidate(
    installed, monkeypatch
):
    original = installed.files.put("logo", b"previous", expected_sha256=None)
    real_rename = snapshots.os.rename

    def rename(source, destination, **kwargs):
        if source == "restored-sdk-files":
            raise OSError("switch failure after candidate was detached")
        return real_rename(source, destination, **kwargs)

    # Fault injection replaces a supported function; retain the real POSIX checks
    # for normal tests rather than changing production's capability detection.
    monkeypatch.setattr(
        ApplicationFileStorage, "_supported", staticmethod(lambda: None)
    )
    monkeypatch.setattr(snapshots.os, "rename", rename)
    supervisor = EnabledSupervisor()
    with pytest.raises(
        activation.ApplicationActivationError, match="rollback is unconfirmed"
    ):
        run_candidate(
            installed,
            lambda: installed.files.put(
                "logo", b"candidate", expected_sha256=original.sha256
            ),
            supervisor=supervisor,
        )
    snapshot = rollbacks(installed)[0]
    assert (snapshot / "sdk-files/blob_logo").read_bytes() == b"previous"
    assert (snapshot / "candidate-sdk-files/blob_logo").read_bytes() == b"candidate"
    assert (snapshot / "restored-sdk-files/blob_logo").read_bytes() == b"previous"
    assert not (installed.data / "sdk-files").exists()
    assert supervisor.calls[-1][0] == "stop"


@pytest.mark.parametrize("ready", [False, True])
def test_cleanup_failure_keeps_phase_evidence_and_stops_runtime(
    installed, monkeypatch, ready
):
    original = installed.files.put("logo", b"previous", expected_sha256=None)

    def fail_cleanup(_path):
        raise OSError("cleanup could not complete")

    monkeypatch.setattr(activation.shutil, "rmtree", fail_cleanup)
    supervisor = EnabledSupervisor()
    with pytest.raises(activation.ApplicationActivationError, match="runtime stopped"):
        run_candidate(
            installed,
            lambda: installed.files.put(
                "logo", b"candidate", expected_sha256=original.sha256
            ),
            ready=ready,
            supervisor=supervisor,
        )
    assert installed.files.get("logo").content == (
        b"candidate" if ready else b"previous"
    )
    record = json.loads((rollbacks(installed)[0] / "activation.json").read_text())
    assert record["phase"] == ("healthy" if ready else "restored")
    assert supervisor.calls[-1][0] == "stop"
