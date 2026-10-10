"""Core actual installed grants + real host metadata Unix IPC + own SQLite.

Lifecycle records/DB are explicitly fixture-prepared, NOT production install or
restore. No service-authored host context or new platform route is used here.
"""

import hashlib
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational as core
from backend.services.application_authority_sources import _configuration
from backend.tests.test_application_authority_management import (
    identity,
)
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import (
    native,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import (
    source_installed,
)
from backend.tests.test_application_relational_admission import SECRET, admitted, apply
from three_mm_application_sdk.relational_wire import (
    accept_permit,
    canonical,
    permit_digest,
    sign_metadata,
)
from three_mm_application_sdk.scoped_relational import ApplicationScopedStorage
from three_mm_runtime import application_relational_session as runtime
from three_mm_runtime.tests.test_application_relational_session import make_prepared

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="POSIX Core keys/host metadata"
)


@pytest.fixture
def host_state(admitted, monkeypatch):
    state = admitted
    monkeypatch.setattr(runtime, "_LIFECYCLE_UID", os.getuid())
    with tempfile.TemporaryDirectory(prefix="3mm-rh-") as directory:
        with Session(state.engine) as db:
            installation = db.get(Installation, 1)
            root = Path(directory) / installation.instance_id
            prepared = state.manager._prepare(1)
            configuration = _configuration(db, 1, prepared[1])
            owner = hashlib.sha256(
                core._canonical_bytes(core._principal(db, 1))
            ).hexdigest()
            generation = db.get(CoreAuthorityGuard, 1).generation
        with state.engine.begin() as db:
            db.execute(
                update(Installation).values(socket_path=str(root / "run/service.sock"))
            )
        definition = state.validated.application_extension
        metadata = {
            "instance_id": root.name,
            "sha256": state.validated.sha256,
            "wheel": "service.whl",
            "configuration": configuration,
            "storage": definition.storage.model_dump(mode="json"),
        }
        with zipfile.ZipFile(state.archive) as archive:
            wheel = archive.read(definition.service.artifact)
        record, receipts = make_prepared(
            root, metadata, wheel=wheel, owner=owner, generation=generation
        )
        with runtime._RelationalHostSession(root, SECRET) as session:
            state.host, state.host_root, state.receipts, state.record = (
                session,
                root,
                receipts,
                record,
            )
            yield state


def invocation(state, **changes):
    operation = state.validated.application_extension.operations[0]
    with Session(state.engine) as db:
        value = core.prepare_host_invocation(
            db,
            1,
            operation.operation_id,
            required_audience=operation.audiences[0],
            transport_secret=SECRET,
        )
    return (
        sign_metadata(SECRET, "invocation", {**value, **changes}) if changes else value
    )


def admit(state, *, identifier=None, mode="write"):
    with Session(state.engine) as db:
        return core.admit_host_transaction(
            db, 1, identifier or identity(), mode, transport_secret=SECRET
        )


def enter(state, ticket):
    return state.host.invocation(
        ticket,
        operation_id=state.validated.application_extension.operations[0].operation_id,
    )


def test_real_host_resolver_never_takes_context_or_deadline_from_service(host_state):
    state = host_state
    with pytest.raises(core.RelationalAuthorityError):
        admit(state)  # Factory/health do not have an implicit invocation/SQL grant.
    ticket = invocation(state)
    operation = state.validated.application_extension.operations[0]
    assert (
        ticket["deadline_ms"] - ticket["started_at_ms"]
        == operation.timeout_seconds * 1000
    )
    with enter(state, ticket):
        permit = admit(state)
        assert permit["runtime_nonce"] == ticket["runtime_nonce"]
        assert permit["database_lineage"] == state.record["database_lineage"]
        assert permit["binding_sha256"] == ticket["binding_sha256"]
        assert permit["deadline_ms"] <= ticket["deadline_ms"]
        assert permit["deadline_ms"] - permit["issued_at_ms"] <= 5000
        with pytest.raises(core.RelationalAuthorityError):
            admit(state, identifier=permit["transaction_id"])
    with pytest.raises(core.RelationalAuthorityError):
        admit(state)


@pytest.mark.parametrize(
    "drift",
    [
        "revoke",
        "disable",
        "configuration",
        "epoch",
        "recovery",
        "instance",
        "transport_key",
    ],
)
def test_real_unix_snapshot_never_substitutes_for_current_authority(host_state, drift):
    state = host_state
    ticket = invocation(state)
    with enter(state, ticket):
        if drift == "revoke":
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"],
            )
        elif drift == "transport_key":
            with (
                Session(state.engine) as db,
                pytest.raises(core.RelationalAuthorityError),
            ):
                core.admit_host_transaction(
                    db, 1, identity(), "write", transport_secret=b"x" * 32
                )
            return
        else:
            with state.engine.begin() as db:
                if drift == "recovery":
                    db.execute(update(CoreAuthorityGuard).values(generation=identity()))
                else:
                    db.execute(
                        update(Installation).values(
                            **{
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
                        )
                    )
        identifier = identity()
        with pytest.raises(core.RelationalAuthorityError):
            admit(state, identifier=identifier)
        with Session(state.engine) as db:
            assert db.get(Action, identifier) is None


def test_host_ipc_does_not_hold_core_db_or_review_key_lease(host_state, monkeypatch):
    original = core._call_host_metadata

    def probe(path, secret):
        # A separate writer commits during IPC, proving no Core write lease.
        with host_state.engine.begin() as db:
            db.execute(update(Installation).values(error="metadata-probe"))
        with host_state.manager.keys.locked():
            return original(path, secret)

    monkeypatch.setattr(core, "_call_host_metadata", probe)
    with enter(host_state, invocation(host_state)):
        assert admit(host_state)["mode"] == "write"


def test_core_signed_ticket_foreign_owner_or_lifecycle_is_refused(host_state):
    state = host_state
    for changes in ({"binding_sha256": "0" * 64}, {"authority_epoch": "0" * 32}):
        with (
            enter(state, invocation(state, **changes)),
            pytest.raises(core.RelationalAuthorityError),
        ):
            admit(state)
    with Session(state.engine) as db, pytest.raises(core.RelationalAuthorityError):
        core.prepare_host_invocation(
            db, 1, "undeclared", required_audience="internal", transport_secret=SECRET
        )


def test_expired_operation_or_restart_never_renews_budget(host_state, monkeypatch):
    state = host_state
    current = invocation(state)
    original = runtime._clock
    with enter(state, current):
        monkeypatch.setattr(
            runtime, "_clock", lambda: (original()[0], current["deadline_ms"])
        )
        with pytest.raises(core.RelationalAuthorityError):
            admit(state)
    monkeypatch.setattr(runtime, "_clock", original)
    # A second worker is created only after the fixture's worker is stopped.
    state.host.__exit__()
    with runtime._RelationalHostSession(state.host_root, SECRET) as restarted:
        with pytest.raises(ValueError):
            with restarted.invocation(current, operation_id=current["operation_id"]):
                pytest.fail("Restart reused an old invocation")


@pytest.mark.parametrize("revoke_before_completion", [False, True])
def test_real_unix_host_core_permit_atomic_business_outbox_receipt_and_lost_ack(
    host_state,
    revoke_before_completion,
):
    state = host_state
    definition = state.validated.application_extension
    permits = []

    def admission(identifier, mode, digest, deadline):
        value = admit(state, identifier=identifier, mode=mode)
        permits.append(value)
        assert value["profile_sha256"] == digest
        return accept_permit(
            value,
            secret=SECRET,
            expected=state.host._permit_expectations(identifier, mode),
            local_deadline=deadline,
        )

    def complete(receipt):
        # Completion runs after own SQLite unlock and can acquire a write lock.
        with sqlite3.connect(state.host_root / "data/state.sqlite3", timeout=0) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()
        db.close()
        if revoke_before_completion:
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"],
            )
        with Session(state.engine) as db:
            core.record_host_commit(db, 1, receipt, transport_secret=SECRET)
        raise OSError("completion ACK lost")

    storage = ApplicationScopedStorage(
        state.host_root / "data",
        declaration=definition.storage.relational,
        schema_revision=definition.storage.schema_revision,
        admit=admission,
        receipts=state.receipts,
        complete=complete,
    )
    from three_mm_application_sdk.scoped_relational import (
        ApplicationRelationalExecutionUnconfirmed,
    )

    with enter(state, invocation(state)):
        with pytest.raises(ApplicationRelationalExecutionUnconfirmed):
            with storage.transaction() as db:
                db.execute("INSERT INTO example(value) VALUES (1)")
                storage.enqueue_outbox(
                    db,
                    outbox_id="one",
                    event_type="example",
                    payload={"intent": 1},
                    idempotency_key="one",
                )
        permit = permits[0]
        assert (
            storage.transaction_status(permit["transaction_id"], permit_digest(permit))[
                "outcome"
            ]
            == "committed"
        )
        with Session(state.engine) as db:
            assert (
                core.transaction_status(db, 1, permit["transaction_id"])["outcome"]
                == "committed"
            )
        with pytest.raises(core.RelationalAuthorityError):
            admit(state, identifier=permit["transaction_id"])
    with sqlite3.connect(state.host_root / "data/state.sqlite3") as db:
        assert db.execute("SELECT value FROM example").fetchall() == [(1,)]
        assert db.execute("SELECT COUNT(*) FROM three_mm_outbox").fetchone()[0] == 1
