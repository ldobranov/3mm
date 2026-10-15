"""Closed local request/peer/reply dialect; no filesystem or production effects."""

import socket
from pathlib import Path

import pytest

import three_mm_runtime.application_relational_preparation_recovery_control as control
from three_mm_application_sdk.relational_wire import canonical, sign_metadata
from three_mm_runtime import update_helper
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError


def request(resume=False):
    value = {
        "action": (
            "resume_application_relational_preparation"
            if resume
            else "recover_application_relational_preparation"
        ),
        "installation_id": 1,
        "actor_token": "test-only-human-token",
        "expected_grant_record_revision": "a" * 32,
        "request_id": "b" * 32,
    }
    if resume:
        value.update(
            source_recovery_id="c" * 32,
            expected_recovery_revision="d" * 32,
            confirm_owned_business_migrations=True,
        )
    else:
        value.update(
            source_preparation_id="c" * 32,
            source_namespace_id="d" * 32,
            expected_preparation_revision="e" * 32,
            confirm_restored_empty_checkpoint=True,
        )
    return value


def handle(tmp_path, value, peer):
    return update_helper._handle_request(
        value,
        stage_root=tmp_path / "stage",
        state_root=tmp_path / "state",
        allowlist=tmp_path / "allowlist",
        status_file=tmp_path / "status",
        relational_peer_uid=peer,
    )


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("peer", [None, 0, 1200, True])
def test_only_exact_core_peer_can_reach_recovery(tmp_path, monkeypatch, peer, resume):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *a: (1202, 1203))
    monkeypatch.setattr(
        control,
        "recover_installed_preparation",
        lambda *a, **kw: pytest.fail("wrong peer reached Root effects"),
    )
    assert handle(tmp_path, request(resume), peer) == {
        "ok": False,
        "error": "invalid_request",
    }
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("resume", [False, True])
def test_core_peer_uses_only_fixed_dependency_wiring(tmp_path, monkeypatch, resume):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *a: (1202, 1203))
    result = {"test-only": "no effects"}

    def run(value, **kw):
        assert kw["root"] == Path("/var/lib/3mm/application-extensions")
        assert kw["coordinator_uid"] == 1202
        assert "actor_token" not in kw
        return result

    monkeypatch.setattr(control, "recover_installed_preparation", run)
    response = handle(tmp_path, request(resume), 1202)
    assert response == {
        "ok": True,
        "status": "prepared_not_started" if resume else "restored_empty_not_started",
        "preparation" if resume else "recovery": result,
    }


@pytest.mark.parametrize("resume", [False, True])
def test_helper_never_leaks_token_or_exception(tmp_path, monkeypatch, caplog, resume):
    monkeypatch.setattr(update_helper, "_service_ids", lambda *a: (1202, 1203))

    def failed(*a, **kw):
        raise ValueError("sensitive test-only-human-token secret")

    monkeypatch.setattr(control, "recover_installed_preparation", failed)
    result = handle(tmp_path, request(resume), 1202)
    assert result == {"ok": False, "error": "relational_empty_preparation_unconfirmed"}
    assert "test-only-human-token" not in caplog.text and "sensitive" not in caplog.text


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize(
    "problem", ["wrong_id", "extra", "status", "model", "lost_reply"]
)
def test_unconfirmed_client_reply_never_retries(monkeypatch, resume, problem):
    calls = []
    payload = request(resume)
    receipt = sign_metadata(
        b"t" * 32,
        "preparation_result" if resume else "empty_preparation_recovery_result",
        {
            "version": 1,
            "preparation_id": payload["request_id"],
            "lifecycle_sha256" if resume else "ticket_sha256": "a" * 64,
            "outcome": (
                "prepared_not_started" if resume else "restored_empty_not_started"
            ),
        },
    )
    response = {
        "ok": True,
        "status": receipt["outcome"],
        "preparation" if resume else "recovery": receipt,
    }
    if problem == "wrong_id":
        receipt["preparation_id"] = "c" * 32
    elif problem == "extra":
        response["secret"] = "bad"
    elif problem == "status":
        response["status"] = "active"
    elif problem == "model":
        receipt["outcome"] = "active_review_required"

    def send(self, value, **kw):
        calls.append(value)
        if problem == "lost_reply":
            raise UpdateHelperError("lost reply")
        # _request's own expected-status gate is deliberately still tested here.
        if response["status"] != kw["expected_status"]:
            raise UpdateHelperError("wrong status")
        return response

    monkeypatch.setattr(UpdateHelperClient, "_request", send)
    with pytest.raises(UpdateHelperError, match="Do not retry"):
        UpdateHelperClient(Path("unused")).reconcile_relational_preparation(payload)
    assert len(calls) == 1


def test_new_purpose_is_domain_separated_from_existing_sql_and_namespace_authority():
    value = {"test": "metadata"}
    purposes = (
        "empty_preparation_recovery",
        "empty_preparation_recovery_result",
        "migration_preparation",
        "admission",
        "namespace_recovery",
    )
    assert len(
        {sign_metadata(b"t" * 32, purpose, value)["signature"] for purpose in purposes}
    ) == len(purposes)


@pytest.mark.skipif(
    not hasattr(socket, "SO_PEERCRED"), reason="Actual Linux peer credentials"
)
@pytest.mark.parametrize("resume", [False, True])
def test_socket_dispatch_reads_kernel_peer_not_payload(monkeypatch, tmp_path, resume):
    import struct

    peer, server = socket.socketpair()
    seen = []

    def record(value, **kw):
        seen.append(kw["relational_peer_uid"])
        return {"ok": False, "error": "test_only"}

    monkeypatch.setattr(update_helper, "_handle_request", record)
    try:
        peer.sendall(canonical(request(resume)) + b"\n")
        update_helper._serve_connection(server)
        assert seen == [
            struct.unpack(
                "3i",
                server.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                ),
            )[1]
        ]
        assert peer.recv(4096).endswith(b"\n")
    finally:
        peer.close()
        server.close()
