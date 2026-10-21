"""Actual M20 UI/native/grant/user gates over HTTP and a real ASGI WebSocket.

The provider is a bounded in-process fixture, NOT an OS-isolation/PTY test.
No installed services, keys, permissions or hardware are consulted.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import (
    ApplicationPermissionGrant,
    ModulePackage,
)
from backend.db.session import UserSession
from backend.routes.application_extensions import ApplicationUiBinding
from backend.routes.application_sessions import application_session_router
from backend.services import compiled_ui
from backend.services.application_browser_sessions import (
    ApplicationBrowserSessions,
    ReviewedSessionRuntime,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_access import fake_compiler
from backend.tests.test_application_authority_management import decide, identity
from backend.tests.test_application_session_authority import (
    CAPABILITY,
    PROVIDER,
    SCOPE,
    checkpoint_app,
    managed_installed,
    session_app,
    source_installed,
    source_subject,
)
from backend.tests.test_application_ui_authority import native
from backend.tests.test_module_packages import application_package
from three_mm_protocol.interactive_session import (
    decode_session_frame,
    encode_session_frame,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Actual protected M20 keys")
ORIGIN = "http://browser.example"


class FixtureProvider:
    def __init__(self):
        self.opened, self.inputs, self.controls, self.closed = [], [], [], []
        self.queue = None
        self.fail_close = False

    async def open(self, context):
        self.opened.append(context)
        self.queue = asyncio.Queue(maxsize=1)
        self.queue.put_nowait(b"ready\r\n")

    async def read_output(self, _session_id):
        return await self.queue.get()

    async def receive(self, session_id, data):
        self.inputs.append((session_id, data))
        return b"reply:" + data

    async def control(self, _session_id, value):
        # The public SDK receives the action, not the browser wire envelope.
        assert set(value) == {"action", "arguments"}
        self.controls.append(value)

    async def close(self, session_id, reason):
        self.closed.append((session_id, reason))
        if self.fail_close:
            raise RuntimeError("Fixture cleanup failed")


@pytest.fixture
def browser_app(session_app, monkeypatch):
    s = session_app
    manifest = s.validated.manifest.model_dump(mode="json")
    manifest.update(
        runtimes=["core", "ui"],
        entrypoints={"core": "application-extension.json", "ui": "compiled-ui.json"},
    )
    definition = s.validated.application_extension.model_dump(mode="json")
    definition["routes"] = [
        {
            "route_id": entry,
            "entrypoint_id": entry,
            "audience": "operator",
            "required_permissions": ["session_use"],
        }
        for entry in ("registration", "operations")
    ]
    blob = application_package(definition=definition, manifest_value=manifest)
    s.validated = validate_module_package(blob)
    s.archive = s.root / "modules" / (s.validated.sha256 + ".zip")
    s.archive.write_bytes(blob)
    with s.engine.begin() as db:
        db.execute(
            update(ModulePackage).values(
                sha256=s.validated.sha256,
                size_bytes=len(blob),
                file_path=str(s.archive),
                manifest=manifest,
            )
        )
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(s.root / "compiled"))

    def compiler(command, **kwargs):
        result = fake_compiler(command, **kwargs)
        (Path(command[3]) / "build-toolchain.json").write_text(
            json.dumps({"node": "24.19.0", "vite": "6.4.3", "vue_plugin": "5.2.4"})
        )
        return result

    monkeypatch.setattr(compiled_ui.subprocess, "run", compiler)
    s.build = compiled_ui.compile_ui_package(blob, s.validated)
    proof = native(s)

    def grant():
        plan = s.manager.create_review(
            1,
            actor_token=s.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            scopes=[SCOPE],
        )
        return decide(s, decide(s, plan, "approve"), "apply")

    grant()
    with s.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True, status="active", authority_epoch=identity()
            )
        )
    s.grant = grant()
    s.grant_record_revision = s.manager.inspect(1)["grant_record_revision"]
    s.ui = ApplicationUiBinding(
        host_version=1,
        entrypoint_id="operations",
        artifact_sha256=s.validated.sha256,
        built_ui_sha256=s.build.built_ui_sha256,
    )
    resource = s.session_authority._resolve(
        1, "console", "ses_" + "a" * 32, "Bearer " + s.user_token, s.request
    )[1]
    s.provider = FixtureProvider()
    s.runtime = ReviewedSessionRuntime(
        resource.target_device_id,
        PROVIDER,
        resource.provider_version,
        resource.control_revision,
        s.provider,
    )
    s.browser = ApplicationBrowserSessions(
        s.session_authority, runtimes=[s.runtime], allowed_origins=[ORIGIN]
    )
    app = FastAPI()
    app.include_router(application_session_router(s.browser))
    s.base = f"/api/v1/application-extensions/{s.validated.manifest.module_id}/session-host/operations"
    s.auth = {"Authorization": "Bearer " + s.user_token}
    with TestClient(app) as client:
        s.client = client
        yield s


def issue(s, **changes):
    body = {
        "binding_id": "console",
        "ui_context": s.ui.model_dump(),
        "request": s.request.model_dump(mode="json"),
        **changes,
    }
    return s.client.post(s.base + "/ticket", headers=s.auth, json=body)


def connect(s, ticket):
    return s.client.websocket_connect(s.base + "/ws", headers={"origin": ORIGIN})


def test_real_ui_ticket_binary_stream_input_control_and_owned_cleanup(browser_app):
    s = browser_app
    discovery = s.client.get(
        s.base,
        params=s.ui.model_dump(exclude={"host_version", "entrypoint_id"}),
        headers=s.auth,
    )
    assert (
        discovery.status_code == 200
        and discovery.headers["cache-control"] == "no-store"
    )
    assert discovery.json()["targets"][0]["available"] is True
    response = issue(s)
    assert response.status_code == 200
    ticket = response.json()
    assert not s.provider.opened
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        opened = ws.receive_json()["acceptance"]
        assert opened["request_id"] == s.request.request_id
        session_id = opened["session_id"]
        try:
            frame = ws.receive_bytes()
        except WebSocketDisconnect:
            pytest.fail(f"Session unexpectedly stopped: {list(s.browser.failures)}")
        header, output = decode_session_frame(frame)
        assert (
            header.session_id == session_id
            and header.seq == 1
            and output == b"ready\r\n"
        )
        ws.send_bytes(
            encode_session_frame(
                op="data",
                seq=1,
                session_id=session_id,
                payload=b"hello",
                payload_kind="binary",
            )
        )
        header, output = decode_session_frame(ws.receive_bytes())
        assert header.seq == 2 and output == b"reply:hello"
        assert ws.receive_json() == {
            "op": "input_ack",
            "session_id": session_id,
            "seq": 1,
        }
        ws.send_json(
            {
                "op": "control",
                "control": {
                    "session_id": session_id,
                    "control_id": "resize_1",
                    "action": "resize",
                    "arguments": {"cols": 80, "rows": 24},
                },
            }
        )
        assert ws.receive_json()["op"] == "control_ack"
        ws.send_json({"op": "close", "session_id": session_id})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert len(s.provider.opened) == len(s.provider.closed) == 1
    assert s.provider.controls == [
        {"action": "resize", "arguments": {"cols": 80, "rows": 24}}
    ]
    assert not s.browser.owned and not s.browser.leases
    with Session(s.engine) as db:
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "APPLICATION_SESSION_LIFECYCLE"
                )
            )
        )
        assert [row.changes["outcome"] for row in audits] == [
            "start_requested",
            "closed",
        ]
        assert all(
            set(row.changes)
            == {"session_id", "binding_id", "grant_revision", "outcome"}
            for row in audits
        )
        assert "hello" not in json.dumps([row.changes for row in audits])
    assert issue(s).status_code == 403  # No retry/reopen with this request ID.
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert len(s.provider.opened) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "service",
        "human",
        "login",
        "build",
        "mode",
        "device",
        "options",
        "ui",
        "no_runtime",
    ],
)
def test_denied_or_changed_bound_authority_cannot_start_provider(browser_app, fault):
    s = browser_app
    if fault == "service":
        s.manager.revoke(
            1,
            actor_token=s.token,
            request_id=identity(),
            expected_revision=s.grant_record_revision,
        )
    elif fault in {"human", "login"}:
        with s.engine.begin() as db:
            db.execute(
                delete(ApplicationPermissionGrant)
                if fault == "human"
                else update(UserSession)
                .where(UserSession.id == 2)
                .values(is_active=False)
            )
    elif fault == "build":
        (s.build.path / "assets/operations.mjs").write_text("changed")
    elif fault == "no_runtime":
        s.browser.runtimes = ()
    changes = {}
    if fault in {"mode", "device", "options"}:
        changes["request"] = {
            **s.request.model_dump(mode="json"),
            **{
                "mode": {"access_mode": "read"},
                "device": {"device_id": "dev_" + "f" * 32},
                "options": {"options": {"columns": 120, "rows": 24}},
            }[fault],
        }
    if fault == "ui":
        changes["ui_context"] = {**s.ui.model_dump(), "entrypoint_id": "registration"}
    assert issue(s, **changes).status_code in {401, 403, 409}
    assert not s.provider.opened


@pytest.mark.parametrize("fault", ["human", "service", "login", "build"])
def test_idle_stream_observes_revocation_without_another_input(browser_app, fault):
    s = browser_app
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        ws.receive_json()
        ws.receive_bytes()
        if fault == "service":
            # Serialize this deliberate test mutation against the idle checker;
            # no stale/status-only read caused by a busy key is used as intent.
            with s.browser.authority_lock:
                s.manager.revoke(
                    1,
                    actor_token=s.token,
                    request_id=identity(),
                    expected_revision=s.grant_record_revision,
                )
        elif fault == "build":
            (s.build.path / "assets/operations.mjs").write_text("changed")
        else:
            with s.engine.begin() as db:
                db.execute(
                    delete(ApplicationPermissionGrant)
                    if fault == "human"
                    else update(UserSession)
                    .where(UserSession.id == 2)
                    .values(is_active=False)
                )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert len(s.provider.closed) == 1 and not s.provider.inputs


def test_no_origin_wrong_origin_query_ticket_and_wrong_session_are_rejected(
    browser_app,
):
    s = browser_app
    for headers, suffix in [
        ({}, ""),
        ({"origin": "http://foreign.example"}, ""),
        ({"origin": ORIGIN}, "?ticket=secret"),
    ]:
        with (
            pytest.raises(WebSocketDisconnect),
            s.client.websocket_connect(s.base + "/ws" + suffix, headers=headers),
        ):
            pass
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        ws.receive_json()
        ws.receive_bytes()
        ws.send_bytes(
            encode_session_frame(
                op="data",
                seq=1,
                session_id="ses_" + "f" * 32,
                payload=b"wrong",
                payload_kind="binary",
            )
        )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not s.provider.inputs and len(s.provider.closed) == 1


def test_revocation_between_ticket_and_redemption_and_failed_cleanup_stay_fenced(
    browser_app,
):
    s = browser_app
    ticket = issue(s).json()
    with s.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant))
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not s.provider.opened and not s.browser.leases


def test_unconfirmed_provider_cleanup_retains_bounded_ownership(browser_app):
    s = browser_app
    s.provider.fail_close = True
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        session_id = ws.receive_json()["acceptance"]["session_id"]
        ws.receive_bytes()
        ws.send_json({"op": "close", "session_id": session_id})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert s.browser.owned[session_id].failed and session_id in s.browser.leases
    assert len(s.provider.closed) == 1
    assert (
        issue(
            s,
            request={**s.request.model_dump(mode="json"), "request_id": "replacement"},
        ).status_code
        == 403
    )


def test_pending_binding_reservation_prevents_replacement_open(browser_app):
    s = browser_app
    ticket = issue(s).json()
    assert "ticket" in ticket
    replacement = {**s.request.model_dump(mode="json"), "request_id": "new_attempt"}
    assert issue(s, request=replacement).status_code == 403
    assert not s.provider.opened


@pytest.mark.parametrize("session_app", ["read"], indirect=True)
def test_read_only_browser_cannot_deliver_input(browser_app):
    s = browser_app
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        session_id = ws.receive_json()["acceptance"]["session_id"]
        ws.receive_bytes()
        ws.send_bytes(
            encode_session_frame(
                op="data",
                seq=1,
                session_id=session_id,
                payload=b"not allowed",
                payload_kind="binary",
            )
        )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not s.provider.inputs


@pytest.mark.parametrize(
    "fault", ["unapproved_control", "duplicate_input", "expired_ticket"]
)
def test_no_unapproved_controls_input_replay_or_expired_ticket(browser_app, fault):
    s = browser_app
    ticket = issue(s).json()
    if fault == "expired_ticket":
        previous = s.browser.tickets[ticket["ticket"]]
        s.browser.tickets[ticket["ticket"]] = (0, *previous[1:])
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        if fault != "expired_ticket":
            session_id = ws.receive_json()["acceptance"]["session_id"]
            ws.receive_bytes()
            if fault == "unapproved_control":
                ws.send_json(
                    {
                        "op": "control",
                        "control": {
                            "session_id": session_id,
                            "control_id": "signal_1",
                            "action": "signal",
                            "arguments": {},
                        },
                    }
                )
            else:
                frame = encode_session_frame(
                    op="data",
                    seq=1,
                    session_id=session_id,
                    payload=b"once",
                    payload_kind="binary",
                )
                ws.send_bytes(frame)
                ws.receive_bytes()
                ws.receive_json()
                ws.send_bytes(frame)
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not s.provider.controls
    assert len(s.provider.inputs) == (1 if fault == "duplicate_input" else 0)


def test_session_lifetime_is_bounded_without_input(browser_app):
    s = browser_app
    now = s.browser.clock()
    s.browser.clock = lambda: now
    ticket = issue(s).json()
    with connect(s, ticket) as ws:
        ws.send_json({"op": "authenticate", "ticket": ticket["ticket"]})
        ws.receive_json()
        ws.receive_bytes()
        s.browser.clock = lambda: now + s.browser.lifetime + 1
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert len(s.provider.closed) == 1 and not s.browser.owned
