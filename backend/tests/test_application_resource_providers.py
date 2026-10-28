"""Actual local worker probes; no connector HTTP, application handler or task."""
import os
import threading
import time

import pytest
pwd = pytest.importorskip('pwd')

from backend.config import ApplicationRuntimeSettings
from backend.services.application_resource_providers import observe
from backend.tests.test_application_command_discovery import vertical, installed, source_subject, source_installed
from backend.tests.test_application_consent import preview, allow
from three_mm_platform_runtime.connector_worker import ConnectorWorker
from three_mm_platform_runtime.server import PlatformRuntime
from three_mm_platform_runtime.events import EventDeliveryWorker
from three_mm_platform_runtime.tasks import TaskWorker

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Actual Unix principals and local workers')


def test_connector_resource_uses_real_worker_without_contacting_destination(vertical, monkeypatch):
    import backend.config as config
    import three_mm_platform_runtime.connector_worker as connector
    s = vertical
    settings = config.get_settings()
    path = s.runtime_socket.with_name('connector.sock')
    current = pwd.getpwuid(os.geteuid()).pw_name
    monkeypatch.setattr(config,'get_settings',lambda:settings.model_copy(update={'applications':
        settings.applications.model_copy(update={'connector_worker_socket':path,'connector_worker_user':current})}))
    monkeypatch.setattr(connector,'execute',lambda *_:pytest.fail('Readiness sent a business HTTP request'))
    allow(s,preview(s))
    worker = ConnectorWorker(path,core_uid=os.geteuid())
    worker.start(); thread = threading.Thread(target=worker.serve_forever,daemon=True); thread.start()
    try:
        row = s.sdk.discover_resources(['connector:business_api'])['resources'][0]
        assert row['readiness'] == 'ready' and row['provider']['provider_id'] == 'http_connector'
        assert not worker.children
        monkeypatch.setattr(config,'get_settings',lambda:settings.model_copy(update={'applications':
            settings.applications.model_copy(update={'connector_worker_socket':path,'connector_worker_user':'root'})}))
        assert s.sdk.discover_resources(['connector:business_api'])['resources'][0]['readiness'] == 'unknown'
    finally: worker.close(); thread.join(timeout=2)


def test_real_event_worker_negotiates_metadata_and_queue_boundary(vertical):
    s = vertical
    runtime = PlatformRuntime(s.runtime_socket.with_name('events.sock'),s.server.socket_path,core_uid=os.geteuid())
    runtime.events = EventDeliveryWorker(s.server.socket_path,core_uid=os.geteuid())
    runtime.start(); thread = threading.Thread(target=runtime.serve_forever,daemon=True); thread.start()
    settings = ApplicationRuntimeSettings(runtime_socket=runtime.path, runtime_user=pwd.getpwuid(os.geteuid()).pw_name)
    try:
        deadline = time.monotonic()+4
        while observe('event',settings) != 'ready':
            assert time.monotonic() < deadline
            time.sleep(.02)
    finally:
        runtime.events.close(); runtime.close(); thread.join(timeout=2)
    assert observe('event',settings) == 'unavailable'


def test_task_probe_never_claims_or_ticks_and_expires_after_lost_core(vertical, monkeypatch):
    s = vertical
    worker = TaskWorker(s.server.socket_path,core_uid=os.geteuid())
    def forbidden(*args): pytest.fail('Readiness executed a worker operation')
    monkeypatch.setattr(worker,'run_once',forbidden)
    monkeypatch.setattr(worker,'poll_schedules',forbidden)
    worker.runner = threading.current_thread()
    path = s.runtime_socket.with_name('task-probe.sock')
    settings = ApplicationRuntimeSettings(task_worker_socket=path,runtime_user=pwd.getpwuid(os.geteuid()).pw_name)
    with worker.readiness_socket(path):
        assert observe('task',settings) == 'unavailable'
        assert worker.exchange({'action':'schedule.poll'}) == []
        assert observe('task',settings) == 'ready'
        worker.last_exchange -= 16
        assert observe('task',settings) == 'unavailable'
        worker.last_exchange = time.monotonic(); worker.stop_event.set()
        assert observe('task',settings) == 'unavailable'
