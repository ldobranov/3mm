"""Closed local peer/frame/client/CLI contract; never invokes live systemd."""

import argparse
import socket
from pathlib import Path

import pytest

from backend.services.application_relational_upgrade_cli import COMMANDS, add_commands
from three_mm_application_sdk.relational_wire import canonical, sign_metadata
from three_mm_runtime import application_relational_upgrade_control as control
from three_mm_runtime import update_helper
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError


def request(action):
    return {
        "action": action,
        "installation_id": 1,
        "actor_token": "test-only-token",
        "source_action_id": "c" * 32,
        "expected_source_revision": "d" * 32,
        "expected_grant_record_revision": "e" * 32,
        "request_id": "b" * 32,
        control.OPERATIONS[action][1]: True,
    }


@pytest.mark.parametrize("action", sorted(control.ACTIONS))
@pytest.mark.parametrize(
    "change", ["extra_path", "bool_id", "no_consent", "source", "token", "request"]
)
def test_request_is_closed_and_requires_explicit_consent(action, change):
    value = request(action)
    if change == "extra_path":
        value["root"] = "/tmp/caller-path"
    elif change == "bool_id":
        value["installation_id"] = True
    elif change == "no_consent":
        value[control.OPERATIONS[action][1]] = 1
    else:
        value[
            {
                "source": "source_action_id",
                "token": "actor_token",
                "request": "request_id",
            }[change]
        ] = ""
    with pytest.raises(ValueError):
        control.upgrade_request(value)


def handle(tmp_path, value, peer):
    return update_helper._handle_request(
        value,
        relational_peer_uid=peer,
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist",
        status_file=tmp_path / "status",
    )


@pytest.mark.parametrize("action", sorted(control.ACTIONS))
@pytest.mark.parametrize("peer", [None, 0, 1200, True])
def test_only_core_peer_reaches_upgrade(tmp_path, monkeypatch, action, peer):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *a: (1202, 1203))
    monkeypatch.setattr(
        control, "installed_upgrade", lambda *a, **kw: pytest.fail("Wrong peer")
    )
    assert handle(tmp_path, request(action), peer) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("action", sorted(control.ACTIONS))
def test_fixed_wiring_and_no_sensitive_error_logs(
    tmp_path, monkeypatch, caplog, action
):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *a: (1202, 1203))

    def execute(value, **kw):
        assert kw["root"] == Path("/var/lib/3mm/application-extensions")
        assert kw["coordinator_uid"] == 1202
        raise ValueError("sensitive test-only-token transport-secret")

    monkeypatch.setattr(control, "installed_upgrade", execute)
    assert handle(tmp_path, request(action), 1202) == {
        "ok": False,
        "error": "relational_upgrade_unconfirmed",
    }
    assert (
        "test-only-token" not in caplog.text and "transport-secret" not in caplog.text
    )


@pytest.mark.parametrize("action", sorted(control.ACTIONS))
@pytest.mark.parametrize(
    "problem", ["lost_reply", "wrong_id", "wrong_source", "extra", "model"]
)
def test_client_never_retries_or_accepts_wrong_completion(monkeypatch, action, problem):
    payload = request(action)
    value = {
        "version": 1,
        "preparation_id": payload["request_id"],
        "lifecycle_sha256": "a" * 64,
        "outcome": control.response_status(action),
    }
    if control.OPERATIONS[action][0] in {"restore", "rollback"}:
        value.update(
            source_upgrade_id=payload["source_action_id"],
            rollback_proof_sha256="f" * 64,
        )
    receipt = sign_metadata(b"t" * 32, "database_upgrade_rollback_result", value)
    response = {"ok": True, "status": value["outcome"], "upgrade": receipt}
    if problem == "wrong_id":
        receipt["preparation_id"] = "d" * 32
    elif problem == "wrong_source":
        receipt["source_upgrade_id"] = "d" * 32
    elif problem == "extra":
        response["secret"] = "bad"
    elif problem == "model":
        receipt["outcome"] = "active_review_required"
    calls = []

    def send(self, payload, **kw):
        calls.append(payload)
        if problem == "lost_reply":
            raise UpdateHelperError("Lost reply")
        return response

    monkeypatch.setattr(UpdateHelperClient, "_request", send)
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        UpdateHelperClient(Path("unused")).application_relational_upgrade(payload)
    assert len(calls) == 1


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_cli_requires_separate_correct_consent(command):
    parser = argparse.ArgumentParser()
    add_commands(parser.add_subparsers(dest="command", required=True))
    arguments = [
        command,
        "--installation-id",
        "1",
        "--source-action-id",
        "c" * 32,
        "--expected-source-revision",
        "d" * 32,
        "--expected-grant-record-revision",
        "e" * 32,
        "--request-id",
        "b" * 32,
    ]
    with pytest.raises(SystemExit):
        parser.parse_args(arguments)
    consent = control.OPERATIONS[COMMANDS[command]][1]
    assert getattr(
        parser.parse_args(arguments + ["--" + consent.replace("_", "-")]), consent
    )
    with pytest.raises(SystemExit):
        parser.parse_args(
            arguments + ["--" + consent.replace("_", "-"), "--actor-token", "forbidden"]
        )


@pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"), reason="Linux kernel peer credentials"
)
@pytest.mark.parametrize("action", sorted(control.ACTIONS))
def test_socket_uses_kernel_peer_uid(monkeypatch, action):
    import os

    peer, server = socket.socketpair()
    seen = []

    def record(value, **kw):
        seen.append(kw["relational_peer_uid"])
        return {"ok": False, "error": "test_only"}

    monkeypatch.setattr(update_helper, "_handle_request", record)
    try:
        peer.sendall(canonical(request(action)) + b"\n")
        update_helper._serve_connection(server)
        assert seen == [os.getuid()]
        assert peer.recv(4096).endswith(b"\n")
    finally:
        peer.close()
        server.close()
