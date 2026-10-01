"""Detached worker durability and installer outcomes using only local fakes."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from deployment import apply_node_update as module
from three_mm_protocol.node_updates import NodeUpdateApplyRequest, NodeUpdateOperation
from three_mm_runtime.node_update_helper import NodeUpdateStore, request_digest


class CurrentRelease:
    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return str(self.path)


@pytest.fixture
def installation(tmp_path):
    store = NodeUpdateStore(tmp_path / "state", enforce_permissions=False)
    created = datetime.now(UTC)
    request = NodeUpdateApplyRequest(operation_id="nodeupd_" + "1" * 32,
        device_id="dev_" + "a" * 32, release_id="v1.2.0", archive_sha256="b" * 64,
        confirmed_install=True, created_at=created, expires_at=created + timedelta(seconds=120))
    old, new = tmp_path / "releases/v1.1.0", tmp_path / "releases/v1.2.0"
    metadata = {}
    for path in (old, new):
        (path / "deployment").mkdir(parents=True)
        metadata[path] = {"release_id": path.name, "version": path.name[1:], "profile": "node"}
        (path / ".3mm-release.json").write_text(json.dumps(metadata[path]))
        (path / ".3mm-install-profile").write_text("node\n")
        (path / "VERSION").write_text(path.name[1:] + "\n")
        (path / "deployment/install-systemd.sh").write_text("fixture")
    agent = tmp_path / "agent"
    agent.mkdir()
    for name, value in {"identity.json": {"device_id": request.device_id},
                        "core-credential.json": {"token": "secret"},
                        "gpio-configuration.json": {"revision": 2}}.items():
        (agent / name).write_text(json.dumps(value))
    operation = NodeUpdateOperation(operation_id=request.operation_id, device_id=request.device_id,
        release_id=request.release_id, archive_sha256=request.archive_sha256,
        status="accepted", updated_at=created)
    store.write({"request": request, "operation": operation, "digest": request_digest(request)})
    archive = tmp_path / "prepared.tar.gz"
    archive.write_bytes(b"already validated")
    current = CurrentRelease(old)
    arguments = dict(store=store, current_root=current, agent_data=agent,
        validator=lambda _: (archive, metadata[new]), health_checker=lambda _: True,
        helper_checker=lambda _: True)
    return store, request, current, old, new, agent, archive, arguments


def test_running_before_mutation_and_success_requires_installer_current_health(installation):
    store, request, current, old, new, agent, archive, arguments = installation
    before = module.snapshot_agent_state(agent)
    calls = []

    def installer(argv):
        # A separately constructed store sees the handover on disk, not memory.
        independent = NodeUpdateStore(store.root, enforce_permissions=False)
        with independent.locked():
            assert independent.read(request.operation_id)["operation"].status == "running"
        calls.append(argv)
        current.path = new
        archive.unlink()  # The real installer removes its input archive.
        return 0

    assert module.apply_node_update(request.operation_id, runner=installer, **arguments) == 0
    operation = store.read(request.operation_id)["operation"]
    assert operation.status == "succeeded" and operation.previous_release_id == "v1.1.0"
    assert module.snapshot_agent_state(agent) == before
    assert calls == [["/usr/bin/bash", str(old / "deployment/install-systemd.sh"),
        str(archive), "v1.2.0", "http://localhost", "", request.archive_sha256, "node"]]
    assert module.apply_node_update(request.operation_id,
        runner=lambda _: pytest.fail("terminal operation reexecuted"), **arguments) == 0


def test_installer_failure_is_rollback_only_when_previous_release_is_healthy(installation):
    store, request, _, _, _, _, _, arguments = installation
    assert module.apply_node_update(request.operation_id, runner=lambda _: 1, **arguments) == 1
    operation = store.read(request.operation_id)["operation"]
    assert operation.status == "rolled_back" and operation.error_code == "installer_failed"
    assert module.apply_node_update(request.operation_id,
        runner=lambda _: pytest.fail("rollback automatically retried"), **arguments) == 1


@pytest.mark.parametrize("failure", ["health", "helper", "metadata", "marker", "version", "identity"])
def test_zero_exit_is_not_success_without_independent_postflight(installation, failure):
    store, request, current, _, new, agent, _, arguments = installation

    def installer(_):
        current.path = new
        if failure == "metadata":
            (new / ".3mm-release.json").write_text('{"release_id":"v9.0.0","version":"9.0.0"}')
        elif failure == "marker":
            (new / ".3mm-install-profile").write_text("full")
        elif failure == "version":
            (new / "VERSION").write_text("9.0.0")
        elif failure == "identity":
            (agent / "identity.json").write_text('{"device_id":"changed"}')
        return 0

    arguments["health_checker"] = lambda _: failure != "health"
    arguments["helper_checker"] = lambda _: failure != "helper"
    assert module.apply_node_update(request.operation_id, runner=installer, **arguments) == 1
    assert store.read(request.operation_id)["operation"].status == "unknown"


def test_expiry_between_preflight_and_installer_does_not_mutate(installation, monkeypatch):
    store, request, _, _, _, _, _, arguments = installation

    class Clock:
        @staticmethod
        def now(_):
            return request.expires_at

    monkeypatch.setattr(module, "datetime", Clock)
    assert module.apply_node_update(request.operation_id,
        runner=lambda _: pytest.fail("expired request mutated"), **arguments) == 1
    operation = store.read(request.operation_id)["operation"]
    assert operation.status == "failed" and operation.error_code == "expired"


def test_preflight_failure_and_crash_leave_durable_nonretriable_outcomes(installation):
    store, request, _, _, _, _, _, arguments = installation
    original = arguments["validator"]
    arguments["validator"] = lambda _: (_ for _ in ()).throw(ValueError("bad staged archive"))
    assert module.apply_node_update(request.operation_id,
        runner=lambda _: pytest.fail("failed preflight mutated"), **arguments) == 1
    assert store.read(request.operation_id)["operation"].status == "failed"
    # Root-controlled test resets acceptance to simulate a separate accepted run.
    store.transition(store.read(request.operation_id), "accepted")
    arguments["validator"] = original

    def crash(_):
        raise SystemExit("worker power loss")

    with pytest.raises(SystemExit):
        module.apply_node_update(request.operation_id, runner=crash, **arguments)
    assert store.read(request.operation_id)["operation"].status == "running"
    assert module.apply_node_update(request.operation_id,
        runner=lambda _: pytest.fail("running operation reexecuted after restart"), **arguments) == 1


def test_installer_timeout_is_owned_by_transient_cgroup_not_bash_parent(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.run_installer(["fixed", "argv"]) == 0
    assert "timeout" not in captured
    assert captured["env"] == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def test_helper_readiness_uses_fixed_socket_and_correlates_running_operation(monkeypatch):
    operation_id = "nodeupd_" + "1" * 32
    replies = iter([
        {"ok": True, "operation": {"operation_id": "nodeupd_" + "2" * 32, "status": "running"}},
        {"ok": True, "operation": {"operation_id": operation_id, "status": "accepted"}},
        {"ok": True, "operation": {"operation_id": operation_id, "status": "running"}},
    ])
    calls = []

    class FakeSocket:
        def __enter__(self):
            self.response = json.dumps(next(replies)).encode() + b"\n"
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, timeout):
            assert timeout == 1

        def connect(self, path):
            assert path == str(module.SOCKET_PATH)

        def sendall(self, message):
            calls.append(message)

        def recv(self, count):
            assert count == 1024
            return self.response

    monkeypatch.setattr(module.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(module.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    assert module.check_helper(operation_id) is True
    assert calls == [b'{"action":"status"}\n'] * 3
