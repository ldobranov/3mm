"""Real independent SDK relay, signed Core admission and original kernel peers."""
from contextlib import ExitStack
import array
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import pytest
from sqlalchemy.orm import sessionmaker

import backend.database
from backend.services.application_platform import CoreRuntimeAuthorityServer
from backend.tests.test_application_identity_read import (
    identity_app, activate_identity_grant, managed_installed, source_subject,
    source_installed, checkpoint_app, identity,
)
from deployment.platform_runtime_component import build_component, validate_artifact
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_platform_runtime.server import probe_runtime
from three_mm_platform_wire import (
    AUTHORITY_CONTRACT, RUNTIME_ACTIONS, peer_identity, receive_authority_frame,
    send_authority_frame,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Linux SCM_RIGHTS and SO_PEERCRED")
SOURCE = Path(__file__).resolve().parents[2]


@pytest.fixture
def relay(identity_app, monkeypatch):
    state = identity_app
    activate_identity_grant(state)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(bind=state.engine))
    with tempfile.TemporaryDirectory(prefix="p4b-", dir="/tmp") as directory:
        base = Path(directory)
        (base / ("a" * 24 + ".key")).write_bytes(b"s" * 32)
        gate = CoreRuntimeAuthorityServer(base / "authority.sock", base,
            runtime_uid=os.geteuid(), group="missing-test-group", runtime_root=base / "applications")
        observed = []
        dispatch = gate._dispatch
        def observe(db, installation, request, **kwargs):
            observed.append(dict(request))
            return dispatch(db, installation, request, **kwargs)
        monkeypatch.setattr(gate, "_dispatch", observe)
        gate.start()
        blob, metadata = build_component(SOURCE)
        _, code = validate_artifact(blob, hashlib.sha256(blob).hexdigest())
        executable = base / "runtime.pyz"
        executable.write_bytes(code)
        with (base / "runtime.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, "-I", str(executable),
                "--socket", str(base / "runtime.sock"), "--authority-socket", str(gate.socket_path),
                "--core-uid", str(os.geteuid())], cwd=base,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 4
                while True:
                    try:
                        result = probe_runtime(base / "runtime.sock", expected_uid=os.geteuid(),
                            expected_build=metadata["build_id"])
                        assert result["authority_contract"] == AUTHORITY_CONTRACT
                        break
                    except (OSError, ValueError):
                        assert process.poll() is None, (base / "runtime.log").read_text()
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                client = ApplicationPlatformClient(base / "runtime.sock", "a" * 24, b"s" * 32)
                yield gate, client, process, observed
            finally:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                gate.stop()


@pytest.mark.parametrize("action", sorted(RUNTIME_ACTIONS))
def test_every_current_family_uses_original_signed_request_and_current_core_admission(relay, action):
    gate, client, process, observed = relay
    payload = {"runtime_nonce": identity()} if action == "relational.boot.startup" else {}
    if action in {"platform.discover", "installation.identity.get"}:
        assert isinstance(client._call(action, payload), dict)
    else:
        # This installation has only the identity grant: a relay adds no rights.
        with pytest.raises(ApplicationPlatformError) as error:
            client._call(action, payload)
        assert error.value.reason in {"operation_denied", "operation_unsupported"}
    assert len(observed) == 1 and observed[0]["action"] == action
    assert observed[0]["instance_id"] == client.instance_id
    assert gate.active_connections <= gate.max_connections
    assert process.pid != os.getpid()


def test_original_kernel_peer_survives_runtime_relay_and_signed_success_is_unchanged(relay, monkeypatch):
    gate, client, process, observed = relay
    import backend.services.application_relational_startup as startup
    calls = []
    def admit(db, installation_id, nonce, *, transport_secret, runtime_root, peer_credentials):
        assert peer_credentials == (os.getpid(), os.geteuid(), os.getegid())
        assert peer_credentials[0] != process.pid
        assert runtime_root == gate.runtime_root and transport_secret == client.secret
        calls.append(nonce)
        return {"verified_original_peer": True}
    monkeypatch.setattr(startup, "admit_boot_startup", admit)
    nonce = identity()
    assert client._call("relational.boot.startup", {"runtime_nonce": nonce}) == {"verified_original_peer": True}
    assert calls == [nonce]
    with pytest.raises(ApplicationPlatformError):
        client._call("relational.boot.startup", {"runtime_nonce": identity(), "peer_credentials": [1, 1, 1]})
    assert calls == [nonce]


def test_relay_has_full_contract_budget_and_does_not_resurrect_the_old_metadata_ceiling(relay):
    _, client, _, observed = relay
    with pytest.raises(ApplicationPlatformError) as error:
        client._call("installation.identity.get", {"foreign": "x" * 20000})
    assert error.value.reason == "operation_denied"
    assert observed[0]["foreign"] == "x" * 20000


@pytest.mark.filterwarnings("error::pytest.PytestUnhandledThreadExceptionWarning")
def test_private_gate_refuses_old_abi_missing_origin_and_origin_on_wrong_operation(relay):
    gate, _, _, observed = relay
    requests = [
        {"authority_contract": 1, "authority_probe": identity()},
        {"action": "relational.boot.startup"},
        {"action": ["platform.discover"]},
    ]
    for request in requests:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            connection.connect(str(gate.socket_path))
            send_authority_frame(connection, request)
            assert connection.recv(4096) == b""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection, ExitStack() as stack:
        origin, peer = socket.socketpair()
        stack.enter_context(origin); stack.enter_context(peer)
        connection.settimeout(1); connection.connect(str(gate.socket_path))
        send_authority_frame(connection, {"action": "platform.discover"}, origin=origin)
        assert connection.recv(4096) == b""
    assert observed == []


@pytest.mark.parametrize("damage", ["unknown_marker", "missing_fd", "unexpected_fd", "multiple_fds",
    "truncated_fds", "regular_file", "internet_socket", "datagram", "listening", "unconnected", "bad_json"])
def test_rejected_private_origin_never_leaks_received_file_descriptors(tmp_path, damage):
    with ExitStack() as stack:
        sender, receiver = socket.socketpair()
        stack.enter_context(sender); stack.enter_context(receiver)
        origin, peer = socket.socketpair()
        stack.enter_context(origin); stack.enter_context(peer)
        marker, descriptors = b"\1", [origin.fileno()]
        if damage == "unknown_marker": marker = b"x"
        elif damage == "missing_fd": descriptors = []
        elif damage == "unexpected_fd": marker = b"\0"
        elif damage == "multiple_fds": descriptors *= 2
        elif damage == "truncated_fds": descriptors *= 20
        elif damage == "regular_file": descriptors = [stack.enter_context((tmp_path / "file").open("wb")).fileno()]
        elif damage in {"internet_socket", "datagram", "listening", "unconnected"}:
            family = socket.AF_INET if damage == "internet_socket" else socket.AF_UNIX
            kind = socket.SOCK_DGRAM if damage == "datagram" else socket.SOCK_STREAM
            other = stack.enter_context(socket.socket(family, kind))
            if damage == "listening": other.bind(str(tmp_path / "listener.sock")); other.listen(1)
            descriptors = [other.fileno()]
        ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", descriptors))] if descriptors else []
        before = len(list(Path("/proc/self/fd").iterdir()))
        sender.sendmsg([marker], ancillary)
        sender.sendall(b"{broken}\n" if damage == "bad_json" else b"{}\n")
        with pytest.raises((OSError, ValueError)):
            receive_authority_frame(receiver, time.monotonic() + 1)
        assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_received_original_socket_is_close_on_exec_and_caller_owned():
    with ExitStack() as stack:
        sender, receiver = socket.socketpair()
        origin, peer = socket.socketpair()
        for connection in (sender, receiver, origin, peer): stack.enter_context(connection)
        send_authority_frame(sender, {"action": "relational.boot.startup"}, origin=origin)
        request, received = receive_authority_frame(receiver, time.monotonic() + 1)
        try:
            assert request == {"action": "relational.boot.startup"}
            assert not os.get_inheritable(received.fileno())
            assert peer_identity(received) == peer_identity(origin)
        finally:
            received.close()
        peer.sendall(b"x")
        assert origin.recv(1) == b"x"  # Closing duplicate does not shut down the original.


def test_runtime_refuses_old_abi2_core_without_connector_feature(tmp_path):
    import threading
    from three_mm_platform_runtime.server import probe_core
    path=tmp_path/'old-core.sock'
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));listener.listen(1)
    def old_core():
        connection,_=listener.accept()
        with connection:
            request,origin=receive_authority_frame(connection,time.monotonic()+2)
            assert origin is None and request.pop('connector_execution_contract')==1
            connection.sendall(json.dumps(request).encode()+b'\n')
    worker=threading.Thread(target=old_core);worker.start()
    try:
        with pytest.raises(ValueError,match='contract'):probe_core(path,os.geteuid())
    finally:worker.join(timeout=3);listener.close()
