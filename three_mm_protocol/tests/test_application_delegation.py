from datetime import UTC, datetime
import pytest
from three_mm_protocol.application_delegation import (
    ActorAccessV1, DelegationCreateV1, DelegationReceiptV1, OperationDelegationV1,
)
from backend.tests.test_module_packages import application_definition
from three_mm_protocol import ApplicationExtensionV1


def executor(): return dict(kind="application", module_id="org.example.app", instance_id="a"*24, artifact_sha256="b"*64)
def receipt():
    return dict(delegation_version=1, delegation_id="c"*32, operation_id="read", module_id="org.example.app",
        status="pending", initiator=dict(kind="user", user_id=7, subject_id="usr_"+"7"*32), executor=executor(),
        expires_at=datetime.now(UTC), result=None, error_code=None, automatic_retry=False)


def test_only_explicit_bounded_operator_operations_can_be_delegated():
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["routes"][1]["delegated_operations"] = ["approve"]
    assert ApplicationExtensionV1.model_validate(definition).routes[1].delegated_operations == ("approve",)
    for changed in (dict(delegated_operations=["missing"]), dict(delegated_operations=["approve","approve"]),
            dict(audience="administrator", required_permissions=[])):
        bad = __import__("copy").deepcopy(definition); bad["routes"][1].update(changed)
        with pytest.raises(ValueError): ApplicationExtensionV1.model_validate(bad)
    for changed in (dict(timeout_seconds=11), dict(audiences=["administrator"]), dict(kind="task", audiences=["internal"])):
        bad = __import__("copy").deepcopy(definition); bad["operations"][2].update(changed)
        with pytest.raises(ValueError): ApplicationExtensionV1.model_validate(bad)


@pytest.mark.parametrize("field,value", [("user_id",7), ("executor",executor()), ("actor",{}), ("audience","administrator")])
def test_browser_create_cannot_choose_actor_executor_or_audience(field, value):
    with pytest.raises(ValueError):
        DelegationCreateV1.model_validate(dict(request_id="a"*32, operation_id="read", payload={}, **{field:value}))


@pytest.mark.parametrize("value", [dict(x=float("nan")), dict(x="x"*4097), dict(x="\ud800"), dict(x=2**53),
    dict(x="я"*3000), dict(x=object()), {str(i):i for i in range(2048)}])
def test_payload_is_finite_and_bounded(value):
    with pytest.raises(ValueError): DelegationCreateV1(request_id="a"*32, operation_id="read", payload=value)


@pytest.mark.parametrize("changes", [{"delegation_version":True}, {"automatic_retry":0}, {"automatic_retry":True},
    {"status":"succeeded"}, {"result":{}}, {"error_code":"expired"}, {"initiator":{"kind":"user","user_id":True}}])
def test_receipt_cannot_invent_success_or_retry(changes):
    with pytest.raises(ValueError): DelegationReceiptV1.model_validate(receipt() | changes)


def test_context_keeps_exact_scope_and_has_no_redelegation():
    value = dict(delegation_id="a"*32, operation_id="read", payload_sha256="b"*64,
        required_permission="records_read", initiator=dict(kind="user",user_id=7,subject_id="usr_"+"7"*32),
        executor=executor(), expires_at=datetime.now(UTC))
    assert OperationDelegationV1(**value).redelegation_allowed is False
    with pytest.raises(ValueError): OperationDelegationV1(**(value | {"redelegation_allowed":True}))


def test_access_snapshot_never_promotes_a_nonhuman_or_discloses_implicit_grants():
    base = dict(entrypoint_id="public", audience="public", built_ui_sha256=None,
        actor=dict(kind="anonymous",user_id=None,subject_id=None,terminal_id=None,platform_administrator=False),
        executor=executor(), permission_ids=[], allowed_operation_ids=[], delegated_operation_ids=[])
    assert ActorAccessV1(**base).service_authority == "separate"
    for change in ({"permission_ids":["read"]}, {"delegated_operation_ids":["read"]},
            {"actor":dict(kind="user",user_id=7,subject_id="usr_"+"7"*32,terminal_id=None,platform_administrator=False)}, {"access_version":True}):
        with pytest.raises(ValueError): ActorAccessV1.model_validate(base | change)
