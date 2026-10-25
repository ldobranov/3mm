"""Trusted runtime composition and live transport-generation refusal.

Uses real M20/browser fixtures for admission; fake executors here are deliberately
not a physical Node, relay, PTY, or OS-isolation acceptance claim.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from starlette.websockets import WebSocketDisconnect

from backend.services.application_session_runtimes import (
    ReviewedSessionRuntime, SessionRuntimeDirectory,
    configure_session_runtimes, session_runtimes,
)
from backend.tests.test_application_browser_sessions import (
    ORIGIN, browser_app, connect, issue,
    checkpoint_app, managed_installed, session_app, source_installed, source_subject,
)
from three_mm_protocol.interactive_session import decode_session_frame


RESOURCE = {
    "target_device_id": "dev_" + "a" * 32,
    "provider_version": "1.0.0", "control_revision": "b" * 64,
    "declaration": {"provider_id": "org.example.counter"},
}


class Source:
    def __init__(self, *, available=True):
        self.current = True
        self.available_value = available
        self.created = 0
        self.resource = None
        self.provider = SimpleNamespace(**{name: lambda: None for name in
                                         ("open", "receive", "control", "close", "read_output")})

    def available(self, db, resource):
        if self.available_value == "error":
            raise RuntimeError("Unavailable executor")
        return self.available_value

    def resolve(self, engine, resource):
        self.created += 1
        self.resource = resource
        return ReviewedSessionRuntime(
            resource["target_device_id"], resource["declaration"]["provider_id"],
            resource["provider_version"], resource["control_revision"],
            self.provider, lambda: self.current,
        )


@pytest.mark.parametrize("values", [[], [False], [True, True], [True, "error"], [1], [None]])
def test_absent_ambiguous_failed_or_non_boolean_probe_never_constructs_provider(values):
    sources = [Source(available=v) for v in values]
    if not sources:
        with pytest.raises(ValueError):
            SessionRuntimeDirectory(sources)
        return
    directory = SessionRuntimeDirectory(sources)
    engine = create_engine("sqlite://")
    try:
        assert directory.resolve(engine, RESOURCE) is None
        assert not any(source.created for source in sources)
    finally:
        engine.dispose()


def test_exact_source_selection_has_no_order_or_local_fallback():
    absent, selected = Source(available=False), Source()
    directory = SessionRuntimeDirectory((absent, selected))
    engine = create_engine("sqlite://")
    try:
        runtime = directory.resolve(engine, RESOURCE)
        assert runtime.provider is selected.provider
        assert absent.created == 0 and selected.created == 1
        assert selected.resource == RESOURCE and selected.resource is not RESOURCE
        selected.current = False
        assert runtime.is_current() is False
        assert directory.resolve(engine, RESOURCE) is None
    finally:
        engine.dispose()


@pytest.mark.parametrize("field,value", [
    ("device_id", "dev_" + "f" * 32), ("provider_id", "org.example.other"),
    ("provider_version", "2.0.0"), ("control_revision", "f" * 64),
    ("is_current", lambda: 1), ("is_current", None), ("provider", object()),
])
def test_resolved_runtime_cannot_change_the_reviewed_target_or_omit_live_generation(field, value):
    source = Source()
    original = source.resolve
    source.resolve = lambda engine, resource: replace(original(engine, resource), **{field: value})
    engine = create_engine("sqlite://")
    try:
        assert SessionRuntimeDirectory((source,)).resolve(engine, RESOURCE) is None
    finally:
        engine.dispose()


def test_composition_is_bounded_per_engine_and_cannot_replace_live_sources():
    a, b = create_engine("sqlite://"), create_engine("sqlite://")
    try:
        one = configure_session_runtimes(a, (Source(),))
        two = configure_session_runtimes(b, (Source(),))
        assert session_runtimes(a) is one and session_runtimes(b) is two
        with a.connect() as connection:
            assert session_runtimes(connection) is one
        with pytest.raises(ValueError):
            configure_session_runtimes(a, (Source(),))
        with pytest.raises(ValueError):
            SessionRuntimeDirectory([Source()] * 9)
        with pytest.raises(ValueError):
            SessionRuntimeDirectory([object()])
    finally:
        a.dispose(); b.dispose()


def test_connection_generation_changed_after_ticket_never_opens_provider(browser_app):
    s = browser_app
    current = [True]
    s.browser.runtimes = (replace(s.runtime, is_current=lambda: current[0]),)
    ticket = issue(s).json()
    current[0] = False
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not s.provider.opened and not s.provider.inputs
    assert not s.browser.owned and not s.browser.reservations


def test_connection_replacement_closes_idle_owned_session_without_reconnect(browser_app):
    s = browser_app
    generation = ["connection-one"]
    s.browser.runtimes = (replace(s.runtime, is_current=lambda: generation[0] == "connection-one"),)
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        sid = ws.receive_json()["acceptance"]["session_id"]
        assert decode_session_frame(ws.receive_bytes())[1] == b"ready\r\n"
        generation[0] = "connection-two"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_bytes()
    assert len(s.provider.opened) == 1 and not s.provider.inputs
    assert len(s.provider.closed) == 1 and s.provider.closed[0][0] == sid
    assert not s.browser.owned and not s.browser.reservations


def test_source_cannot_mutate_the_authoritative_resource_to_select_another_target():
    source = Source()
    original = source.resolve
    def change(engine, resource):
        resource["target_device_id"] = "dev_" + "f" * 32
        return original(engine, resource)
    source.resolve = change
    engine = create_engine("sqlite://")
    try:
        assert SessionRuntimeDirectory((source,)).resolve(engine, RESOURCE) is None
        assert RESOURCE["target_device_id"] == "dev_" + "a" * 32
    finally:
        engine.dispose()
