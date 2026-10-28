from dataclasses import FrozenInstanceError

import pytest

from three_mm_application_sdk import OperationContext


def test_human_actor_and_permissions_are_immutable_and_platform_role_is_separate():
    raw = dict(audience="operator", correlation_id="actor-test", user_id=7, subject_id="usr_"+"7"*32,
        platform_administrator=True, permission_ids=["records_read"])
    context = OperationContext.from_platform(raw)
    raw["permission_ids"].append("records_manage")
    assert context.actor.kind == "user" and context.actor.user_id == 7
    assert context.actor.platform_administrator is True
    assert context.permission_ids == ("records_read",)
    assert context.has_application_permission("records_read")
    assert not context.has_application_permission("records_manage")
    with pytest.raises(FrozenInstanceError):
        context.actor.user_id = 99
    with pytest.raises(FrozenInstanceError):
        context.permission_ids = ("records_manage",)


def test_kiosk_anonymous_and_internal_contexts_do_not_invent_a_human():
    kiosk = OperationContext.from_platform(dict(audience="kiosk", terminal_id="a" * 32))
    assert kiosk.actor.kind == "kiosk" and kiosk.actor.terminal_id == "a" * 32
    assert kiosk.user_id is None and not kiosk.has_application_permission("records_read")
    for audience, kind in (("public", "anonymous"), ("internal", "service")):
        actor = OperationContext.from_platform(dict(audience=audience)).actor
        assert actor.kind == kind and actor.user_id is None
        assert not actor.platform_administrator


@pytest.mark.parametrize("changed", [
    {"user_id": True}, {"user_id": "7"}, {"user_id": 0}, {"user_id": None},
    {"platform_administrator": "true"}, {"terminal_id": "a" * 32},
    {"permission_ids": "records_read"}, {"permission_ids": [True]},
    {"permission_ids": ["*"]}, {"permission_ids": ["records_read", "records_read"]},
    {"permission_ids": ["p_" + str(i) for i in range(97)]},
    {"machine": {}}, {"audience": "administrator", "platform_administrator": False},
])
def test_invalid_human_context_cannot_be_silently_downgraded(changed):
    with pytest.raises(ValueError):
        OperationContext.from_platform(dict(audience="operator", user_id=7, subject_id="usr_"+"7"*32) | changed)


@pytest.mark.parametrize("audience", ["public", "internal", "kiosk"])
@pytest.mark.parametrize("extra", [{"user_id": 1}, {"platform_administrator": True}, {"permission_ids": ["records_read"]}])
def test_nonhuman_context_cannot_borrow_human_rights(audience, extra):
    value = dict(audience=audience)
    if audience == "kiosk": value["terminal_id"] = "b" * 32
    with pytest.raises(ValueError):
        OperationContext.from_platform(value | extra)


@pytest.mark.parametrize("terminal", [None, True, "foreign", "../" + "a" * 32])
def test_kiosk_requires_the_core_terminal_identity(terminal):
    with pytest.raises(ValueError):
        OperationContext.from_platform(dict(audience="kiosk", terminal_id=terminal))


@pytest.mark.parametrize("audience", ["installation_peer", "installation_bootstrap"])
def test_installation_actor_is_not_a_delegated_user(audience):
    scopes = ["installation.status.report"] if audience == "installation_peer" else []
    machine = dict(installation_id="inst_" + "a" * 32, key_id="b" * 64,
        binding_id="peer_" + "c" * 32, generation=1, scopes=scopes)
    context = OperationContext.from_platform(dict(audience=audience, machine=machine))
    assert context.actor.kind == "installation" and context.actor.installation_id == machine["installation_id"]
    assert context.actor.user_id is None and not context.actor.platform_administrator
    assert context.permission_ids == () and context.machine.scopes == tuple(scopes)


def test_worker_actor_does_not_project_a_lease_or_claim_a_human_initiator():
    task = dict(task_run_id="task_" + "a" * 32, task_id="calculate", lease_token="b" * 64)
    context = OperationContext.from_platform(dict(audience="internal", task_execution=task))
    assert context.actor.kind == "worker" and context.actor.user_id is None
    assert not hasattr(context.actor, "lease_token")
    assert context.task_execution.task_run_id == task["task_run_id"]
    assert not context.has_application_permission("records_manage")


@pytest.mark.parametrize("audience", [None, {}, [], "future", True])
def test_unknown_or_wrong_type_audience_is_rejected(audience):
    with pytest.raises(ValueError):
        OperationContext.from_platform(dict(audience=audience))
