import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError, OperationContext
from three_mm_application_sdk.transaction_guard import host_operation
from three_mm_protocol.application_delegation import DelegationReceiptV1


def result():
    return DelegationReceiptV1(delegation_id="a"*32, operation_id="read", module_id="org.example.app",
        status="succeeded", initiator=dict(kind="user",user_id=7,subject_id="usr_"+"7"*32),
        executor=dict(module_id="org.example.app",instance_id="b"*24,artifact_sha256="c"*64),
        expires_at=datetime.now(UTC)+timedelta(seconds=60), result={}, error_code=None).model_dump(mode="json")


def test_sdk_transports_only_the_ready_delegation_id_and_does_not_retry(monkeypatch):
    client = ApplicationPlatformClient(Path("unused"), "b"*24, b"k"*32)
    calls = []
    monkeypatch.setattr(client,"_call", lambda action,payload: calls.append((action,payload)) or result())
    assert client.execute_delegation("a"*32)["status"] == "succeeded"
    assert calls == [("delegation.execute",{"delegation_id":"a"*32})]
    def lost(action,payload):
        calls.append((action,payload)); raise ApplicationPlatformError("lost reply")
    monkeypatch.setattr(client,"_call",lost)
    with pytest.raises(ApplicationPlatformError): client.execute_delegation("a"*32)
    assert len(calls)==2
    with host_operation(), pytest.raises(RuntimeError, match="worker"):
        client.execute_delegation("a"*32)
    assert len(calls)==2


@pytest.mark.parametrize("fault", ["executor","request","retry","status"])
def test_sdk_refuses_foreign_or_malformed_receipts(monkeypatch,fault):
    client=ApplicationPlatformClient(Path("unused"),"b"*24,b"k"*32)
    value=result()
    if fault=="executor": value["executor"]["instance_id"]="d"*24
    if fault=="request": value["delegation_id"]="d"*32
    if fault=="retry": value["automatic_retry"]=True
    if fault=="status": value["status"]="pending"
    monkeypatch.setattr(client,"_call",lambda *_:value)
    with pytest.raises((ValueError,ApplicationPlatformError)): client.lookup_delegation("a"*32)


def test_context_separates_initiator_and_executor_and_refuses_promotion():
    receipt=result()
    delegation=dict(delegation_version=1,delegation_id="a"*32,operation_id="read",
        payload_sha256="d"*64, required_permission="records_read", initiator=receipt["initiator"],
        executor=receipt["executor"],expires_at=receipt["expires_at"],redelegation_allowed=False)
    raw=dict(audience="operator",user_id=7,subject_id="usr_"+"7"*32,permission_ids=["records_read"],platform_administrator=False,
        executor=receipt["executor"],delegation=delegation)
    context=OperationContext.from_platform(raw)
    assert context.initiator.user_id==7 and context.executor.instance_id=="b"*24
    assert not context.actor.platform_administrator and not context.delegation.redelegation_allowed
    for changed in ({"user_id":8},{"platform_administrator":True},{"audience":"administrator","platform_administrator":True},
            {"permission_ids":[]},{"executor":receipt["executor"] | {"instance_id":"e"*24}}):
        with pytest.raises(ValueError): OperationContext.from_platform(raw | changed)
