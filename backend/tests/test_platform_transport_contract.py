"""Real signed current SDK contract, overload, recovery and no replay."""
from three_mm_platform_wire import COMPATIBILITY_ACTIONS
from contextlib import ExitStack
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

import backend.database
import three_mm_application_sdk as sdk
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_platform as platform
from backend.tests.test_application_identity_read import (
    identity_app, activate_identity_grant, managed_installed, source_subject,
    source_installed, checkpoint_app, identity,
)
from three_mm_protocol.platform_transport import MAX_CONNECTIONS, SCOPED_ACTIONS

pytestmark=pytest.mark.skipif(os.name!="posix",reason="Real POSIX authority and Unix listener")


def wait_for(predicate,timeout=2):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline: pytest.fail("local listener did not reach expected state")
        time.sleep(.005)


@pytest.fixture
def boundary(identity_app,monkeypatch):
    state=identity_app
    activate_identity_grant(state)
    monkeypatch.setattr(backend.database,"SessionLocal",sessionmaker(bind=state.engine))
    with tempfile.TemporaryDirectory(prefix="pt-",dir="/tmp") as directory:
        root=Path(directory)
        secret=b"s"*32
        (root/("a"*24+".key")).write_bytes(secret)
        server=platform.ApplicationPlatformServer(root/"platform/platform.sock",root,group="missing-test-group", allowed_actions=COMPATIBILITY_ACTIONS)
        server.start()
        client=sdk.ApplicationPlatformClient(server.socket_path,"a"*24,secret)
        try: yield state,server,client
        finally: server.stop()


def test_discovery_is_current_metadata_not_an_authority_lease(boundary):
    state,server,client=boundary
    first=client.discover_platform()
    assert set(first["operations"])==SCOPED_ACTIONS
    assert first["admission_cache_ms"]==0 and first["automatic_retry"] is False
    assert first["jobs_supported"] is False and first["max_connections"]==MAX_CONNECTIONS
    assert client.get_installation_identity()["sdk_version"]=="1.3"
    state.manager.revoke(1,actor_token=state.token,request_id=identity(),
        expected_revision=state.manager.inspect(1)["grant_record_revision"])
    second=client.discover_platform()
    assert second["authority_epoch"] != first["authority_epoch"]
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.get_installation_identity()
    assert error.value.reason=="operation_denied" and not error.value.retryable


def test_recovery_and_listener_restart_change_distinct_generations(boundary):
    state,server,client=boundary
    before=client.discover_platform()
    generation=identity()
    with state.engine.begin() as db:
        db.execute(update(CoreAuthorityGuard).values(generation=generation))
    after=client.discover_platform()
    assert after["recovery_generation"]==generation
    assert after["transport_generation"]==before["transport_generation"]
    with pytest.raises(sdk.ApplicationPlatformError): client.get_installation_identity()
    server.stop();server.start()
    restarted=client.discover_platform()
    assert restarted["transport_generation"]!=before["transport_generation"]
    assert restarted["recovery_generation"]==generation
    with pytest.raises(sdk.ApplicationPlatformError): client.get_installation_identity()


def test_disabled_installation_cannot_reuse_discovery(boundary):
    state,server,client=boundary
    client.discover_platform()
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False,status="disabled"))
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.reason=="installation_unavailable"


def test_unknown_action_extra_fields_and_internal_failure_have_fixed_reasons(boundary,monkeypatch):
    _,server,client=boundary
    for action,payload,reason in [("not.supported",{},"operation_unsupported"),
            ("platform.discover",{"authority_mode":"compatibility"},"operation_denied")]:
        with pytest.raises(sdk.ApplicationPlatformError) as error: client._call(action,payload)
        assert error.value.reason==reason
    def fail(*args,**kwargs): raise OSError("private-path secret=must-not-leak")
    monkeypatch.setattr(server,"_dispatch",fail)
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.reason=="operation_failed" and "must-not-leak" not in str(error.value)


def test_request_id_is_not_dispatched_twice_and_replay_cache_is_bounded(boundary,monkeypatch):
    _,server,client=boundary
    request_id="platform_"+identity()
    client._exchange("installation.identity.get",{},request_id)
    with pytest.raises(sdk.ApplicationPlatformError) as error:
        client._exchange("installation.identity.get",{},request_id)
    assert error.value.reason=="request_replayed"
    monkeypatch.setattr(platform,"MAX_RECENT_REQUESTS",len(server._recent))
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.reason=="overloaded"
    assert len(server._recent)==1


def test_busy_listener_closes_excess_connections_and_recovers_capacity(boundary):
    _,server,client=boundary
    with ExitStack() as stack:
        for _ in range(MAX_CONNECTIONS):
            connection=stack.enter_context(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM))
            connection.settimeout(1);connection.connect(str(server.socket_path))
        wait_for(lambda:server.active_connections==MAX_CONNECTIONS)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as excess:
            excess.settimeout(1);excess.connect(str(server.socket_path))
            assert excess.recv(1)==b""
        assert server.active_connections==MAX_CONNECTIONS
    wait_for(lambda:server.active_connections==0)
    assert client.get_installation_identity()["sdk_version"]=="1.3"


def test_incomplete_request_read_deadline_and_shutdown_release_slots(boundary,monkeypatch):
    _,server,client=boundary
    monkeypatch.setattr(platform,"READ_TIMEOUT_SECONDS",.08)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as partial:
        partial.settimeout(1);partial.connect(str(server.socket_path));partial.sendall(b'{')
        wait_for(lambda:server.active_connections==1)
        assert partial.recv(1)==b""
    wait_for(lambda:server.active_connections==0)
    monkeypatch.setattr(platform,"READ_TIMEOUT_SECONDS",5)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as partial:
        partial.connect(str(server.socket_path));partial.sendall(b'{')
        wait_for(lambda:server.active_connections==1)
        server.stop()
        assert server.active_connections==0 and not server._handlers
    server.start()
    assert client.get_installation_identity()["sdk_version"]=="1.3"


def test_sdk_timeout_is_ambiguous_and_never_retries(boundary,monkeypatch):
    _,server,client=boundary
    calls=[]
    def late(*args,**kwargs):
        calls.append("admitted")
        time.sleep(.2)
        return {"executed":True}
    monkeypatch.setattr(server,"_dispatch",late)
    monkeypatch.setattr(sdk,"REQUEST_TIMEOUT_SECONDS",.06)
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.get_installation_identity()
    assert error.value.reason=="deadline_exceeded"
    assert error.value.phase=="execution_unconfirmed" and not error.value.retryable
    wait_for(lambda:server.active_connections==0)
    assert calls==["admitted"]


def test_unavailable_transport_is_not_dispatched_and_reserved_fields_do_not_send(tmp_path):
    client=sdk.ApplicationPlatformClient(tmp_path/"missing.sock","a"*24,b"s"*32)
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.phase=="not_dispatched" and not error.value.retryable
    with pytest.raises(sdk.ApplicationPlatformError) as error: client._call("platform.discover",{"instance_id":"b"*24})
    assert error.value.reason=="request_invalid" and error.value.phase=="not_dispatched"


def test_request_thread_start_failure_returns_capacity_without_stopping_listener(boundary,monkeypatch):
    _,server,client=boundary
    original=threading.Thread.start
    def fail_handler(thread):
        if thread.name=="3mm-application-platform-request": raise RuntimeError("no thread")
        return original(thread)
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread,"start",fail_handler)
        with pytest.raises(sdk.ApplicationPlatformError): client.discover_platform()
        wait_for(lambda:server.active_connections==0)
    assert server.is_running
    assert client.get_installation_identity()["sdk_version"]=="1.3"


def test_oversized_result_is_signed_failure_with_unconfirmed_outcome(boundary,monkeypatch):
    _,server,client=boundary
    monkeypatch.setattr(server,"_dispatch",lambda *args,**kwargs:{"data":"x"*platform.MAX_PLATFORM_MESSAGE_BYTES})
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.reason=="response_too_large" and error.value.phase=="execution_unconfirmed"


@pytest.mark.parametrize("damage",["signature","version","timestamp","ok","reason","result","nonfinite"])
def test_sdk_rejects_malformed_signed_response_without_retry(boundary,monkeypatch,damage):
    _,server,client=boundary
    original=sdk.read_frame
    calls=[]
    def damaged(connection,deadline):
        import hashlib,hmac
        from three_mm_protocol.platform_transport import canonical
        response=original(connection,deadline)
        calls.append(response["request_id"])
        if damage=="signature": response["signature"]="0"*64
        elif damage=="version": response["version"]=True
        elif damage=="timestamp": response["timestamp"]=True
        elif damage=="ok": response["ok"]=1
        elif damage=="reason": response.update(ok=False,reason={"untrusted":"value"})
        elif damage=="result": response["result"]={**response["result"],"instance_id":"f"*24}
        elif damage=="nonfinite": response["result"]={"n":float("inf")}
        if damage not in {"signature","nonfinite"}:
            response["signature"]=hmac.new(client.secret,canonical(response),hashlib.sha256).hexdigest()
        return response
    monkeypatch.setattr(sdk,"read_frame",damaged)
    with pytest.raises(sdk.ApplicationPlatformError) as error: client.discover_platform()
    assert error.value.reason=="response_invalid" and not error.value.retryable
    assert len(calls)==1


def test_boot_transport_preserves_original_unix_peer_and_exact_success_envelope(boundary,monkeypatch):
    _,server,client=boundary
    import backend.services.application_relational_startup as startup
    observed=[]
    def admit(db,installation_id,nonce,*,transport_secret,runtime_root,peer_credentials):
        assert peer_credentials==(os.getpid(),os.geteuid(),os.getegid())
        assert transport_secret==client.secret and runtime_root==server.socket_path.parent.parent
        observed.append(nonce)
        return {"transport_verified":True}
    monkeypatch.setattr(startup,"admit_boot_startup",admit)
    original=sdk.read_frame
    def envelope(connection,deadline):
        result=original(connection,deadline)
        assert set(result)=={"version","request_id","timestamp","ok","result","signature"}
        return result
    monkeypatch.setattr(sdk,"read_frame",envelope)
    nonce=identity()
    assert client._call("relational.boot.startup",{"runtime_nonce":nonce})=={"transport_verified":True}
    assert observed==[nonce]
