"""Actual first preparation: fresh root key -> two Core consents -> UID worker."""

import os
import sqlite3
import stat

import pytest
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services import application_relational_lifecycle as coordinator
from backend.tests.test_application_relational_migrations import candidate, script
from backend.tests.test_application_relational_namespace import (
    ROOT_ONLY,
    absent_paths,
    action,
    identity,
    managed_installed,
    source_installed,
    source_subject,
    stopped,
)
from three_mm_application_sdk.relational_wire import (
    canonical,
    prepared_lifecycle,
    sign_metadata,
)
from three_mm_runtime import application_relational_installation as helper
from three_mm_runtime import application_relational_namespace as namespace
from three_mm_runtime.application_activation import (
    ApplicationActivationError,
    _require_no_pending_rollback,
)
from three_mm_runtime.application_relational_session import _prepared

pytestmark = [
    ROOT_ONLY,
    pytest.mark.skipif(os.name != "posix", reason="Real POSIX preparation"),
]


@pytest.fixture
def initial(absent_paths, tmp_path):
    state = absent_paths
    for directory in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        directory.chmod(directory.stat().st_mode | 0o111)
    candidate(state, script())
    state.issued = []
    state.expected_grant = state.manager.inspect(1)["grant_record_revision"]
    return state


def issuers(state):
    def issue_namespace(**kw):
        value = coordinator.issue_namespace_preparation(
            state.manager,
            1,
            actor_token=state.token,
            expected_grant_record_revision=state.expected_grant,
            confirm_fresh_owned_namespace=True,
            service_uid=1200,
            service_gid=1201,
            coordinator_uid=1202,
            **kw,
        )
        state.issued.append(value)
        return value

    def issue_migration(**kw):
        assert not state.database.exists()
        assert len(state.issued) == 1
        assert action(state, state.issued[0])["state"] == "prepared"
        value = coordinator.issue_migrated_schema_preparation(
            state.manager,
            1,
            actor_token=state.token,
            expected_grant_record_revision=state.expected_grant,
            confirm_owned_business_migrations=True,
            **kw,
        )
        state.issued.append(value)
        return value

    return issue_namespace, issue_migration


def run(state, **changes):
    issue_namespace, issue_migration = issuers(state)
    return helper.prepare_fresh_relational_installation(
        state.archive,
        **{
            "configuration": state.configuration,
            "root": state.runtime,
            "key_root": state.transport_keys,
            "state_root": state.helper_state,
            "service_uid": 1200,
            "service_gid": 1201,
            "coordinator_uid": 1202,
            "confirm_fresh_owned_namespace": True,
            "confirm_owned_business_migrations": True,
            "issue_namespace": issue_namespace,
            "issue_migration": issue_migration,
            "checkpoint": lambda *a, **kw: coordinator.preparation_checkpoint(
                state.manager, 1, *a, actor_token=state.token, **kw
            ),
            "supervisor": state.supervisor,
            **changes,
        },
    )


def test_real_first_preparation_is_disabled_bounded_nonroot_and_keeps_protected_handoff(
    initial,
):
    state = initial
    result = run(state)
    source, migration = state.issued
    assert result["namespace"]["outcome"] == "namespace_created_not_started"
    assert result["database"]["outcome"] == "prepared_not_started"
    secret = state.key_path.read_bytes()
    assert len(secret) == 32 and secret != b"t" * 32
    assert helper._read_bootstrap_secret(state.helper_state, source) == secret
    info = helper._handoff_path(state.helper_state, source).stat()
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o600)
    assert secret.hex() not in canonical(result).decode()
    assert _prepared(state.instance, secret) == prepared_lifecycle(migration, secret)
    assert state.database.stat().st_uid == 1200
    with sqlite3.connect(state.database) as db:
        assert db.execute(
            "SELECT revision FROM three_mm_schema_migrations"
        ).fetchall() == [("0001",), ("0002",)]
        assert db.execute("SELECT migrated FROM business").fetchall() == []
    with Session(state.engine) as db:
        assert not db.get(Installation, 1).enabled
    assert state.calls == [("stop", state.instance.name), ("stop", state.instance.name)]
    before = state.database.read_bytes()
    with pytest.raises(helper.RelationalPreparationError, match="absent namespace"):
        run(state)
    assert (
        state.database.read_bytes() == before and state.key_path.read_bytes() == secret
    )


@pytest.mark.parametrize(
    "flag", ["confirm_fresh_owned_namespace", "confirm_owned_business_migrations"]
)
def test_both_explicit_consents_required_before_any_issuance_or_effect(initial, flag):
    with pytest.raises(helper.RelationalPreparationError, match="Explicit"):
        run(initial, **{flag: False})
    assert not initial.issued and not initial.instance.exists()
    assert not list(initial.helper_state.glob("namespace-key-*.key"))


def test_revocation_after_namespace_does_not_issue_or_run_migrations(initial):
    state = initial

    def revoked(value, phase, **kw):
        result = coordinator.preparation_checkpoint(
            state.manager, 1, value, phase, actor_token=state.token, **kw
        )
        if value["action"] == "create_owned_namespace" and phase == "finish":
            state.manager.revoke(
                1,
                actor_token=state.token,
                request_id=identity(),
                expected_revision=state.expected_grant,
            )
        return result

    with pytest.raises(authority.AuthorityManagementError):
        run(state, checkpoint=revoked)
    assert len(state.issued) == 1
    assert state.key_path.exists() and not state.database.exists()
    assert not (state.instance / "active.json").exists()


def test_partial_actual_key_write_retains_fresh_secret_for_explicit_recovery(
    initial, monkeypatch
):
    state = initial
    original = namespace._exclusive_file

    def partial(path, content, mode, gid):
        if path == state.key_path:
            original(path, content[:4], mode, gid)
            raise OSError("injected incomplete key")
        return original(path, content, mode, gid)

    monkeypatch.setattr(namespace, "_exclusive_file", partial)
    with pytest.raises(helper.RelationalPreparationError):
        run(state)
    assert len(state.issued) == 1
    source = state.issued[0]
    secret = helper._read_bootstrap_secret(state.helper_state, source)
    assert len(secret) == 32 and state.key_path.read_bytes() == secret[:4]
    assert not state.database.exists() and state.marker.exists()
    with pytest.raises(ApplicationActivationError):
        _require_no_pending_rollback(state.instance)


def test_lost_namespace_finish_ack_never_runs_or_reissues_migrations(initial):
    state = initial

    def lost(value, phase, **kw):
        result = coordinator.preparation_checkpoint(
            state.manager, 1, value, phase, actor_token=state.token, **kw
        )
        if phase == "finish":
            raise OSError("lost namespace completion")
        return result

    with pytest.raises(helper.RelationalPreparationError):
        run(state, checkpoint=lost)
    assert len(state.issued) == 1
    assert action(state, state.issued[0])["state"] == "prepared"
    assert state.marker.exists() and not state.database.exists()
    assert (
        helper._read_bootstrap_secret(state.helper_state, state.issued[0])
        == state.key_path.read_bytes()
    )


def test_real_partial_handoff_quarantine_then_fresh_install_uses_new_key(
    initial, monkeypatch
):
    from backend.services import application_relational_namespace_recovery as recovery
    from three_mm_runtime.application_relational_namespace_recovery import (
        reconcile_empty_relational_namespace,
    )

    state = initial
    original = namespace._exclusive_file

    def partial(path, content, mode, gid):
        if path == state.key_path:
            original(path, content[:4], mode, gid)
            raise OSError("injected partial key")
        return original(path, content, mode, gid)

    with monkeypatch.context() as patch:
        patch.setattr(namespace, "_exclusive_file", partial)
        with pytest.raises(helper.RelationalPreparationError):
            run(state)
    source = state.issued[0]
    old_secret = helper._read_bootstrap_secret(state.helper_state, source)
    value = recovery.issue_namespace_recovery(
        state.manager,
        1,
        actor_token=state.token,
        request_id=identity(),
        source_preparation_id=source["preparation_id"],
        expected_grant_record_revision=state.expected_grant,
        choice="quarantine",
        confirm_empty_bootstrap_reviewed=True,
        transport_secret=old_secret,
    )
    reconcile_empty_relational_namespace(
        state.archive,
        value,
        source,
        configuration=state.configuration,
        transport_secret=old_secret,
        root=state.runtime,
        key_root=state.transport_keys,
        state_root=state.helper_state,
        service_uid=1200,
        service_gid=1201,
        coordinator_uid=1202,
        supervisor=state.supervisor,
        checkpoint=lambda *a, **kw: recovery.namespace_recovery_checkpoint(
            state.manager,
            1,
            *a,
            actor_token=state.token,
            transport_secret=old_secret,
            **kw,
        ),
    )
    assert action(state, source)["state"] == "execution_unconfirmed"
    assert helper._read_bootstrap_secret(state.helper_state, source) == old_secret
    state.issued = []
    result = run(state)
    assert result["database"]["outcome"] == "prepared_not_started"
    assert state.key_path.read_bytes() != old_secret
    assert helper._read_bootstrap_secret(state.helper_state, source) == old_secret


def test_a_different_grant_epoch_in_second_ticket_cannot_silently_replace_first_consent(
    initial,
):
    state = initial
    _, real = issuers(state)

    def changed(**kw):
        original = real(**kw)
        return sign_metadata(
            kw["transport_secret"],
            "migration_preparation",
            {**original, "authority_epoch": identity()},
        )

    with pytest.raises(helper.RelationalPreparationError, match="between consents"):
        run(state, issue_migration=changed)
    assert not state.database.exists()
    assert action(state, state.issued[1])["state"] == "recorded"


@pytest.mark.parametrize("problem", ["hardlink", "mode", "bytes", "source"])
def test_bootstrap_handoff_is_exact_root_protected_and_not_arbitrary_key_retrieval(
    initial, problem
):
    state = initial
    run(state)
    source = state.issued[0]
    path = helper._handoff_path(state.helper_state, source)
    if problem == "hardlink":
        os.link(path, state.helper_state / "alias")
    elif problem == "mode":
        path.chmod(0o640)
    elif problem == "bytes":
        path.write_bytes(b"x" * 32)
    else:
        source = {**source, "preparation_id": identity()}
    with pytest.raises((ValueError, OSError)):
        helper._read_bootstrap_secret(state.helper_state, source)
