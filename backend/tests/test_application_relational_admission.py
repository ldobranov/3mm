"""Actual Core sealed grants + internal signed admission, NOT deployed host flow.

The fixture supplies the future protected host context directly. No public
transport route or production relational activation is enabled by these tests.
"""

import dataclasses
import hashlib
import json
import os
import sqlite3
import threading
import time

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational as service
from backend.tests.test_application_authority_management import identity
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import native
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import source_installed
from backend.tests.test_application_relational_review_api import store_package
from three_mm_application_sdk import ApplicationMigration, ApplicationStorage
from three_mm_application_sdk.relational_receipts import _prepare_receipt_metadata
from three_mm_application_sdk.relational_wire import (
    accept_permit,
    canonical,
    permit_digest,
    sign_metadata,
    verify_metadata,
)
from three_mm_application_sdk.scoped_relational import ApplicationScopedStorage
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real Core POSIX keys/clock")
SECRET = b"t" * 32


def apply(state, native_id):
    plan = state.manager.create_review(
        1,
        actor_token=state.token,
        request_id=identity(),
        native_review_id=native_id,
        scopes=state.manager.inspect(1)["scopes"],
    )
    for decision in ("approve", "apply"):
        result = state.manager.decide(
            1,
            actor_token=state.token,
            request_id=identity(),
            plan_id=plan["plan_id"],
            expected_revision=plan["revision"],
            fingerprint=plan["fingerprint"],
            decision=decision,
        )
        plan = {**plan, **result}


@pytest.fixture
def admitted(managed_installed, request):
    state = managed_installed
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request(
        mode=getattr(request, "param", "read_write")
    )
    store_package(state, definition)
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    proof = native(state)
    apply(state, proof["native_review_id"])
    # Fixture re-enable, not a production lifecycle bypass. Fresh review/epoch.
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                enabled=True, status="active", authority_epoch=identity()
            )
        )
    apply(state, proof["native_review_id"])
    state.native_id = proof["native_review_id"]
    state.runtime_nonce, state.database_lineage = identity(), identity()
    return state


def context(state):
    boot, now = authority._clock()
    with Session(state.engine) as db:
        row = db.get(Installation, 1)
        return service._HostTransactionContext(
            row.instance_id,
            state.runtime_nonce,
            state.database_lineage,
            boot,
            row.authority_epoch,
            db.get(CoreAuthorityGuard, 1).generation,
            now,
            now + 20000,
        )


def admit(state, *, transaction_id=None, mode="write", host=None):
    with Session(state.engine) as db:
        return service.admit_transaction(
            db,
            1,
            transaction_id or identity(),
            mode,
            host_context=host or context(state),
            transport_secret=SECRET,
        )


def status(state, identifier):
    with Session(state.engine) as db:
        return service.transaction_status(db, 1, identifier)


def commit(state, permit, host, **changes):
    value = sign_metadata(
        SECRET,
        "receipt",
        {
            "version": 1,
            "transaction_id": permit["transaction_id"],
            "permit_sha256": permit_digest(permit),
            "database_lineage": permit["database_lineage"],
            "schema_revision": state.validated.application_extension.storage.schema_revision,
            "outcome": "committed",
            **changes,
        },
    )
    with Session(state.engine) as db:
        return service.record_commit(
            db, 1, value, host_context=host, transport_secret=SECRET
        )


def test_signed_admission_is_durable_metadata_and_never_reissued(admitted):
    state = admitted
    host = context(state)
    permit = admit(state, host=host)
    verify_metadata(SECRET, "admission", permit)
    assert permit["deadline_ms"] <= host.started_at_ms + 5000
    assert permit["deadline_ms"] <= host.operation_deadline_ms
    assert status(state, permit["transaction_id"])["outcome"] == "execution_unconfirmed"
    with pytest.raises(service.RelationalAuthorityError):
        admit(state, transaction_id=permit["transaction_id"], host=host)
    with pytest.raises(service.RelationalAuthorityError):
        admit(state, transaction_id=permit["transaction_id"], mode="read", host=host)
    with Session(state.engine) as db:
        row = db.get(Action, permit["transaction_id"])
        assert "SQL" not in row.payload and str(state.root) not in row.payload
    assert "signature" not in status(
        state, permit["transaction_id"]
    )  # No reusable permit.


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "native_revoke",
        "disable",
        "configuration",
        "epoch",
        "recovery",
        "key",
        "instance",
        "artifact",
    ],
)
def test_current_authority_drift_refuses_fresh_admission(admitted, drift):
    state = admitted
    host = context(state)
    if drift == "revoke":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "native_revoke":
        item = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=item["native_review_id"],
            expected_revision=item["revision"],
        )
    elif drift == "key":
        state.keys.rotate(expected_key_id=state.keys.identity().key_id)
    elif drift == "artifact":
        definition = state.validated.application_extension.model_dump(mode="json")
        definition["storage"]["relational"]["max_busy_ms"] = 0
        store_package(state, definition)
    else:
        with state.engine.begin() as db:
            if drift == "recovery":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                changes = {
                    "disable": {"enabled": False, "status": "disabled"},
                    "configuration": {
                        "configuration": {
                            **state.configuration,
                            "PRIVATE_NOTE": "changed",
                        }
                    },
                    "epoch": {"authority_epoch": identity()},
                    "instance": {"instance_id": "e" * 24},
                }[drift]
                db.execute(update(Installation).values(**changes))
    with pytest.raises(service.RelationalAuthorityError):
        admit(state, host=host)


@pytest.mark.parametrize(
    "change",
    [
        {"started_at_ms": True},
        {"operation_deadline_ms": True},
        {"operation_deadline_ms": 0},
        {"started_at_ms": 0},
        {"runtime_nonce": "bad"},
        {"database_lineage": "bad"},
        {"boot_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_invalid_or_expired_host_context_refuses_before_record(admitted, change):
    state = admitted
    identifier = identity()
    with pytest.raises(service.RelationalAuthorityError):
        admit(
            state,
            transaction_id=identifier,
            host=dataclasses.replace(context(state), **change),
        )
    with Session(state.engine) as db:
        assert db.get(Action, identifier) is None


@pytest.mark.parametrize("admitted", ["read"], indirect=True)
def test_read_only_current_grant_never_admits_write(admitted):
    assert admit(admitted, mode="read")["mode"] == "read"
    with pytest.raises(service.RelationalAuthorityError):
        admit(admitted)


def test_admitted_commit_metadata_can_finish_after_revoke_but_not_recovery(admitted):
    state = admitted
    host = context(state)
    permit = admit(state, host=host)
    state.manager.revoke(
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_revision=state.manager.inspect(1)["grant_record_revision"],
    )
    assert commit(state, permit, host)["outcome"] == "committed"
    assert commit(state, permit, host) == status(state, permit["transaction_id"])
    with pytest.raises(service.RelationalAuthorityError):
        admit(state, host=host)
    with state.engine.begin() as db:
        db.execute(update(CoreAuthorityGuard).values(generation=identity()))
    with pytest.raises(service.RelationalAuthorityError):
        status(state, permit["transaction_id"])


@pytest.mark.parametrize(
    "change",
    [
        {"permit_sha256": "e" * 64},
        {"database_lineage": "e" * 32},
        {"schema_revision": "0002"},
        {"transaction_id": "e" * 32},
        {"outcome": "rolled_back"},
    ],
)
def test_completion_cannot_clear_uncertainty_with_foreign_or_unproved_receipt(
    admitted, change
):
    host = context(admitted)
    permit = admit(admitted, host=host)
    with pytest.raises(service.RelationalAuthorityError):
        commit(admitted, permit, host, **change)
    assert (
        status(admitted, permit["transaction_id"])["outcome"] == "execution_unconfirmed"
    )


def test_bounded_core_journal_refuses_without_evicting_uncertain_record(
    admitted, monkeypatch
):
    state = admitted
    permit = admit(state)
    with Session(state.engine) as db:
        count = len(db.scalars(select(Action)).all())
    monkeypatch.setattr(service, "MAX_RELATIONAL_ACTIONS", count)
    with pytest.raises(service.RelationalAuthorityError):
        admit(state)
    assert status(state, permit["transaction_id"])["outcome"] == "execution_unconfirmed"


def test_revoke_committed_while_archive_preparation_runs_wins(admitted, monkeypatch):
    state = admitted
    host = context(state)
    prepared, resume = threading.Event(), threading.Event()
    original = state.manager._prepare
    errors = []

    def pause(identifier):
        result = original(identifier)
        if threading.current_thread().name == "pending-admission":
            prepared.set()
            assert resume.wait(10)
        return result

    monkeypatch.setattr(state.manager, "_prepare", pause)

    def worker():
        try:
            admit(state, host=host)
        except service.RelationalAuthorityError as error:
            errors.append(error)

    thread = threading.Thread(target=worker, name="pending-admission")
    thread.start()
    try:
        assert prepared.wait(10)
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    finally:
        resume.set()
        thread.join(10)
    assert not thread.is_alive() and len(errors) == 1


@pytest.mark.parametrize(
    "action", ["relational.admit", "relational.complete", "relational.status"]
)
def test_unfinished_host_dependency_is_not_exposed_to_application_gateway(
    admitted, action
):
    from backend.services.application_platform import ApplicationPlatformServer

    server = ApplicationPlatformServer(
        admitted.root / "platform.sock", admitted.root / "keys"
    )
    for mode in ("enforced", "compatibility"):
        with admitted.engine.begin() as db:
            db.execute(update(Installation).values(authority_mode=mode))
        with Session(admitted.engine) as db, pytest.raises(ValueError):
            server._dispatch(
                db,
                db.get(Installation, 1),
                {
                    "action": action,
                    "host_context": dataclasses.asdict(context(admitted)),
                },
                transport_secret=SECRET,
            )


def test_real_core_grant_signed_permit_and_atomic_sqlite_receipt(admitted, tmp_path):
    state = admitted
    definition = state.validated.application_extension
    legacy = ApplicationStorage(tmp_path / "data")
    revision = definition.storage.schema_revision
    legacy.migrate(
        [
            ApplicationMigration(
                revision, lambda db: db.execute("CREATE TABLE example(value INTEGER)")
            )
        ],
        revision,
    )
    with sqlite3.connect(legacy.database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        receipts = _prepare_receipt_metadata(
            db,
            database_lineage=state.database_lineage,
            schema_revision=revision,
            secret=SECRET,
        )
    permits = []
    host = context(state)

    def admission(identifier, mode, digest, deadline):
        permit = admit(state, transaction_id=identifier, mode=mode, host=host)
        assert permit["profile_sha256"] == digest
        permits.append(permit)
        expected = {
            field: permit[field]
            for field in (
                "transaction_id",
                "mode",
                "profile_sha256",
                "instance_id",
                "runtime_nonce",
                "database_lineage",
                "boot_id",
                "authority_epoch",
                "recovery_generation",
                "binding_sha256",
            )
        }
        return accept_permit(
            permit, secret=SECRET, expected=expected, local_deadline=deadline
        )

    def completion(receipt):
        with Session(state.engine) as db:
            service.record_commit(
                db, 1, receipt, host_context=host, transport_secret=SECRET
            )

    storage = ApplicationScopedStorage(
        legacy.data_dir,
        declaration=definition.storage.relational,
        schema_revision=revision,
        admit=admission,
        receipts=receipts,
        complete=completion,
    )
    with storage.transaction() as db:
        db.execute("INSERT INTO example(value) VALUES (1)")
        storage.enqueue_outbox(
            db,
            outbox_id="one",
            event_type="example",
            payload={"intent": 1},
            idempotency_key="one",
        )
    assert status(state, permits[0]["transaction_id"])["outcome"] == "committed"
    assert (
        storage.transaction_status(
            permits[0]["transaction_id"], permit_digest(permits[0])
        )["outcome"]
        == "committed"
    )
    with sqlite3.connect(legacy.database_path) as db:
        assert db.execute("SELECT value FROM example").fetchall() == [(1,)]
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 1
