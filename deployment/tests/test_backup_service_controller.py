"""Exact backup pause/resume, including systemd's unloaded-instance behavior."""

import subprocess

import pytest

from deployment.create_backup import RUNTIME_SERVICES, SystemdServiceController, create_backup


APP = "3mm-application-extension@" + "a" * 24 + ".service"
STOPPED = "3mm-application-extension@" + "b" * 24 + ".service"
BASE = RUNTIME_SERVICES[:2]


def systemd(monkeypatch, listing="", *, query_fails=False, stop_fails=False,
            start_fails=False, inactive_after_start=None):
    calls = []
    active = {*BASE, APP} if APP in listing else set(BASE)

    def run(command, **kwargs):
        calls.append(command)
        action = command[1]
        if action == "list-units":
            if query_fails:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout=listing)
        if action == "stop":
            if stop_fails:
                raise subprocess.CalledProcessError(1, command)
            # After stop, inactive instances are unloaded. A subsequent wildcard
            # start cannot rediscover them, even though the API DB says active.
            active.clear()
        elif action == "start":
            if start_fails:
                raise subprocess.CalledProcessError(1, command)
            active.update(name for name in command[2:] if "*" not in name)
            active.discard(inactive_after_start)
        elif action == "is-active":
            if any(name not in active for name in command[2:]):
                raise subprocess.CalledProcessError(3, command)
        else:
            raise AssertionError(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("deployment.create_backup.subprocess.run", run)
    return calls, active


def test_backup_resumes_exact_instances_after_systemd_unloads_them(monkeypatch):
    calls, active = systemd(monkeypatch, f"{APP} loaded active running Test app\n")
    controller = SystemdServiceController()
    controller.stop(RUNTIME_SERVICES)
    controller.start(RUNTIME_SERVICES)
    assert active == {*BASE, APP}
    assert [call for call in calls if call[1] == "start"] == [
        ["/usr/bin/systemctl", "start", *BASE, APP]]


@pytest.mark.parametrize("state,substate", [("inactive", "dead"), ("failed", "failed"),
                                            ("deactivating", "stop-sigterm")])
def test_previously_stopped_or_stopping_apps_are_not_started(monkeypatch, state, substate):
    calls, active = systemd(monkeypatch,
        f"{APP} loaded active running Active\n{STOPPED} loaded {state} {substate} Stopped\n")
    controller = SystemdServiceController()
    controller.stop(RUNTIME_SERVICES)
    controller.start(RUNTIME_SERVICES)
    assert STOPPED not in active
    assert all(STOPPED not in call[2:] for call in calls if call[1] == "start")


@pytest.mark.parametrize("state", ["activating", "reloading"])
def test_running_transition_is_remembered(monkeypatch, state):
    _, active = systemd(monkeypatch, f"{APP} loaded {state} start Test\n")
    controller = SystemdServiceController()
    controller.stop(RUNTIME_SERVICES)
    controller.start(RUNTIME_SERVICES)
    assert APP in active


def test_no_apps_still_resumes_core_and_agent(monkeypatch):
    _, active = systemd(monkeypatch)
    controller = SystemdServiceController()
    controller.stop(RUNTIME_SERVICES)
    controller.start(RUNTIME_SERVICES)
    assert active == set(BASE)


@pytest.mark.parametrize("listing", ["bad row", "unrelated.service loaded active running Other\n"])
def test_invalid_listing_refuses_before_stopping_any_service(monkeypatch, listing):
    calls, _ = systemd(monkeypatch, listing)
    with pytest.raises(ValueError):
        SystemdServiceController().stop(RUNTIME_SERVICES)
    assert not any(call[1] == "stop" for call in calls)


def test_query_failure_refuses_before_stopping_any_service(monkeypatch):
    calls, _ = systemd(monkeypatch, query_fails=True)
    with pytest.raises(subprocess.CalledProcessError):
        SystemdServiceController().stop(RUNTIME_SERVICES)
    assert not any(call[1] == "stop" for call in calls)


@pytest.mark.parametrize("failure", ["start", "inactive"])
def test_resume_failure_is_propagated(monkeypatch, failure):
    systemd(monkeypatch, f"{APP} loaded active running Test\n",
            start_fails=failure == "start", inactive_after_start=APP if failure == "inactive" else None)
    controller = SystemdServiceController()
    controller.stop(RUNTIME_SERVICES)
    with pytest.raises(subprocess.CalledProcessError):
        controller.start(RUNTIME_SERVICES)


def test_resume_without_successful_stop_is_refused(monkeypatch):
    calls, _ = systemd(monkeypatch, stop_fails=True)
    controller = SystemdServiceController()
    with pytest.raises(subprocess.CalledProcessError):
        controller.stop(RUNTIME_SERVICES)
    with pytest.raises(ValueError):
        controller.start(RUNTIME_SERVICES)
    assert not any(call[1] == "start" for call in calls)


def test_real_backup_status_reports_application_resume_failure(tmp_path, monkeypatch):
    from backend.services.backups import read_backup_operation_status
    from backend.tests.test_backup_preview import _settings

    systemd(monkeypatch, f"{APP} loaded active running Test\n", inactive_after_start=APP)
    settings = _settings(tmp_path)
    with pytest.raises(subprocess.CalledProcessError):
        create_backup(settings, key_file=tmp_path / "backup.key", requested_by_user_id=7)
    status = read_backup_operation_status(settings.backups.storage_dir / "status.json")
    assert status.state == "failed"
    assert status.error_code == "service_restart_failed"


def test_archive_failure_still_resumes_the_exact_application(tmp_path, monkeypatch):
    from backend.tests.test_backup_preview import _settings

    _, active = systemd(monkeypatch, f"{APP} loaded active running Test\n")
    def fail_archive(*args):
        raise ValueError("injected archive failure")
    monkeypatch.setattr("deployment.create_backup._write_archive", fail_archive)
    with pytest.raises(ValueError, match="injected archive failure"):
        create_backup(_settings(tmp_path), key_file=tmp_path / "backup.key", requested_by_user_id=7)
    assert active == {*BASE, APP}
