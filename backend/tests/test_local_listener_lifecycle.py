from three_mm_platform_wire import COMPATIBILITY_ACTIONS
import os
import socket

import pytest

from backend.config import ApplicationRuntimeSettings
from backend.services.application_platform import ApplicationPlatformServer

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Target POSIX Unix socket ownership')


@pytest.fixture
def listener(request,tmp_path):
    path=tmp_path/'listener.sock'
    return ApplicationPlatformServer(path,tmp_path,group='missing-test-group', allowed_actions=COMPATIBILITY_ACTIONS)


def test_occupied_file_is_preserved_on_failed_start_and_stop(listener):
    listener.socket_path.write_text('preserve me')
    with pytest.raises(FileExistsError): listener.start()
    listener.stop()
    assert listener.socket_path.read_text()=='preserve me'


def test_partial_bind_failure_closes_descriptor_and_owned_socket(listener,monkeypatch):
    import backend.services.application_platform as sdk
    def unavailable(*args): raise PermissionError('cannot set socket mode')
    with monkeypatch.context() as patch:
        patch.setattr(sdk.os,'chmod',unavailable)
        with pytest.raises(PermissionError): listener.start()
    assert listener._server is None and not listener.socket_path.exists()
    listener.start()
    assert listener.is_running
    listener.stop()
    assert not listener.socket_path.exists()


def test_active_listener_is_never_replaced(listener):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as foreign:
        foreign.bind(str(listener.socket_path));foreign.listen(1)
        identity=listener.socket_path.stat().st_ino
        with pytest.raises(FileExistsError): listener.start()
        listener.stop()
        assert listener.socket_path.stat().st_ino==identity


def test_stale_socket_can_restart_and_shutdown_preserves_a_replacement_file(listener):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as stale:
        stale.bind(str(listener.socket_path))
    listener.start()
    assert listener.is_running
    moved=listener.socket_path.with_suffix('.old')
    listener.socket_path.rename(moved)
    listener.socket_path.write_text('different owner')
    listener.stop()
    assert not listener.is_running
    assert listener.socket_path.read_text()=='different owner'
    moved.unlink()


def test_thread_start_failure_cleans_the_bound_socket_and_can_be_retried(listener,monkeypatch):
    import threading
    def unavailable(self): raise RuntimeError('thread creation failed')
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread,'start',unavailable)
        with pytest.raises(RuntimeError,match='thread creation failed'): listener.start()
    assert listener._server is None and not listener.socket_path.exists()
    listener.start()
    assert listener.is_running
    listener.stop()
    assert not listener.socket_path.exists()
