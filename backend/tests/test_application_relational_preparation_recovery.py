"""Real sealed authority and root filesystem recovery; no installed VM effects."""

import hashlib
import os
import sqlite3

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.session import UserSession
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as lifecycle
from backend.services import application_relational_preparation_recovery as coordinator
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.services.application_relational_admin_worker import dispatch
from backend.tests.test_application_relational_installation import (
    ROOT_ONLY,
    absent_paths,
    action,
    identity,
    initial,
    managed_installed,
)
from backend.tests.test_application_relational_installation import run as first_prepare
from backend.tests.test_application_relational_installation import (
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_preparation_recovery_wire import (
    _EmptyPreparationRecoveryTicket,
)
from three_mm_application_sdk.relational_wire import (
    _RelationalMigrationPreparationTicket,
    _RelationalPreparationTicket,
    canonical,
)
from three_mm_runtime import application_relational_preparation as preparation
from three_mm_runtime import application_relational_preparation_recovery as helper
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    _require_no_pending_rollback,
)
from three_mm_runtime.application_relational_preparation_recovery_control import (
    preparation_recovery_request,
    recover_installed_preparation,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX sealed authority"
)


def sources(state):
    namespace = lifecycle.issue_namespace_preparation(
        state.manager,
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_grant_record_revision=state.manager.inspect(1)[
            "grant_record_revision"
        ],
        confirm_fresh_owned_namespace=True,
        transport_secret=b"t" * 32,
        service_uid=1200,
        service_gid=1201,
        coordinator_uid=1202,
    )
    lifecycle.preparation_checkpoint(
        state.manager,
        1,
        namespace,
        "begin",
        actor_token=state.token,
        transport_secret=b"t" * 32,
    )
    from three_mm_application_sdk.relational_wire import sign_metadata

    receipt = sign_metadata(
        b"t" * 32,
        "namespace_preparation_result",
        {
            "version": 1,
            "preparation_id": namespace["preparation_id"],
            "ticket_sha256": hashlib.sha256(canonical(namespace)).hexdigest(),
            "outcome": "namespace_created_not_started",
        },
    )
    lifecycle.preparation_checkpoint(
        state.manager,
        1,
        namespace,
        "finish",
        actor_token=state.token,
        transport_secret=b"t" * 32,
        receipt=receipt,
    )
    source = lifecycle.issue_migrated_schema_preparation(
        state.manager,
        1,
        actor_token=state.token,
        request_id=identity(),
        expected_grant_record_revision=state.manager.inspect(1)[
            "grant_record_revision"
        ],
        confirm_owned_business_migrations=True,
        transport_secret=b"t" * 32,
    )
    lifecycle.preparation_checkpoint(
        state.manager,
        1,
        source,
        "begin",
        actor_token=state.token,
        transport_secret=b"t" * 32,
    )
    state.namespace, state.source, state.secret = namespace, source, b"t" * 32
    return state


def issue(state, **changes):
    return coordinator.issue_empty_preparation_recovery(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_preparation_id": state.source["preparation_id"],
            "source_namespace_id": state.namespace["preparation_id"],
            "expected_preparation_revision": action(state, state.source)["revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_restored_empty_checkpoint": True,
            "transport_secret": state.secret,
            **changes,
        },
    )


def check(state, ticket, phase, **kwargs):
    return coordinator.empty_preparation_recovery_checkpoint(
        state.manager,
        1,
        ticket,
        phase,
        actor_token=state.token,
        transport_secret=state.secret,
        **kwargs,
    )


def recover(state, ticket, callback=None, **changes):
    return helper.reconcile_restored_empty_preparation(
        state.archive,
        ticket,
        state.source,
        state.namespace,
        **{
            "configuration": state.configuration,
            "transport_secret": state.secret,
            "root": state.runtime,
            "key_root": state.transport_keys,
            "state_root": state.helper_state,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            "checkpoint": callback or (lambda *a, **kw: check(state, *a, **kw)),
            "supervisor": state.supervisor,
            **changes,
        },
    )


@pytest.fixture
def failed(initial, monkeypatch):
    state = initial

    def denied(*a, **kw):
        raise PermissionError("injected worker UID transition refusal")

    with monkeypatch.context() as patch:
        patch.setattr(preparation, "run_business_migrations", denied)
        with pytest.raises(preparation.RelationalPreparationError):
            first_prepare(state)
    state.namespace, state.source = state.issued
    state.secret = state.key_path.read_bytes()
    state.rollback = state.instance / (
        ".activation-" + state.source["preparation_id"] + ".rollback"
    )
    assert (
        helper._json(state.rollback / "activation.json")["phase"]
        == "restored_not_started"
    )
    assert not state.database.exists()
    return state


@pytest.mark.parametrize(
    "problem",
    ["confirmation", "actor", "source", "namespace", "revision", "grant", "secret"],
)
def test_recovery_requires_exact_current_local_consent(stopped, problem):
    state = sources(stopped)
    changes = {
        "confirmation": {"confirm_restored_empty_checkpoint": False},
        "actor": {"actor_token": state.user_token},
        "source": {"source_preparation_id": identity()},
        "namespace": {"source_namespace_id": identity()},
        "revision": {"expected_preparation_revision": identity()},
        "grant": {"expected_grant_record_revision": identity()},
        "secret": {"transport_secret": b"x" * 32},
    }[problem]
    with pytest.raises((authority.AuthorityManagementError, ValueError)):
        issue(state, **changes)
    assert "preparation_recovery_id" not in action(state, state.source)["data"]


def test_source_unknown_outcome_preserved_and_late_helper_fenced(stopped):
    state = sources(stopped)
    first = issue(state)
    assert action(state, state.source)["state"] == "execution_unconfirmed"
    assert "receipt" not in action(state, state.source)["data"]
    with pytest.raises(authority.AuthorityManagementError, match="superseded"):
        lifecycle.preparation_checkpoint(
            state.manager,
            1,
            state.source,
            "check",
            actor_token=state.token,
            transport_secret=state.secret,
        )
    check(state, first, "begin")
    second_expected = action(state, state.source)["revision"]
    second = issue(state)
    with pytest.raises(authority.AuthorityManagementError, match="superseded"):
        check(state, first, "check")
    assert check(state, second, "authorize") == {"state": "authorized_not_started"}
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        issue(
            state,
            request_id=second["preparation_id"],
            expected_preparation_revision=second_expected,
        )
    for model in (_RelationalMigrationPreparationTicket, _RelationalPreparationTicket):
        with pytest.raises(ValidationError):
            model.model_validate(second)


@pytest.mark.parametrize(
    "drift",
    ["grant", "native", "actor", "epoch", "generation", "enabled", "deadline", "boot"],
)
def test_each_recovery_phase_rechecks_current_authority(stopped, monkeypatch, drift):
    state = sources(stopped)
    ticket = issue(state)
    check(state, ticket, "begin")
    if drift == "grant":
        state.manager.revoke(
            1,
            actor_token=state.token,
            request_id=identity(),
            expected_revision=state.manager.inspect(1)["grant_record_revision"],
        )
    elif drift == "native":
        proof = state.manager.inspect(1)["native_reviews"][0]
        state.manager.revoke_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            native_review_id=proof["native_review_id"],
            expected_revision=proof["revision"],
        )
    elif drift in {"deadline", "boot"}:
        monkeypatch.setattr(
            authority,
            "_clock",
            lambda: (
                (
                    ticket["boot_id"]
                    if drift == "deadline"
                    else "00000000-0000-0000-0000-000000000001"
                ),
                (
                    ticket["deadline_ms"]
                    if drift == "deadline"
                    else ticket["issued_at_ms"]
                ),
            ),
        )
    else:
        with state.engine.begin() as db:
            if drift == "actor":
                db.execute(update(UserSession).values(is_active=False))
            elif drift == "generation":
                db.execute(update(CoreAuthorityGuard).values(generation=identity()))
            else:
                db.execute(
                    update(Installation).values(
                        **(
                            {"authority_epoch": identity()}
                            if drift == "epoch"
                            else {"enabled": True, "status": "active"}
                        )
                    )
                )
    with pytest.raises(
        (
            authority.AuthorityManagementError,
            AuthorityReviewKeyError,
            PolicyReviewStoreError,
        )
    ):
        check(state, ticket, "check")


def resumption(state, ticket, **changes):
    return coordinator.issue_preparation_resumption(
        state.manager,
        1,
        **{
            "actor_token": state.token,
            "request_id": identity(),
            "source_recovery_id": ticket["preparation_id"],
            "expected_recovery_revision": action(state, ticket)["revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "confirm_owned_business_migrations": True,
            "transport_secret": state.secret,
            **changes,
        },
    )


@ROOT_ONLY
def test_real_recovery_retains_all_bytes_and_fresh_resume_runs_only_nonroot_migration(
    failed,
):
    state = failed
    before = {path.name: path.read_bytes() for path in state.rollback.iterdir()}
    wheel = state.instance / "releases" / state.validated.sha256 / "service.whl"
    original_wheel, original_key = wheel.read_bytes(), state.secret
    old_history = action(state, state.source)["state"]
    ticket = issue(state)
    result = recover(state, ticket)
    assert result["outcome"] == "restored_empty_not_started"
    assert (
        state.key_path.read_bytes() == original_key
        and wheel.read_bytes() == original_wheel
    )
    archive = state.instance / (
        ".preparation-evidence-" + state.source["preparation_id"] + ".rollback"
    )
    assert {path.name: path.read_bytes() for path in archive.iterdir()} == before
    assert action(state, state.source)["state"] == old_history
    assert "receipt" not in action(state, state.source)["data"]
    assert not state.database.exists() and not (state.instance / "active.json").exists()
    _require_no_pending_rollback(state.instance)
    helper.validate_preparation_resumption(state.instance, ticket, result, state.secret)
    source_revision = action(state, ticket)["revision"]
    migration = resumption(state, ticket)
    with pytest.raises(authority.AuthorityManagementError):
        resumption(state, ticket, expected_recovery_revision=source_revision)
    prepared = preparation.prepare_migrated_relational_database(
        state.archive,
        migration,
        configuration=state.configuration,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        supervisor=state.supervisor,
        resumption=(ticket, result),
        checkpoint=lambda *a, **kw: lifecycle.preparation_checkpoint(
            state.manager,
            1,
            *a,
            actor_token=state.token,
            transport_secret=state.secret,
            **kw,
        ),
    )
    assert prepared["outcome"] == "prepared_not_started"
    assert state.database.stat().st_uid == 1200
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
    assert all(call[0] == "stop" for call in state.calls)
    assert original_key == state.key_path.read_bytes()
    assert archive.exists()


@ROOT_ONLY
@pytest.mark.parametrize(
    "problem",
    [
        "data",
        "run",
        "active",
        "relational",
        "candidate",
        "unknown",
        "symlink",
        "hardlink",
        "preimage",
        "phase",
        "wheel",
        "key",
        "ownership",
        "ambiguous",
    ],
)
def test_unknown_or_nonempty_state_refuses_without_archiving_or_deleting(
    failed, problem
):
    state = failed
    if problem in {"data", "run"}:
        (state.instance / problem / "unknown").write_bytes(b"KEEP")
    elif problem in {"active", "relational"}:
        (state.instance / (problem + ".json")).write_bytes(b"KEEP")
    elif problem == "candidate":
        (state.rollback / "candidate-state.sqlite3").write_bytes(b"KEEP")
    elif problem == "unknown":
        (state.instance / "unknown").mkdir()
    elif problem == "symlink":
        (state.rollback / "files.json").unlink()
        (state.rollback / "files.json").symlink_to(state.rollback / "database.json")
    elif problem == "hardlink":
        os.link(state.rollback / "files.json", state.instance / "hardlink")
    elif problem == "preimage":
        (state.rollback / "database.json").write_bytes(
            canonical(
                {"version": 1, "present": True, "size_bytes": 0, "sha256": "0" * 64}
            )
        )
    elif problem == "phase":
        payload = helper._json(state.rollback / "activation.json")
        payload["phase"] = "completion_unconfirmed"
        (state.rollback / "activation.json").write_bytes(canonical(payload))
    elif problem == "wheel":
        (
            state.instance / "releases" / state.validated.sha256 / "service.whl"
        ).write_bytes(b"changed")
    elif problem == "key":
        state.key_path.write_bytes(b"x" * 32)
    elif problem == "ownership":
        os.chown(state.data, 1203, 1201)
    else:
        (
            state.instance
            / (".preparation-evidence-" + state.source["preparation_id"] + ".rollback")
        ).mkdir()
    ticket = issue(state)
    with pytest.raises((ValueError, preparation.RelationalPreparationError)):
        recover(state, ticket)
    assert state.rollback.exists()
    assert not (
        state.instance / (".activation-" + ticket["preparation_id"] + ".rollback")
    ).exists()
    assert action(state, ticket)["state"] == "recorded"


@ROOT_ONLY
@pytest.mark.parametrize("failure", ["finish_before", "finish_after", "archive_reply"])
def test_interrupted_recovery_fences_resume_and_requires_fresh_ticket(
    failed, monkeypatch, failure
):
    state = failed
    first = issue(state)

    def fail(current, phase, **kw):
        if phase == "finish" and failure == "finish_before":
            raise OSError("finish not delivered")
        result = check(state, current, phase, **kw)
        if phase == "finish" and failure == "finish_after":
            raise OSError("finish ACK lost")
        return result

    original = helper._move

    def moved(source, target):
        original(source, target)
        if source == state.rollback:
            raise OSError("archive reply lost")

    with monkeypatch.context() as patch:
        if failure == "archive_reply":
            patch.setattr(helper, "_move", moved)
        with pytest.raises(preparation.RelationalPreparationError):
            recover(state, first, fail)
    with pytest.raises(ApplicationActivationError):
        _require_no_pending_rollback(state.instance)
    if failure == "finish_after":
        sealed_receipt = action(state, first)["data"]["receipt"]
        with pytest.raises(ApplicationActivationError):
            helper.validate_preparation_resumption(
                state.instance, first, sealed_receipt, state.secret
            )
    second = issue(state)
    result = recover(state, second)
    _require_no_pending_rollback(state.instance)
    helper.validate_preparation_resumption(state.instance, second, result, state.secret)
    assert list(state.instance.glob(".preparation-uncertain-*.rollback"))
    assert not state.database.exists()
    with pytest.raises(authority.AuthorityManagementError, match="consumed"):
        recover(state, second)


@ROOT_ONLY
def test_core_revocation_before_finish_keeps_blocking_evidence(failed):
    state = failed
    ticket = issue(state)

    def revoked(current, phase, **kwargs):
        if phase == "finish":
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.manager.inspect(1)["grant_record_revision"],
            )
        return check(state, current, phase, **kwargs)

    with pytest.raises(preparation.RelationalPreparationError):
        recover(state, ticket, revoked)
    with pytest.raises(ApplicationActivationError):
        _require_no_pending_rollback(state.instance)
    assert state.key_path.read_bytes() == state.secret
    assert not state.database.exists()


@ROOT_ONLY
def test_real_fixed_installed_dispatch_recovery_and_resume(failed):
    state = failed

    class Metadata:
        def call(self, value):
            return dispatch(state.manager, value, application_root=state.runtime)

    arguments = dict(
        metadata=Metadata(),
        upload_root=state.archive.parent,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        coordinator_uid=1202,
        supervisor=state.supervisor,
    )
    payload = {
        "action": "recover_application_relational_preparation",
        "installation_id": 1,
        "actor_token": state.token,
        "source_preparation_id": state.source["preparation_id"],
        "source_namespace_id": state.namespace["preparation_id"],
        "expected_preparation_revision": action(state, state.source)["revision"],
        "expected_grant_record_revision": state.manager.inspect(1)[
            "grant_record_revision"
        ],
        "request_id": identity(),
        "confirm_restored_empty_checkpoint": True,
    }
    result = recover_installed_preparation(payload, **arguments)
    historical = coordinator.inspect_empty_recovery_record(
        state.manager,
        1,
        actor_token=state.token,
        source_recovery_id=result["preparation_id"],
    )
    assert historical["state"] == "confirmed" and not historical["resumption_reserved"]
    resumed = recover_installed_preparation(
        {
            "action": "resume_application_relational_preparation",
            "installation_id": 1,
            "actor_token": state.token,
            "source_recovery_id": result["preparation_id"],
            "expected_recovery_revision": historical["source_revision"],
            "expected_grant_record_revision": state.manager.inspect(1)[
                "grant_record_revision"
            ],
            "request_id": identity(),
            "confirm_owned_business_migrations": True,
        },
        **arguments,
    )
    assert resumed["outcome"] == "prepared_not_started" and state.database.exists()


@pytest.mark.parametrize(
    "field", ["path", "transport_secret", "service_uid", "automatic", "configuration"]
)
def test_helper_request_cannot_accept_package_paths_or_dependencies(stopped, field):
    payload = {
        "action": "recover_application_relational_preparation",
        "installation_id": 1,
        "actor_token": stopped.token,
        "source_preparation_id": identity(),
        "source_namespace_id": identity(),
        "expected_preparation_revision": identity(),
        "expected_grant_record_revision": identity(),
        "request_id": identity(),
        "confirm_restored_empty_checkpoint": True,
        field: "bad",
    }
    with pytest.raises(ValueError):
        preparation_recovery_request(payload)
