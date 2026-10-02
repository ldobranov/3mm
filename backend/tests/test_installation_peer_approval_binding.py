"""Real signatures, durable SQLite, API and SDK envelopes; no live peers."""

import copy
import json
from datetime import UTC, datetime, timedelta

import backend.database
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.installation_peer import (
    InstallationPeerInbound,
    InstallationPeerOutbound,
)
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.routes.installation_peers import router
from backend.services import installation_peers as peers
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.module_packages import validate_module_package, ModulePackageError
from backend.tests import test_installation_peers as legacy
from backend.tests.test_installation_peers import pair, sender_call, MODULE, ORIGIN
from backend.tests.test_module_packages import application_package
from backend.tests.test_installation_identity_platform import MemoryConnection
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from deployment.installation_peer_recovery import quarantine_restored_installation_peers
from three_mm_application_sdk import (
    ApplicationPlatformClient,
    ApplicationPlatformError,
    OperationContext,
)
from three_mm_protocol.installation_peer import (
    PeerEnrollmentStartV1,
    PeerCredentialV1,
    PEER_PREFIX,
)
from three_mm_protocol.installation_peer_v2 import (
    PEER_V2_PREFIX,
    PeerEnrollmentMetadataV2,
    PeerInboundStatusV2,
    enrollment_metadata,
    parse_peer,
)

INTENT = "fixture_intent_4dd1"


@pytest.fixture
def pair_v2(request, monkeypatch):
    original = legacy.peer_package

    def package_v2():
        _, definition, manifest = original()
        definition["service"]["sdk_version"] = "1.3"
        definition["peer_receiver"]["peer_version"] = 2
        bootstrap = next(
            item
            for item in definition["operations"]
            if item["operation_id"] == "peer_enroll"
        )
        bootstrap["input_schema"]["properties"]["enrollment_metadata"] = {
            "type": "object"
        }
        bootstrap["input_schema"]["required"].append("enrollment_metadata")
        return (
            application_package(definition=definition, manifest_value=manifest),
            definition,
            manifest,
        )

    monkeypatch.setattr(legacy, "peer_package", package_v2)
    fixture = request.getfixturevalue("pair")
    with Session(fixture.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        old = db.get(InstallationPeerOutbound, fixture.sender.link_id)
        consent = old.consent
        peers.revoke_peer(db, app, old.link_id, "outbound", user_id=1)
        result = peers.create_outbound(
            db,
            app,
            origin=ORIGIN,
            receiver_identity=fixture.receiver.identity,
            target_module_id=MODULE,
            consent=consent,
            user_id=1,
            peer_version=2,
            application_intent=INTENT,
        )
        fixture.sender.link_id = result["link_id"]
    return fixture


def inbound(fixture):
    with Session(fixture.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        result = peers.list_peers(db, app)["inbound"][0]
        PeerInboundStatusV2.model_validate(result)
        return result


def approve(fixture, review=None):
    review = review or inbound(fixture)
    metadata = review["verified_metadata"]
    with Session(fixture.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        return peers.approve_inbound(
            db,
            app,
            review["binding_id"],
            review["generation"],
            expected_metadata_revision=metadata["consent_revision"],
            expected_metadata_hash=metadata["metadata_hash"],
            user_id=1,
        )


def activate(fixture):
    assert sender_call(fixture, peers.enroll_outbound)["state"] == "pending"
    result = approve(fixture)
    assert sender_call(fixture, peers.enroll_outbound)["state"] == "active"
    return result


def update(fixture, consent):
    with Session(fixture.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        row = db.get(InstallationPeerOutbound, fixture.sender.link_id)
        return peers.update_consent(
            db, app, row.link_id, consent, row.consent_revision, user_id=1
        )


def signed_report(fixture, projection_change=None):
    with Session(fixture.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, fixture.sender.link_id)
        app = db.scalar(select(ApplicationExtensionInstallation))
        projection = peers.installation_projection(db, app, row.link_id).model_dump(
            mode="json"
        )
        if projection_change:
            projection_change(projection)
        request = peers.signed_outbound_request(
            db,
            row,
            PEER_V2_PREFIX + "/report",
            {
                "report_id": "report_" + "a" * 32,
                "projection": projection,
            },
        )
        db.commit()
        return request


def test_metadata_verified_before_review_and_bound_into_credential_and_report(pair_v2):
    result = sender_call(pair_v2, peers.enroll_outbound)
    metadata = result["enrollment_metadata"]
    assert metadata["application_intent"] == INTENT
    review = inbound(pair_v2)
    assert review["verified_metadata"] == metadata
    args, kwargs = pair_v2.captured[-1]
    assert args[4]["enrollment_metadata"] == metadata
    context = OperationContext.from_platform(args[5])
    assert (
        context.machine.generation == review["generation"] and context.user_id is None
    )
    assert metadata["metadata_hash"] in context.idempotency_key
    assert kwargs["before_dispatch"]() is True
    credential = approve(pair_v2)["credential"]
    assert credential["claims"]["credential_version"] == 2
    assert credential["claims"]["enrollment_metadata"] == metadata
    sender_call(pair_v2, peers.enroll_outbound)
    assert (
        sender_call(pair_v2, peers.report_outbound, "report_" + "1" * 32)["status"]
        == "accepted"
    )


def test_challenged_metadata_is_not_exposed_as_verified(pair_v2):
    with Session(pair_v2.sender.engine) as db:
        start = db.get(InstallationPeerOutbound, pair_v2.sender.link_id).start_request
    pair_v2.transport(ORIGIN, PEER_V2_PREFIX + "/enrollments/start", start)
    review = inbound(pair_v2)
    assert review["state"] == "challenged" and review["verified_metadata"] is None
    with Session(pair_v2.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        with pytest.raises(peers.InstallationPeerError):
            peers.approve_inbound(
                db,
                app,
                review["binding_id"],
                review["generation"],
                expected_metadata_revision=1,
                expected_metadata_hash=start["enrollment_metadata"]["metadata_hash"],
            )


@pytest.mark.parametrize(
    "field",
    [
        "application_intent",
        "consent",
        "revision",
        "hash",
        "module",
        "origin",
        "identity",
    ],
)
def test_signed_start_cannot_be_substituted(pair_v2, field):
    with Session(pair_v2.sender.engine) as db:
        start = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair_v2.sender.link_id).start_request
        )
    metadata = start["enrollment_metadata"]
    if field in {"application_intent", "consent", "revision"}:
        start["enrollment_metadata"] = enrollment_metadata(
            "different_intent" if field == "application_intent" else INTENT,
            {} if field == "consent" else metadata["consent"],
            2 if field == "revision" else 1,
        ).model_dump(mode="json")
    elif field == "hash":
        metadata["metadata_hash"] = "0" * 64
    elif field == "module":
        start["target_module_id"] = "org.3mm.other-reference"
    elif field == "origin":
        start["receiver_challenge"]["audience"] = "https://other.test"
    else:
        start["sender"]["installation_id"] = "inst_" + "0" * 32
    assert (
        pair_v2.client.post(
            PEER_V2_PREFIX + "/enrollments/start", json=start
        ).status_code
        == 409
    )


def test_completion_hash_and_review_cas_cannot_be_replaced(pair_v2):
    sender_call(pair_v2, peers.enroll_outbound)
    with Session(pair_v2.sender.engine) as db:
        complete = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair_v2.sender.link_id).complete_request
        )
    complete["metadata_hash"] = "0" * 64
    assert (
        pair_v2.client.post(
            PEER_V2_PREFIX + "/enrollments/complete", json=complete
        ).status_code
        == 409
    )
    review = inbound(pair_v2)
    url = f"/api/v1/installation-peers/applications/{MODULE}/inbound/{review['binding_id']}/approve"
    for changed in (
        {},
        {
            "expected_metadata_revision": 2,
            "expected_metadata_hash": review["verified_metadata"]["metadata_hash"],
        },
        {"expected_metadata_revision": 1, "expected_metadata_hash": "0" * 64},
    ):
        response = pair_v2.client.post(
            url, json={"expected_generation": review["generation"], **changed}
        )
        assert response.status_code == 409
    approved = approve(pair_v2)
    assert approved == approve(pair_v2)  # exact retry only, including metadata
    assert (
        pair_v2.client.post(
            url, json={"expected_generation": review["generation"]}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "consent",
    [
        {},
        {"summary_fields": ["core_version"]},
        {"summary_fields": ["core_version", "sdk_version", "protocol_version"]},
    ],
)
def test_any_changed_consent_stops_reports_and_requires_fresh_approval(
    pair_v2, consent
):
    activate(pair_v2)
    old_review = inbound(pair_v2)
    old_request = signed_report(pair_v2)
    sender_call(pair_v2, peers.report_outbound, "report_" + "2" * 32)
    changed = update(pair_v2, consent)
    assert changed["state"] == "new" and changed["consent_revision"] == 2
    with Session(pair_v2.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair_v2.sender.link_id)
        assert (
            row.credential
            is row.report_id
            is row.report_projection
            is row.report_result
            is None
        )
    with pytest.raises(peers.InstallationPeerError, match="not active"):
        sender_call(pair_v2, peers.report_outbound, "report_" + "2" * 32)
    assert sender_call(pair_v2, peers.enroll_outbound)["state"] == "pending"
    fresh = inbound(pair_v2)
    assert fresh["generation"] > old_review["generation"]
    assert fresh["verified_metadata"]["consent_revision"] == 2
    with pytest.raises(peers.InstallationPeerError):
        approve(pair_v2, old_review)
    assert (
        pair_v2.client.post(
            old_request.path,
            json=old_request.model_dump(mode="json"),
            headers={"Authorization": "ThreeMM-Peer"},
        ).status_code
        == 409
    )
    approve(pair_v2)
    sender_call(pair_v2, peers.enroll_outbound)
    assert (
        sender_call(pair_v2, peers.report_outbound, "report_" + "3" * 32)["status"]
        == "accepted"
    )


def test_reordered_same_selection_does_not_create_new_approval(pair_v2):
    activate(pair_v2)
    with Session(pair_v2.sender.engine) as db:
        consent = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair_v2.sender.link_id).consent
        )
    for field in ("summary_fields", "node_ids", "node_fields"):
        consent[field].reverse()
    assert update(pair_v2, consent)["consent_revision"] == 1


@pytest.mark.parametrize("change", ["revision", "summary", "nodes", "fields"])
def test_even_signed_projection_must_match_receiver_review(pair_v2, change):
    activate(pair_v2)

    def mutate(projection):
        if change == "revision":
            projection["consent_revision"] = 2
        elif change == "summary":
            projection["summary"]["protocol_version"] = {
                "status": "known",
                "value": "1.0",
            }
        elif change == "nodes":
            projection["nodes"] = []
        else:
            projection["nodes"][0]["fields"].pop("online")

    request = signed_report(pair_v2, mutate)
    before = len(pair_v2.captured)
    response = pair_v2.client.post(
        request.path,
        json=request.model_dump(mode="json"),
        headers={"Authorization": "ThreeMM-Peer"},
    )
    assert response.status_code == 409 and len(pair_v2.captured) == before


@pytest.mark.parametrize("phase", ["start", "complete", "rotate", "report"])
def test_lost_reply_and_restart_retry_exact_durable_episode(pair_v2, phase):
    if phase in {"rotate", "report"}:
        activate(pair_v2)
    function = (
        peers.rotate_outbound
        if phase == "rotate"
        else peers.report_outbound if phase == "report" else peers.enroll_outbound
    )
    args = ["report_" + "4" * 32] if phase == "report" else []

    def lose(origin, path, payload):
        result = pair_v2.transport(origin, path, payload)
        if path.endswith("/" + phase):
            raise peers.InstallationPeerError("fixture lost reply")
        return result

    with pytest.raises(peers.InstallationPeerError, match="lost reply"):
        sender_call(pair_v2, function, *args, transport=lose)
    result = sender_call(
        pair_v2, function, *args
    )  # new SQLite sessions, persisted state
    assert result["status" if phase == "report" else "state"] in {
        "accepted",
        "pending",
        "active",
    }
    if phase in {"start", "complete"}:
        approve(pair_v2)
        assert sender_call(pair_v2, peers.enroll_outbound)["state"] == "active"
    assert inbound(pair_v2)["generation"] == (2 if phase == "rotate" else 1)


@pytest.mark.parametrize("phase", ["enroll", "rotate", "report"])
@pytest.mark.parametrize("action", ["consent", "withdraw"])
def test_local_change_fences_delayed_success(pair_v2, phase, action):
    if phase != "enroll":
        activate(pair_v2)

    def delayed(origin, path, payload):
        result = pair_v2.transport(origin, path, payload)
        if action == "consent":
            update(pair_v2, {})
        else:
            with Session(pair_v2.sender.engine) as db:
                app = db.scalar(select(ApplicationExtensionInstallation))
                peers.revoke_peer(
                    db, app, pair_v2.sender.link_id, "outbound", user_id=1
                )
        return result

    function = {
        "enroll": peers.enroll_outbound,
        "rotate": peers.rotate_outbound,
        "report": peers.report_outbound,
    }[phase]
    args = ["report_" + "5" * 32] if phase == "report" else []
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair_v2, function, *args, transport=delayed)
    with Session(pair_v2.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair_v2.sender.link_id)
        assert row.state == ("new" if action == "consent" else "revoked")
        assert row.credential is row.report_result is None


def test_restore_quarantines_metadata_and_uninstall_does_not_revive_it(pair_v2):
    activate(pair_v2)
    old = inbound(pair_v2)
    quarantine_restored_installation_peers(pair_v2.sender.database)
    quarantine_restored_installation_peers(pair_v2.receiver.database)
    assert inbound(pair_v2)["verified_metadata"] is None
    with pytest.raises(peers.InstallationPeerError):
        approve(pair_v2, old)
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair_v2, peers.enroll_outbound)
    with Session(pair_v2.receiver.engine) as db:
        peers.invalidate_application_peers(db, MODULE)
        db.commit()
        row = db.scalar(select(InstallationPeerInbound))
        assert row.start_request["enrollment_metadata"] == old["verified_metadata"]
        assert row.state == "revoked" and row.credential is None


@pytest.mark.parametrize(
    "intent", ["", "x" * 257, "https://intent.test/token", "with space", "кирилица"]
)
def test_intent_is_bounded_opaque_reference_not_an_unbounded_payload(intent):
    with pytest.raises(ValidationError):
        enrollment_metadata(intent, {})


def test_metadata_versions_hash_and_extra_context_are_strict():
    value = enrollment_metadata(INTENT, {}).model_dump(mode="json")
    for changed in (
        {"metadata_version": True},
        {"consent_revision": True},
        {"metadata_hash": "0" * 64},
        {"user_id": 1},
    ):
        with pytest.raises(ValidationError):
            PeerEnrollmentMetadataV2.model_validate({**value, **changed})


@pytest.mark.parametrize("claims", [None, "not-an-object", [], 2, True])
def test_malformed_credential_is_validation_error_not_attribute_error(claims):
    with pytest.raises(ValueError):
        parse_peer(PeerCredentialV1, {"claims": claims})


def test_v1_is_not_a_metadata_downgrade_and_capability_is_explicit(pair_v2):
    with Session(pair_v2.sender.engine) as db:
        row = db.get(InstallationPeerOutbound, pair_v2.sender.link_id)
        with pytest.raises(ValidationError):
            PeerEnrollmentStartV1.model_validate(row.start_request)
        assert (
            pair_v2.client.post(
                PEER_PREFIX + "/enrollments/start", json=row.start_request
            ).status_code
            == 409
        )
        stripped = {
            key: value
            for key, value in row.start_request.items()
            if key != "enrollment_metadata"
        }
        stripped["peer_version"] = 1
    assert (
        pair_v2.client.post(
            PEER_PREFIX + "/enrollments/start", json=stripped
        ).status_code
        == 409
    )
    caps = pair_v2.client.get(PEER_V2_PREFIX + "/capabilities")
    assert caps.status_code == 200 and caps.json()["minimum_sdk_version"] == "1.3"
    assert caps.headers["cache-control"] == "no-store"


def test_public_or_human_payload_cannot_supply_verified_metadata(pair_v2):
    with Session(pair_v2.sender.engine) as db:
        start = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair_v2.sender.link_id).start_request
        )
    for changed, headers in (
        ({"verified_metadata": start["enrollment_metadata"]}, {}),
        ({}, {"Authorization": "Bearer fixture-human"}),
    ):
        assert pair_v2.client.post(
            PEER_V2_PREFIX + "/enrollments/start",
            json={**start, **changed},
            headers=headers,
        ).status_code in (409, 401)
    app = FastAPI()
    app.include_router(router)

    def deny_admin():
        raise HTTPException(403, "administrator required")

    app.dependency_overrides[require_admin] = deny_admin
    with TestClient(app) as client:
        assert (
            client.post(
                f"/api/v1/installation-peers/applications/{MODULE}/outbound/v2", json={}
            ).status_code
            == 403
        )


@pytest.mark.parametrize("intent_state", ["wrong", "expired", "reused"])
def test_receiving_application_checks_opaque_intent_policy_before_approval(
    pair_v2, monkeypatch, intent_state
):
    # Generic fixture policy, not Core organization/invitation tables.
    ledger = {
        INTENT: {"expires": datetime.now(UTC) + timedelta(minutes=1), "used": False}
    }
    if intent_state == "wrong":
        ledger.clear()
    elif intent_state == "expired":
        ledger[INTENT]["expires"] = datetime.now(UTC) - timedelta(seconds=1)
    else:
        ledger[INTENT]["used"] = True
    refused = []

    def receiver_handler(*args, **kwargs):
        assert kwargs["before_dispatch"]()
        context = OperationContext.from_platform(args[5])
        metadata = args[4]["enrollment_metadata"]
        assert context.machine and not context.user_id
        record = ledger.get(metadata["application_intent"])
        if not record or record["used"] or record["expires"] <= datetime.now(UTC):
            refused.append(True)
            return {"approved": False}
        pytest.fail("Invalid intent reached application approval")

    monkeypatch.setattr(peers, "invoke_application", receiver_handler)
    assert sender_call(pair_v2, peers.enroll_outbound)["state"] == "pending"
    assert refused and inbound(pair_v2)["state"] == "pending"


def test_signed_sdk_reads_review_and_approval_via_owned_platform_boundary(
    pair_v2, tmp_path, monkeypatch
):
    sender_call(pair_v2, peers.enroll_outbound)
    key_root = tmp_path / "sdk-keys"
    key_root.mkdir()
    secret = b"s" * 32
    instance = "a" * 24
    (key_root / f"{instance}.key").write_bytes(secret)
    server = ApplicationPlatformServer(tmp_path / "platform.sock", key_root)
    monkeypatch.setattr(
        backend.database, "SessionLocal", lambda: Session(pair_v2.receiver.engine)
    )

    class ClientSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def sendall(self, message):
            connection = MemoryConnection(message)
            server._handle(connection)
            self.response = connection.response

        def recv(self, _limit):
            result, self.response = self.response, b""
            return result

    monkeypatch.setattr(
        "three_mm_application_sdk.socket.socket", lambda *_args: ClientSocket()
    )
    monkeypatch.setattr("three_mm_application_sdk.socket.AF_UNIX", 1, raising=False)
    client = ApplicationPlatformClient(server.socket_path, instance, secret)
    assert client.get_installation_peer_capabilities()["approval_binding_version"] == 2
    review = client.list_installation_peers()["inbound"][0]
    with pytest.raises(ApplicationPlatformError, match="metadata"):
        client.approve_installation_peer(
            review["binding_id"], expected_generation=review["generation"]
        )
    result = client.approve_installation_peer(
        review["binding_id"],
        expected_generation=review["generation"],
        expected_metadata_revision=review["verified_metadata"]["consent_revision"],
        expected_metadata_hash=review["verified_metadata"]["metadata_hash"],
    )
    assert result["state"] == "active" and result["peer_version"] == 2
    fake = {
        "version": 1,
        "action": "installation.peers.approve",
        "instance_id": instance,
        "request_id": "forged",
        "timestamp": int(datetime.now(UTC).timestamp()),
        "signature": "0" * 64,
    }
    connection = MemoryConnection(json.dumps(fake).encode() + b"\n")
    server._handle(connection)
    assert json.loads(connection.response)["ok"] is False


def test_admin_api_persists_normalized_v2_metadata_and_cannot_accept_verified_claims(
    pair_v2,
):
    app = FastAPI()
    app.include_router(router)

    def sender_db():
        with Session(pair_v2.sender.engine) as db:
            yield db

    app.dependency_overrides[get_db] = sender_db
    app.dependency_overrides[require_admin] = lambda: type("Admin", (), {"id": 1})()
    payload = {
        "origin": ORIGIN,
        "receiver_identity": pair_v2.receiver.identity.model_dump(mode="json"),
        "target_module_id": MODULE,
        "application_intent": "another_fixture_intent",
        "consent": {"summary_fields": ["sdk_version", "core_version"]},
    }
    path = f"/api/v1/installation-peers/applications/{MODULE}/outbound/v2"
    with TestClient(app) as client:
        result = client.post(path, json=payload)
        assert result.status_code == 201
        metadata = result.json()["enrollment_metadata"]
        assert metadata["consent"]["summary_fields"] == ["core_version", "sdk_version"]
        for changed in (
            {"verified_metadata": metadata},
            {"metadata_hash": metadata["metadata_hash"]},
            {"application_intent": ""},
            {"application_intent": "x" * 257},
        ):
            assert client.post(path, json={**payload, **changed}).status_code == 422


def test_package_v2_requires_sdk_13_and_metadata_bootstrap_schema(pair_v2):
    definition = copy.deepcopy(pair_v2.definition)
    definition["service"]["sdk_version"] = "1.2"
    with pytest.raises(ModulePackageError):
        validate_module_package(
            application_package(definition=definition, manifest_value=pair_v2.manifest)
        )
    definition["service"]["sdk_version"] = "1.3"
    bootstrap = next(
        item
        for item in definition["operations"]
        if item["operation_id"] == "peer_enroll"
    )
    bootstrap["input_schema"]["required"].remove("enrollment_metadata")
    with pytest.raises(ModulePackageError):
        validate_module_package(
            application_package(definition=definition, manifest_value=pair_v2.manifest)
        )


def test_old_complete_and_bootstrap_callback_are_fenced_after_new_consent(pair_v2):
    sender_call(pair_v2, peers.enroll_outbound)
    with Session(pair_v2.sender.engine) as db:
        complete = copy.deepcopy(
            db.get(InstallationPeerOutbound, pair_v2.sender.link_id).complete_request
        )
    old_guard = pair_v2.captured[-1][1]["before_dispatch"]
    update(pair_v2, {})
    sender_call(pair_v2, peers.enroll_outbound)
    assert old_guard() is False
    assert (
        pair_v2.client.post(
            PEER_V2_PREFIX + "/enrollments/complete", json=complete
        ).status_code
        == 409
    )


def test_receiver_revoke_wins_delayed_rotation_receipt(pair_v2):
    activate(pair_v2)
    review = inbound(pair_v2)

    def revoke(origin, path, payload):
        pair_v2.transport(origin, path, payload)
        with Session(pair_v2.receiver.engine) as db:
            app = db.scalar(select(ApplicationExtensionInstallation))
            peers.revoke_peer(db, app, review["binding_id"], "inbound", user_id=1)
        raise peers.InstallationPeerError("fixture lost reply")

    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair_v2, peers.rotate_outbound, transport=revoke)
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair_v2, peers.rotate_outbound)
    assert inbound(pair_v2)["state"] == "revoked"


def test_explicit_v1_to_v2_upgrade_requires_revoke_reopen_and_new_proof(pair):
    legacy.activate_pair(pair)
    definition = copy.deepcopy(pair.definition)
    definition["service"]["sdk_version"] = "1.3"
    definition["peer_receiver"]["peer_version"] = 2
    bootstrap = next(
        item
        for item in definition["operations"]
        if item["operation_id"] == "peer_enroll"
    )
    bootstrap["input_schema"]["properties"]["enrollment_metadata"] = {"type": "object"}
    bootstrap["input_schema"]["required"].append("enrollment_metadata")
    blob = application_package(definition=definition, manifest_value=pair.manifest)
    pair.package_path.write_bytes(blob)
    validated = validate_module_package(blob)
    for core in (pair.sender, pair.receiver):
        with Session(core.engine) as db:
            package = db.scalar(select(ModulePackage))
            package.sha256, package.size_bytes = validated.sha256, len(blob)
            db.commit()
    with Session(pair.sender.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        old = db.get(InstallationPeerOutbound, pair.sender.link_id)
        peers.revoke_peer(db, app, old.link_id, "outbound", user_id=1)
        result = peers.create_outbound(
            db,
            app,
            origin=ORIGIN,
            receiver_identity=pair.receiver.identity,
            target_module_id=MODULE,
            consent={},
            application_intent=INTENT,
            peer_version=2,
            user_id=1,
        )
        pair.sender.link_id = result["link_id"]
    with pytest.raises(peers.InstallationPeerError):
        sender_call(pair, peers.enroll_outbound)
    with Session(pair.receiver.engine) as db:
        app = db.scalar(select(ApplicationExtensionInstallation))
        row = db.scalar(select(InstallationPeerInbound))
        peers.revoke_peer(db, app, row.binding_id, "inbound", user_id=1)
        peers.reopen_inbound(db, app, row.binding_id, row.generation, user_id=1)
    activate(pair)
    assert inbound(pair)["verified_metadata"]["application_intent"] == INTENT
