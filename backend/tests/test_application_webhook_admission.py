"""Loopback CAP12 admission with real Core seals and disposable state."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager, ExitStack
from dataclasses import asdict, replace
import hashlib
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import re
import secrets
import select
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import zipfile

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.application_authority_grant import ApplicationAuthorityAction
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_extensions import ApplicationGatewayError, prepare_application_invocation
from backend.services.application_webhook_admission import ReviewedWebhookAdmission, ReviewedWebhookTarget
from backend.services.authority_metadata import authority_transaction, read_application_authority
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_application_authority_management import identity, installed, source_subject, source_installed
from backend.tests.test_application_consent import allow, preview, state as core_state
from backend.tests.test_application_public_forms import launch_host, stop_host
from three_mm_protocol.public_webhooks import (
    WebhookRejected, webhook_delivery_input_schema, webhook_delivery_result_schema,
)
from tools import webhook_delivery_lab as delivery, webhook_lab as lab, webhook_public_pilot
from tools.tests.test_webhook_lab import AUDIENCE, BODY, EVENT, KEY, headers, post, post_at, raw_post, rows, server
from tools.webhook_lab import WebhookInbox, WebhookLabServer


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Core review seals require POSIX key ownership and locks")


@pytest.fixture
def state(core_state):
    """Package and validate a disposable receiver wheel, including its digest."""
    state = core_state
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest.update(capabilities={"provides": [], "consumes": []},
                    permissions=["data.read", "data.write", "process.spawn"])
    manifest["configuration_schema"] = {"type": "object", "properties": {}, "additionalProperties": False}
    definition = state.validated.application_extension.model_dump(mode="json")
    definition.update(connectors=[], command_bindings=[])
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.write(Path(__file__).with_name("webhook_reference_service.py"), "cap12_receiver.py")
    service_bytes = wheel.getvalue()
    definition["service"].update(sdk_version="1.3", entrypoint="cap12_receiver:create_service",
                                 artifact_sha256=hashlib.sha256(service_bytes).hexdigest())
    definition["storage"] = dict(schema_revision="0001", migration_entrypoint="cap12_receiver:get_migrations")
    definition["public_webhook"] = dict(contract_version=1, webhook_id="receive", path="/webhooks/demo",
                                        signature_profile="hmac_sha256_v1", handler_operation_id="receive_event")
    definition["operations"].append(dict(operation_id="receive_event", kind="command", audiences=["internal"],
        idempotency="required", audit="redacted", input_schema=webhook_delivery_input_schema(),
        output_schema=webhook_delivery_result_schema()))
    blob = package_bytes(state, manifest, definition, wheel=service_bytes)
    state.validated = validate_module_package(blob)
    state.archive = state.root / "modules" / (state.validated.sha256 + ".zip")
    state.archive.write_bytes(blob)
    with state.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            manifest=manifest, sha256=state.validated.sha256, size_bytes=len(blob), file_path=str(state.archive)))
        db.execute(update(ApplicationExtensionInstallation).where(ApplicationExtensionInstallation.id == 1)
                   .values(configuration={}))
    return state


def package_bytes(state, manifest, definition, *, wheel=None):
    artifact = definition["service"]["artifact"]
    output = io.BytesIO()
    with zipfile.ZipFile(state.archive) as previous, zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(artifact, previous.read(artifact) if wheel is None else wheel)
    return output.getvalue()


def target(state):
    with Session(state.engine) as db:
        installation = db.get(ApplicationExtensionInstallation, 1)
        return ReviewedWebhookTarget(installation.id, installation.instance_id, state.validated.sha256)


def bind(state, **changes):
    return ReviewedWebhookAdmission(state.engine, replace(target(state), **changes), audience=AUDIENCE)


def approve(state):
    assert allow(state, preview(state))["effective"] is True


def revoke(state):
    revision = state.manager.inspect(1)["grant_record_revision"]
    state.manager.revoke(1, actor_token=state.token, request_id=identity(), expected_revision=revision)


def test_no_binding_without_exact_active_review(state):
    with pytest.raises(WebhookRejected):
        bind(state)
    approve(state)
    for changes in ({"installation_id": 2}, {"instance_id": "b" * 24}, {"package_sha256": "1" * 64}):
        with pytest.raises(WebhookRejected):
            bind(state, **changes)
    assert bind(state).binding_sha256 == bind(state).binding_sha256


def test_approved_package_without_declaration_is_not_a_webhook_target(core_state):
    approve(core_state)
    with pytest.raises(WebhookRejected):
        bind(core_state)


def test_webhook_package_cannot_request_outside_resources_or_use_generic_dispatch(state):
    manifest = state.validated.manifest.model_dump(mode="json")
    manifest["permissions"].append("events.publish")
    with pytest.raises(ModulePackageError, match="cannot request additional"):
        validate_module_package(package_bytes(state, manifest, state.validated.application_extension.model_dump(mode="json")))
    with Session(state.engine) as db, pytest.raises(ApplicationGatewayError, match="dedicated delivery"):
        prepare_application_invocation(db.get(ApplicationExtensionInstallation, 1), db.get(ModulePackage, 1),
            ApplicationRuntimeSettings(), "receive_event",
            {"receipt_id": "1" * 32, "event_id": "event", "body_base64": "YQ=="},
            {"audience": "internal", "correlation_id": "1" * 32, "idempotency_key": "1" * 32},
            required_audience="internal")


def test_revocation_blocks_both_new_and_existing_receipts_and_reapproval_needs_new_binding(state, tmp_path):
    approve(state)
    admission = bind(state)
    original_grant = state.manager.inspect(1)["grant_record_revision"]
    with server(tmp_path, admission=admission) as listener:
        original = post(listener)
        assert original[0] == 202 and post(listener) == original
        assert state.manager.inspect(1)["grant_record_revision"] == original_grant
        saved = rows(tmp_path)
        revoke(state)
        assert post(listener) == post(listener, event_id="after-revoke") == (403, {"status": "refused"})
        approve(state)
        assert post(listener)[0] == 403
        assert rows(tmp_path) == saved
    with pytest.raises(ValueError, match="does not match"):
        WebhookLabServer(tmp_path, AUDIENCE, KEY, admission=bind(state))
    with pytest.raises(ValueError, match="does not match"):
        WebhookLabServer(tmp_path, AUDIENCE, KEY)  # Cannot reopen a reviewed inbox as standalone.
    assert rows(tmp_path) == saved


@pytest.mark.parametrize("change", ["disabled", "package"])
def test_stop_or_package_drift_closes_existing_listener(state, tmp_path, change):
    approve(state)
    admission = bind(state)
    with server(tmp_path, admission=admission) as listener:
        assert post(listener)[0] == 202
        with Session(state.engine) as db, authority_transaction(db) as mutation:
            if change == "disabled":
                mutation.advance_application_epoch(read_application_authority(db, 1))
                db.execute(update(ApplicationExtensionInstallation)
                           .where(ApplicationExtensionInstallation.id == 1)
                           .values(enabled=False, status="disabled"))
            else:
                db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(sha256="1" * 64))
        assert post(listener)[0] == 403
        assert post(listener, event_id="different")[0] == 403
    assert len(rows(tmp_path)) == 1


def test_revocation_between_package_prepare_and_durable_admission_wins(state, tmp_path, monkeypatch):
    approve(state)
    admission = bind(state)
    prepared = threading.Event()
    proceed = threading.Event()
    main_thread = threading.get_ident()
    prepare = state.manager._prepare

    def pause_after_prepare(*args, **kwargs):
        result = prepare(*args, **kwargs)
        if threading.get_ident() != main_thread:
            prepared.set()
            if not proceed.wait(4):
                raise AssertionError("Test did not release the package preparation barrier")
        return result

    monkeypatch.setattr(state.manager, "_prepare", pause_after_prepare)
    with server(tmp_path, admission=admission) as listener, ThreadPoolExecutor(max_workers=1) as client:
        response = client.submit(post, listener)
        try:
            assert prepared.wait(4)
            revoke(state)
        finally:
            proceed.set()
        assert response.result(timeout=5)[0] == 403
    assert rows(tmp_path) == []


def decide(admission, state, review, **changes):
    return admission.decide_delivery(**({
        "actor_token": state.token, "request_id": identity(), "binding_sha256": review["binding_sha256"],
        "expected_revision": review["revision"], "decision": "approve", "confirmed": True,
    } | changes))


def test_ingress_and_delivery_have_separate_current_approvals(state, tmp_path):
    approve(state)
    admission = bind(state)
    review = admission.review_delivery(actor_token=state.token)
    assert (review["state"], review["path"], review["handler_operation_id"]) == (
        "not_approved", "/webhooks/demo", "receive_event")
    with pytest.raises(WebhookRejected):
        admission.review_delivery(actor_token=state.user_token)
    with server(tmp_path, admission=admission) as listener:
        assert post_at(listener.server_address)[0] == 404
        assert post(listener)[0] == 202
        with pytest.raises(WebhookRejected), admission.hold_delivery():
            pytest.fail("Package consent must not approve delivery")
        for change in ({"confirmed": False}, {"actor_token": state.user_token}, {"binding_sha256": "f" * 64}):
            with pytest.raises(WebhookRejected):
                decide(admission, state, review, **change)
        request_id = identity()
        approved = decide(admission, state, review, request_id=request_id)
        assert approved["state"] == "approved"
        with bind(state).hold_delivery():
            assert len(rows(tmp_path)) == 1
        with pytest.raises(WebhookRejected):
            decide(admission, state, review)  # Stale preview cannot overwrite the current decision.
        other_audience = ReviewedWebhookAdmission(state.engine, target(state), audience="0" * 32)
        with pytest.raises(WebhookRejected), other_audience.hold_delivery():
            pytest.fail("Approval must not cross audiences")
        current = admission.review_delivery(actor_token=state.token)
        assert decide(admission, state, current, decision="revoke")["state"] == "revoked"
        historical = decide(admission, state, review, request_id=request_id)
        assert historical["historical"] is True and historical["state"] == "approved"
        with pytest.raises(WebhookRejected), admission.hold_delivery():
            pytest.fail("A historical decision cannot restore approval")
        assert post(listener, event_id="accepted-but-not-delivered")[0] == 202
    assert len(rows(tmp_path)) == 2


def test_delivery_approval_dies_with_grant_even_after_new_package_consent(state):
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    revoke(state)
    approve(state)
    for candidate in (admission, bind(state)):
        with pytest.raises(WebhookRejected), candidate.hold_delivery():
            pytest.fail("New package consent cannot restore delivery approval")
    assert bind(state).review_delivery(actor_token=state.token)["state"] == "stale"


def test_corrupt_delivery_seal_is_never_authority(state):
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    with state.engine.begin() as db:
        db.execute(update(ApplicationAuthorityAction).where(
            ApplicationAuthorityAction.request_id == admission._head_id).values(seal="0" * 64))
    with pytest.raises(WebhookRejected), admission.hold_delivery():
        pytest.fail("Corrupt sealed approval must fail closed")


@pytest.fixture
def receiver(state):
    selected = target(state)
    definition = state.validated.application_extension
    with tempfile.TemporaryDirectory(prefix="cap12-", dir="/tmp") as directory:
        root = Path(directory)
        keys = root / "keys"
        keys.mkdir(mode=0o700)
        (keys / f"{selected.instance_id}.key").write_bytes(secrets.token_bytes(32))
        instance = root / selected.instance_id
        (instance / "run").mkdir(parents=True)
        release = instance / "releases" / selected.package_sha256
        release.mkdir(parents=True)
        wheel = Path(definition.service.artifact).name
        with zipfile.ZipFile(state.archive) as archive:
            (release / wheel).write_bytes(archive.read(definition.service.artifact))
        (instance / "active.json").write_text(json.dumps(dict(
            instance_id=selected.instance_id, module_id=definition.module_id, version=definition.version,
            sha256=selected.package_sha256, wheel=wheel, entrypoint=definition.service.entrypoint,
            storage=definition.storage.model_dump(mode="json"), configuration={},
            operations=[op.model_dump(mode="json") for op in definition.operations],
        )), encoding="utf-8")
        path = instance / "run" / "service.sock"
        with state.engine.begin() as db:
            db.execute(update(ApplicationExtensionInstallation).where(ApplicationExtensionInstallation.id == 1)
                       .values(socket_path=str(path)))
        with (root / "host.log").open("w+") as log:
            child = launch_host(selected.instance_id, root, keys, log)
            try:
                deadline = time.monotonic() + 8
                while not path.is_socket():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        pytest.fail("Disposable webhook host did not start: " + log.read(2048))
                    time.sleep(0.02)
                yield ApplicationRuntimeSettings(root=root, key_root=keys), instance / "data" / "state.sqlite3", path
            finally:
                if child.poll() is None:
                    stop_host(child)


def received(database):
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute("SELECT receipt_id, event_id, body FROM received ORDER BY rowid").fetchall()


def accepted_receipt(listener, body=BODY, event_id=EVENT):
    status, result = post(listener, body=body, event_id=event_id)
    assert status == 202
    return result["receipt_id"]


def test_signed_receipt_delivers_exact_bytes_once_and_records_outcome(state, receiver, tmp_path):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    with server(tmp_path, admission=admission) as listener:
        receipt_id = accepted_receipt(listener)
        assert received(database) == []  # A successful POST does not dispatch.
        with pytest.raises(WebhookRejected):
            delivery.deliver_one(listener.inbox, admission, settings, receipt_id)
        decide(admission, state, admission.review_delivery(actor_token=state.token))
        first = delivery.deliver_one(listener.inbox, admission, settings, receipt_id)
        assert first.status == "delivered"
        assert rows(tmp_path)[0][3] is None
        assert accepted_receipt(listener) == receipt_id
        reopened = WebhookInbox(tmp_path, AUDIENCE, admission.binding_sha256)
        assert delivery.deliver_one(reopened, admission, settings, receipt_id) == first
        refused_id = accepted_receipt(listener, b"reject", "receiver-refuses")
        assert delivery.deliver_one(reopened, admission, settings, refused_id).status == "rejected"
    assert received(database) == [(receipt_id, EVENT, BODY)]


@pytest.mark.parametrize("fault", ["lost", "wrong_request"])
def test_unconfirmed_receipt_is_not_replayed_after_receiver_commit(state, receiver, tmp_path, monkeypatch, fault):
    settings, database, _ = receiver
    now = int(time.time())
    monkeypatch.setattr(lab, "_retention_now", lambda: now)
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    real_read = delivery.read_frame

    def drop_confirmation(*args, **kwargs):
        reply = real_read(*args, **kwargs)
        if fault == "lost":
            raise TimeoutError
        _, key = delivery._transport(host_target, settings)
        return delivery.sign_message({**reply, "request_id": "f" * 32}, key)

    with admission.hold_delivery() as host_target:
        pass
    with server(tmp_path, admission=admission) as listener:
        receipt_id = accepted_receipt(listener)
        with monkeypatch.context() as patch:
            patch.setattr(delivery, "read_frame", drop_confirmation)
            cycle = delivery.consume_pending(listener.inbox, admission, settings)
        assert cycle.status == "paused"
        attempt, = cycle.attempts
        assert attempt.receipt_id == receipt_id
        assert attempt.status == "unconfirmed"
        assert received(database) == [(receipt_id, EVENT, BODY)]
        assert rows(tmp_path)[0][3] == BODY
    reopened = WebhookInbox(tmp_path, AUDIENCE, admission.binding_sha256)
    now += lab.BODY_RETENTION_SECONDS
    assert delivery.deliver_one(reopened, admission, settings, receipt_id) == attempt
    assert rows(tmp_path)[0][3] is None
    assert received(database) == [(receipt_id, EVENT, BODY)]


def test_expired_pending_receipt_cannot_be_rearmed_with_fresh_signature(state, receiver, tmp_path, monkeypatch):
    settings, database, _ = receiver
    now = int(time.time())
    monkeypatch.setattr(lab, "_retention_now", lambda: now)
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    with server(tmp_path, admission=admission) as listener:
        receipt_id = accepted_receipt(listener)
        now += lab.BODY_RETENTION_SECONDS
        with pytest.raises(WebhookRejected):
            delivery.deliver_one(listener.inbox, admission, settings, receipt_id)
        assert rows(tmp_path)[0][3] is None
    # Simulate a backward clock step and a fresh signed submission after restart.
    now -= lab.BODY_RETENTION_SECONDS
    with server(tmp_path, admission=admission) as listener:
        assert accepted_receipt(listener) == receipt_id
        with pytest.raises(WebhookRejected):
            delivery.deliver_one(listener.inbox, admission, settings, receipt_id)
    assert received(database) == []


def test_delivery_wait_does_not_lock_core_or_allow_new_claim_after_revocation(state, receiver, tmp_path, monkeypatch):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    real_read = delivery.read_frame
    waiting, proceed = threading.Event(), threading.Event()

    def wait_after_reply(*args, **kwargs):
        reply = real_read(*args, **kwargs)
        waiting.set()
        assert proceed.wait(5)
        return reply

    monkeypatch.setattr(delivery, "read_frame", wait_after_reply)
    with server(tmp_path, admission=admission) as listener, ThreadPoolExecutor(max_workers=1) as worker:
        first = accepted_receipt(listener)
        second = accepted_receipt(listener, event_id="next-event")
        result = worker.submit(delivery.deliver_one, listener.inbox, admission, settings, first)
        try:
            assert waiting.wait(5)
            duplicate = delivery.deliver_one(listener.inbox, admission, settings, first)
            assert duplicate.status == "unconfirmed"
            assert decide(admission, state, admission.review_delivery(actor_token=state.token),
                          decision="revoke")["state"] == "revoked"
            with pytest.raises(WebhookRejected):
                delivery.deliver_one(listener.inbox, admission, settings, second)
        finally:
            proceed.set()
        assert result.result(timeout=5) == replace(duplicate, status="delivered")
    assert received(database) == [(first, EVENT, BODY)]


def test_missing_host_is_not_dispatched_and_wrong_socket_is_not_admitted(state, receiver, tmp_path):
    settings, database, path = receiver
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    with server(tmp_path, admission=admission) as listener:
        receipt_id = accepted_receipt(listener)
        with pytest.raises(WebhookRejected):
            delivery.deliver_one(listener.inbox, admission, ApplicationRuntimeSettings(), receipt_id)
        missing = path.with_name("owned-test.sock")
        path.rename(missing)
        try:
            attempt = delivery.deliver_one(listener.inbox, admission, settings, receipt_id)
            assert attempt.status == "not_dispatched"
        finally:
            missing.rename(path)
        assert delivery.deliver_one(listener.inbox, admission, settings, receipt_id) == attempt
    assert received(database) == []


def test_consumer_claims_in_order_with_a_fixed_batch_limit(state, receiver, tmp_path, monkeypatch):
    settings, database, path = receiver
    now = int(time.time())
    monkeypatch.setattr(lab, "_retention_now", lambda: now)
    approve(state)
    admission = bind(state)
    with server(tmp_path, admission=admission) as listener:
        expired = accepted_receipt(listener, event_id="expired")
        now += lab.BODY_RETENTION_SECONDS
        entries = [(accepted_receipt(listener, event_id=f"event-{i}"), f"event-{i}", BODY) for i in range(5)]
        assert delivery.consume_pending(listener.inbox, admission, settings) == delivery.DeliveryCycle("blocked", ())
        decide(admission, state, admission.review_delivery(actor_token=state.token))
        missing = path.with_name("owned-test.sock")
        path.rename(missing)
        try:
            assert delivery.consume_pending(listener.inbox, admission, settings) == delivery.DeliveryCycle("blocked", ())
        finally:
            missing.rename(path)
        first = delivery.consume_pending(listener.inbox, admission, settings)
        assert first.status == "limit_reached"
        assert [(a.receipt_id, a.status) for a in first.attempts] == [(e[0], "delivered") for e in entries[:4]]
        assert received(database) == entries[:4]
        second = delivery.consume_pending(listener.inbox, admission, settings)
        assert second.status == "drained"
        assert [(a.receipt_id, a.status) for a in second.attempts] == [(entries[4][0], "delivered")]
        assert delivery.consume_pending(listener.inbox, admission, settings) == delivery.DeliveryCycle("drained", ())
        with pytest.raises(WebhookRejected):
            delivery.deliver_one(listener.inbox, admission, settings, expired)
    assert received(database) == entries


def test_consumer_stops_after_current_attempt_when_approval_is_revoked(state, receiver, tmp_path, monkeypatch):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    approved = decide(admission, state, admission.review_delivery(actor_token=state.token))
    original_read = delivery.read_frame

    def revoke_after_reply(*args, **kwargs):
        reply = original_read(*args, **kwargs)
        assert decide(admission, state, approved, decision="revoke")["state"] == "revoked"
        return reply

    monkeypatch.setattr(delivery, "read_frame", revoke_after_reply)
    with server(tmp_path, admission=admission) as listener:
        first = accepted_receipt(listener)
        accepted_receipt(listener, event_id="blocked-next")
        cycle = delivery.consume_pending(listener.inbox, admission, settings)
        assert cycle.status == "blocked"
        assert [(a.receipt_id, a.status) for a in cycle.attempts] == [(first, "delivered")]
    assert received(database) == [(first, EVENT, BODY)]


_CONSUMER_CHILD = """
from dataclasses import asdict
import json, os, sys
from pathlib import Path
from sqlalchemy import create_engine
from backend.config import ApplicationRuntimeSettings
import backend.db.permission  # Register the User mapper's relationship targets.
import backend.db.role
from backend.services import application_authority_management as management
from backend.services.application_webhook_admission import ReviewedWebhookAdmission, ReviewedWebhookTarget
from tools import webhook_delivery_lab as delivery
from tools.webhook_lab import WebhookInbox

args = json.loads(sys.argv[1])
engine = create_engine(args['db'])
manager = management.ApplicationAuthorityManager(engine, uploads_root=args['uploads'],
    core_version=args['core_version'], review_key_directory=args['review_keys'])
management.configured_manager = lambda engine: manager
admission = ReviewedWebhookAdmission(engine, ReviewedWebhookTarget(**args['target']), audience=args['audience'])
inbox = WebhookInbox(Path(args['inbox']), args['audience'], admission.binding_sha256)
if args['exit_after_reply']:
    read = delivery.read_frame
    def exit_after_reply(*args, **kwargs):
        read(*args, **kwargs)
        os._exit(17)
    delivery.read_frame = exit_after_reply
print(json.dumps(asdict(delivery.consume_pending(inbox, admission, ApplicationRuntimeSettings(**args['settings'])))))
"""


def run_consumer_process(state, settings, directory, *, exit_after_reply=False):
    args = dict(db=str(state.engine.url), uploads=str(state.root), core_version=state.manager.core_version,
                review_keys=str(state.key_directory), target=asdict(target(state)), audience=AUDIENCE,
                inbox=str(directory), settings={"root": str(settings.root), "key_root": str(settings.key_root)},
                exit_after_reply=exit_after_reply)
    return subprocess.run([sys.executable, "-c", _CONSUMER_CHILD, json.dumps(args)],
                          cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20)


def test_restarted_consumer_never_replays_after_process_exit(state, receiver, tmp_path):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    with server(tmp_path, admission=admission) as listener:
        first = accepted_receipt(listener)
        second = accepted_receipt(listener, event_id="new-after-restart")
        exited = run_consumer_process(state, settings, tmp_path, exit_after_reply=True)
        assert exited.returncode == 17, exited.stderr
        assert received(database) == [(first, EVENT, BODY)]
        assert accepted_receipt(listener) == first
        restarted = run_consumer_process(state, settings, tmp_path)
        assert restarted.returncode == 0, restarted.stderr
        result = json.loads(restarted.stdout)
        assert result["status"] == "drained"
        assert [(a["receipt_id"], a["status"]) for a in result["attempts"]] == [(second, "delivered")]
        assert delivery.deliver_one(listener.inbox, admission, settings, first).status == "unconfirmed"
    assert received(database) == [(first, EVENT, BODY), (second, "new-after-restart", BODY)]


_PUBLIC_WEB_CHILD = """
from pathlib import Path
import sys
from three_mm_public_web.server import create_server
from three_mm_public_web.webhook_pilot import WebhookPilotClient

runtime, route, broker, uid, *private_files = sys.argv[1:]
for name in private_files:
    try:
        with Path(name).open('rb'):
            raise RuntimeError('Public Web can open broker-private data')
    except PermissionError:
        pass
pilot = WebhookPilotClient(route, Path(broker), int(uid) if uid else None) if broker else None
with create_server(Path(runtime), port=0, webhook_pilot=pilot) as server:
    print(f'CAP12 Public Web {server.server_port}', flush=True)
    server.serve_forever()
"""


@contextmanager
def public_web_process(runtime_socket, route, pilot=None, *, user=None, group=None, private_files=()):
    args = [sys.executable, '-c', _PUBLIC_WEB_CHILD, str(runtime_socket), route,
            str(pilot.socket_path) if pilot is not None else '',
            str(pilot.broker_uid) if pilot is not None and pilot.broker_uid is not None else '',
            *(str(path) for path in private_files)]
    principal = {} if user is None else dict(user=user, group=group, extra_groups=[])
    with subprocess.Popen(args, cwd=Path(__file__).resolve().parents[2], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, **principal) as child:
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            line = child.stdout.readline() if ready else ''
            match = re.fullmatch(r'CAP12 Public Web ([0-9]+)\n', line)
            assert match, f'Disposable Public Web did not start: {line}'
            port = int(match[1])
            yield SimpleNamespace(server_address=('127.0.0.1', port), authority=f'127.0.0.1:{port}', route=route)
        finally:
            if child.poll() is None:
                stop_host(child)


@pytest.mark.skipif(sys.platform != 'linux', reason='Requires Linux Unix peer credentials')
def test_public_web_pilot_uses_real_http_ingress_and_never_replays(state, receiver, tmp_path):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    key = secrets.token_bytes(32)
    unused_runtime = settings.root / 'unused-public.sock'
    with public_web_process(unused_runtime, admission.path) as disabled:
        with closing(HTTPConnection(*disabled.server_address, timeout=5)) as client:
            client.request('POST', disabled.route, BODY, headers(BODY, key=key))
            with client.getresponse() as response:
                assert response.status == 405  # Default configuration keeps the legacy refusal.
    assert not (tmp_path / lab.DATABASE).exists()
    with ExitStack() as stack:
        with webhook_public_pilot.pilot_ingress(tmp_path, admission, key) as (pilot, inbox):
            listener = stack.enter_context(public_web_process(unused_runtime, admission.path, pilot))
            assert post(listener, key=KEY) == (403, {'status': 'refused'})
            framing = [f'{name}: {value}' for name, value in headers(BODY, key=key).items()]
            framing.append(f'Content-Length: {len(BODY)}')
            for path in (listener.route + '?unexpected=1', listener.route.replace('/demo', '/%64emo'),
                         '/' + listener.route):
                assert raw_post(listener, framing, body=BODY, path=path)[0] == 404
            assert raw_post(listener, framing + ['Authorization: not-forwarded'], body=BODY, path=listener.route)[0] == 400
            assert raw_post(listener, framing + ['X-3mm-Webhook-Id: duplicate'], body=BODY, path=listener.route)[0] == 400
            assert raw_post(listener, framing[:-1] + ['Content-Length: 65537'], path=listener.route)[0] == 413
            assert rows(tmp_path) == []
            first = post(listener, key=key)
            second = post(listener, key=key, event_id='new-after-restart')
            assert first[0] == second[0] == 202
            first_id, second_id = first[1]['receipt_id'], second[1]['receipt_id']
            assert post(listener, key=key) == first
            assert post(listener, key=key, body=BODY + b'!')[0] == 409
            assert received(database) == []  # HTTP acknowledges the inbox, not a service execution.
            crashed = run_consumer_process(state, settings, tmp_path, exit_after_reply=True)
            assert crashed.returncode == 17, crashed.stderr
            assert received(database) == [(first_id, EVENT, BODY)]
            restarted = run_consumer_process(state, settings, tmp_path)
            assert restarted.returncode == 0, restarted.stderr
            assert [(a['receipt_id'], a['status']) for a in json.loads(restarted.stdout)['attempts']] == [
                (second_id, 'delivered')]
            assert post(listener, key=key) == first
            revoke(state)
            assert post(listener, key=key) == (403, {'status': 'refused'})
            assert post(listener, key=key, event_id='after-revoke')[0] == 403
            assert delivery.consume_pending(inbox, admission, settings) == delivery.DeliveryCycle('blocked', ())
        # Stopping only the broker closes intake even while the HTTP process is alive.
        assert post(listener, key=key) == (503, {'status': 'refused'})
    assert received(database) == [(first_id, EVENT, BODY), (second_id, 'new-after-restart', BODY)]
    assert len(rows(tmp_path)) == 2


@pytest.mark.skipif(sys.platform != 'linux', reason='Requires Linux Unix peer credentials')
def test_public_web_rotates_only_the_endpoint_key_without_rearming_receipts(state, receiver, tmp_path):
    settings, database, _ = receiver
    approve(state)
    admission = bind(state)
    decide(admission, state, admission.review_delivery(actor_token=state.token))
    key, replacement = secrets.token_bytes(32), secrets.token_bytes(32)
    unused_runtime = settings.root / 'unused-public.sock'
    with webhook_public_pilot.pilot_ingress(tmp_path, admission, key) as (pilot, inbox):
        with public_web_process(unused_runtime, admission.path, pilot) as listener:
            first = post(listener, key=key)
            assert first[0] == 202
            assert delivery.consume_pending(inbox, admission, settings).attempts[0].status == 'delivered'
            with pytest.raises(ValueError, match='Stop the active webhook pilot'):
                with webhook_public_pilot.pilot_ingress(tmp_path, admission, replacement):
                    pytest.fail('A second broker acquired the same inbox')
            assert post(listener, key=key) == first
    with webhook_public_pilot.pilot_ingress(tmp_path, admission, replacement) as (pilot, inbox):
        with public_web_process(unused_runtime, admission.path, pilot) as listener:
            for event_id in (EVENT, 'after-rotation'):
                assert post(listener, key=key, event_id=event_id)[0] == 403
            assert post(listener, key=replacement) == first
            assert post(listener, key=replacement, body=BODY + b'!')[0] == 409
            second = post(listener, key=replacement, event_id='after-rotation')
            assert second[0] == 202
            cycle = delivery.consume_pending(inbox, admission, settings)
            assert [(attempt.receipt_id, attempt.status) for attempt in cycle.attempts] == [
                (second[1]['receipt_id'], 'delivered')]
    assert received(database) == [(first[1]['receipt_id'], EVENT, BODY),
                                  (second[1]['receipt_id'], 'after-rotation', BODY)]


@pytest.mark.skipif(sys.platform != 'linux' or getattr(os, 'geteuid', lambda: -1)() != 0,
                    reason='Disposable Linux root driver for existing, distinct principals')
def test_public_web_pilot_separates_service_principals(state, tmp_path):
    import pwd

    public, stranger = pwd.getpwnam('www-data'), pwd.getpwnam('nobody')
    assert len({os.geteuid(), public.pw_uid, stranger.pw_uid}) == 3
    approve(state)
    admission = bind(state)
    key = secrets.token_bytes(32)
    key_path = tmp_path / 'test-signing-key'
    with os.fdopen(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(key)
    unused_runtime = tmp_path / 'unused-public.sock'
    private_files = (key_path, tmp_path / lab.DATABASE)
    with tempfile.TemporaryDirectory(prefix='cap12-peers-', dir='/tmp') as directory:
        socket_dir = Path(directory)
        os.chown(socket_dir, os.geteuid(), public.pw_gid)
        socket_dir.chmod(0o2710)
        with webhook_public_pilot.pilot_ingress(tmp_path, admission, key_path.read_bytes(),
                public_uid=public.pw_uid, socket_dir=socket_dir) as (pilot, _inbox):
            assert pilot.socket_path.stat().st_gid == public.pw_gid
            # The wrong UID can reach the socket through the same group but
            # the kernel credential check refuses before intake.
            with public_web_process(unused_runtime, admission.path, pilot, user=stranger.pw_uid,
                                    group=public.pw_gid, private_files=private_files) as listener:
                assert post(listener, key=key)[0] == 503
            # Public Web authenticates the server's kernel UID in return.
            with public_web_process(unused_runtime, admission.path, replace(pilot, broker_uid=stranger.pw_uid),
                                    user=public.pw_uid, group=public.pw_gid, private_files=private_files) as listener:
                assert post(listener, key=key)[0] == 503
            assert rows(tmp_path) == []
            with public_web_process(unused_runtime, admission.path, pilot, user=public.pw_uid,
                                    group=public.pw_gid, private_files=private_files) as listener:
                first = post(listener, key=key)
                assert first[0] == 202 and post(listener, key=key) == first
            assert len(rows(tmp_path)) == 1
        assert not (socket_dir / 'ingress.sock').exists()
