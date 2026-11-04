from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from agent.config import AgentSettings
from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredential, OutboxStore, ReconciliationStore,
)
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.modules.character_display import character_display_handler
from agent.physical_command_journal import PhysicalCommandJournal
from backend.services.module_packages import validate_module_package
from three_mm_protocol import AgentCommand
from three_mm_protocol.capability_contracts import CapabilityContractError
from three_mm_protocol.character_display import (
    CharacterDisplayProfileV1, DISPLAY_CAPABILITY, DISPLAY_ENTRYPOINT,
)
from three_mm_protocol.hardware_profiles import AgentHardwareApprovalV1

DEVICE_ID = 'dev_' + 'a' * 32


@pytest.fixture
def builder():
    source = Path(__file__).resolve().parents[2] / "modules/character-display/build_package.py"
    spec = importlib.util.spec_from_file_location("character_display_fixture", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installed(tmp_path, builder, *, profile=None, approved_profile=""):
    blob = builder.build_package(profile)
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l", device_id=DEVICE_ID, runtime_handlers={
        DISPLAY_ENTRYPOINT: character_display_handler(native_allowed=True,
                                                      lock_dir=tmp_path / "display-locks")})
    sha = hashlib.sha256(blob).hexdigest()
    approval = (AgentHardwareApprovalV1(device_id=DEVICE_ID, package_sha256=sha,
                profile_sha256=approved_profile).model_dump() if approved_profile else None)
    runtime.install(blob, expected_sha256=sha, hardware_profile_approval=approval)
    return runtime


def arguments(profile=None, **changes):
    profile = profile or CharacterDisplayProfileV1()
    return {"display_id": profile.display_id, "profile_sha256": profile.digest(),
            "text": "BTC/USD\n123.45", "backlight": True, **changes}


def invoke(runtime, args=None, **changes):
    contract = CharacterDisplayProfileV1().contract()
    return runtime.invoke(DISPLAY_CAPABILITY, "write_frame", args or arguments(),
                          **{"contract_version": "2.0", "contract_digest": contract.digest(), **changes})


@pytest.mark.parametrize('columns', [16,20,24,40])
def test_profile_size_controls_mock_state_frame_and_immutable_package_identity(tmp_path,builder,columns):
    profile=CharacterDisplayProfileV1(columns=columns)
    runtime=installed(tmp_path,builder,profile=profile)
    try:
        assert len(runtime.capability_states()[DISPLAY_CAPABILITY]['text'].split('\n')[0]) == columns
        result=invoke(runtime,arguments(profile),contract_digest=profile.contract().digest())
        assert result['text']=='BTC/USD'.ljust(columns)+'\n'+'123.45'.ljust(columns)
        assert result['profile_sha256']==profile.digest()
        assert builder.manifest(profile)['configuration_defaults']['columns']==columns
        with pytest.raises(CapabilityContractError):
            invoke(runtime,arguments(profile,text='x'*(columns+1)+'\nok'),contract_digest=profile.contract().digest())
    finally:
        runtime.close()


def test_deterministic_package_uses_normal_core_validation_and_no_code_or_raw_io(builder):
    blob = builder.build_package()
    assert blob == builder.build_package()
    validated = validate_module_package(blob, architecture="armv6l")
    assert validated.manifest.permissions == ("hardware.display",)
    assert validated.manifest.registrations[0].contract == CharacterDisplayProfileV1().contract()
    with ZipFile(io.BytesIO(blob)) as archive:
        assert set(archive.namelist()) == {"manifest.json", "health/ready"}


@pytest.mark.parametrize('changes', [
    {'columns': 16}, {'columns': 24}, {'columns': 40}, {'columns': 20, 'rows': 4},
    {'columns': 21, 'rows': 4}, {'rows': 3}, {'address': 0x28},
    {'controller': 'other'}, {'pin_map': 'other'},
])
def test_inert_builder_and_independent_native_driver_agree_on_supported_topology(builder, tmp_path, changes):
    from agent.hardware.character_display import NativeCharacterDisplay
    profile = CharacterDisplayProfileV1(driver='pcf8574', **changes)
    try:
        native = NativeCharacterDisplay(profile, tmp_path)
    except ValueError:
        with pytest.raises(ValueError): builder.build_package(profile)
    else:
        assert builder.build_package(profile)
        native.close()


def test_native_requires_installation_consent_not_an_ambient_environment_flag(tmp_path, builder, monkeypatch):
    monkeypatch.setenv('THREE_MM_CHARACTER_DISPLAY_DRIVER', 'pcf8574')
    monkeypatch.setenv('THREE_MM_CHARACTER_DISPLAY_APPROVED_PROFILE', 'a'*64)
    with pytest.raises(ModuleLifecycleError, match='approval is required'):
        installed(tmp_path, builder, profile=CharacterDisplayProfileV1(driver='pcf8574'))
    assert not (tmp_path/'modules/releases').exists()


def test_mock_writes_complete_padded_frames_and_close_does_not_restore_a_saved_frame(tmp_path, builder):
    runtime = installed(tmp_path, builder)
    before = runtime.capability_states()[DISPLAY_CAPABILITY]
    assert before["has_frame"] is False and before["simulated"] is True
    assert runtime.capability_healthy(DISPLAY_CAPABILITY)
    result = invoke(runtime)
    assert result == {**before, "has_frame": True, "text": "BTC/USD".ljust(20)+'\n'+"123.45".ljust(20), "backlight": True,
                      "last_write_at": result["last_write_at"]}
    assert datetime.fromisoformat(result["last_write_at"]).utcoffset() == timedelta(0)
    assert runtime.capability_states()[DISPLAY_CAPABILITY]["last_write_at"] == result["last_write_at"]
    assert invoke(runtime, arguments(text="\n", backlight=False))["text"] == ' '*20+'\n'+' '*20
    runtime.disable(builder.manifest(CharacterDisplayProfileV1())["module_id"])
    assert runtime.capability_states() == {}
    with pytest.raises(ModuleLifecycleError, match="capability is unavailable"):
        invoke(runtime)
    # Reinstall/Agent restart never replay a frame just because it was saved.
    installed(tmp_path, builder).close()
    restarted = AgentModuleRuntime(tmp_path, architecture="armv6l", runtime_handlers={
        DISPLAY_ENTRYPOINT: character_display_handler(lock_dir=tmp_path / "display-locks")})
    restarted.start_active()
    assert restarted.capability_states()[DISPLAY_CAPABILITY]["has_frame"] is False
    restarted.close()


@pytest.mark.parametrize("args, binding", [
    ({"text": "x" * 21+'\nok'}, {}), ({"text": "\n\n"}, {}),
    ({"text": "Курс\nok"}, {}), ({"backlight": 1}, {}),
    ({"profile_sha256": "0" * 64}, {}), ({"address": 0x28}, {}),
    ({}, {"contract_digest": "0" * 64}), ({}, {"contract_version": "1.0"}),
])
def test_invalid_arguments_or_contract_never_reach_the_driver(tmp_path, builder, monkeypatch, args, binding):
    runtime = installed(tmp_path, builder)
    def forbidden(*_args):
        pytest.fail("Invalid request reached a display driver")
    monkeypatch.setattr("agent.modules.character_display.MockCharacterDisplay.write_frame", forbidden)
    with pytest.raises(CapabilityContractError):
        invoke(runtime, arguments(**args), **binding)
    assert runtime.capability_states()[DISPLAY_CAPABILITY]["has_frame"] is False


def test_manifest_cannot_lie_about_its_hardware_binding(tmp_path, builder):
    manifest = builder.manifest(CharacterDisplayProfileV1())
    manifest["configuration_defaults"]["address"] = 0x26
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("health/ready", "ok")
    blob = output.getvalue()
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l", runtime_handlers={
        DISPLAY_ENTRYPOINT: character_display_handler(lock_dir=tmp_path / "display-locks")})
    # The generic profile check now rejects the changed configuration before
    # extraction/activation, rather than relying on the provider-specific gate.
    with pytest.raises(ModuleLifecycleError, match="Hardware profile digest does not match configuration"):
        runtime.install(blob, expected_sha256=hashlib.sha256(blob).hexdigest())
    assert runtime.capability_states() == {}
    assert not (runtime.root/'releases').exists()


def command(**changes):
    now = datetime.now(UTC)
    return AgentCommand(command_id="cmd_" + "a" * 32, device_id="dev_" + "b" * 32,
        command_type="application.capability.invoke", idempotency_key="display-frame-1",
        created_at=now, expires_at=now + timedelta(seconds=10), payload={
            "capability_id": DISPLAY_CAPABILITY, "contract_version": "2.0",
            "contract_digest": CharacterDisplayProfileV1().contract().digest(),
            "action": "write_frame", "arguments": arguments()}, **changes)


def test_mock_journal_does_not_repeat_a_write_and_fences_changed_content(tmp_path, builder, monkeypatch):
    runtime = installed(tmp_path / "runtime", builder)
    calls = []
    monkeypatch.setattr("agent.modules.character_display.MockCharacterDisplay.write_frame", lambda *args: calls.append(args))
    request = command()
    journal = PhysicalCommandJournal(tmp_path / "journal")
    first = journal.execute(request, lambda: invoke(runtime))
    assert first.status == "succeeded" and first.output["simulated"] is True
    assert journal.execute(request, lambda: invoke(runtime)) == first
    changed = request.model_copy(update={"payload": {**request.payload, "arguments": arguments(text="ETH/USD\n123.45")}})
    assert journal.execute(changed, lambda: invoke(runtime)).output["execution_state"] == "conflict"
    assert len(calls) == 1


def test_unknown_driver_failure_is_not_retried_or_reported_as_current(tmp_path, builder, monkeypatch):
    runtime = installed(tmp_path / "runtime", builder)
    calls = []
    def broken(*args):
        calls.append(1)
        raise OSError("simulated partial write")
    monkeypatch.setattr("agent.modules.character_display.MockCharacterDisplay.write_frame", broken)
    journal = PhysicalCommandJournal(tmp_path / "journal")
    request = command()
    result = journal.execute(request, lambda: invoke(runtime))
    assert result.status == "failed" and result.output["execution_state"] == "unknown"
    assert journal.execute(request, lambda: invoke(runtime)) == result
    assert len(calls) == 1
    assert not runtime.capability_healthy(DISPLAY_CAPABILITY)
    assert runtime.capability_states()[DISPLAY_CAPABILITY]["has_frame"] is False


@pytest.mark.parametrize("outcome", ["approved", "denied", "offline", "expired", "invalid_text"])
def test_application_command_uses_the_live_permit_deadline_and_normal_agent_path(
        tmp_path, builder, monkeypatch, outcome):
    runtime = installed(tmp_path / "runtime", builder)
    request = command()
    if outcome == "expired":
        request = request.model_copy(update={"expires_at": request.created_at - timedelta(seconds=1)})
    if outcome == "invalid_text":
        request = request.model_copy(update={"payload": {**request.payload, "arguments": arguments(text="ok\n\x1b")}})
    calls, permits, results = [], [], []
    monkeypatch.setattr("agent.modules.character_display.MockCharacterDisplay.write_frame", lambda *args: calls.append(args))

    class Transport:
        device_id = request.device_id

        def receive_command(self, *, timeout_seconds):
            return request

        def authorize_execution(self, command_id):
            permits.append(command_id)
            if outcome == "offline":
                raise ConnectionError("Core unavailable")
            return {"command_id": command_id, "authorized": outcome != "denied"}

    monkeypatch.setattr(CorePublisher, "_post", lambda *args: None)
    monkeypatch.setattr(CorePublisher, "_submit_result", lambda self, result: results.append(result))
    publisher = CorePublisher(core_url="http://core.test",
        credential=DeviceCredential(device_id=request.device_id, credential_id="cred_" + "c" * 32,
                                    credential_secret="test-secret-" + "x" * 32),
        inventory_provider=lambda: None, command_journal=CommandJournal(tmp_path / "agent"),
        reconciliation_store=ReconciliationStore(tmp_path / "agent"),
        outbox=OutboxStore(tmp_path / "agent"), started_monotonic=0,
        module_runtime=runtime, capability_availability=True, transport=Transport())
    publisher._poll_command()
    publisher._poll_command()  # Same delivery cannot cause another driver attempt/permit.
    assert results[0] == results[1]
    if outcome == "approved":
        assert results[0].status == "succeeded" and results[0].output["simulated"] is True
        assert len(calls) == 1
    else:
        assert results[0].output["execution_state"] == "not_executed"
        assert calls == []
    assert len(permits) == (0 if outcome == "expired" else 1)
    runtime.close()


def test_unavailable_optional_display_does_not_prevent_agent_readiness(tmp_path, builder):
    from fastapi.testclient import TestClient
    from agent.hardware import HardwareProfile
    from agent.main import create_app

    # An enabled native provider belongs to another device identity. Agent/Core
    # must still boot without activating it or silently falling back to mock.
    native = CharacterDisplayProfileV1(driver='pcf8574')
    installed(tmp_path, builder, profile=native, approved_profile=native.digest()).close()
    settings = AgentSettings(data_dir=tmp_path, provisioning_data_dir=tmp_path / "provisioning",
                             hardware_profile=HardwareProfile.MOCK_PI3)
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").json()["status"] == "ready"
    module_id = builder.manifest(native)["module_id"]
    state = json.loads((tmp_path / "modules/state" / (module_id + ".json")).read_text())
    assert state["runtime_error"]


def test_native_requires_separate_exact_local_approval_and_does_not_write_at_activation(
        tmp_path, builder, monkeypatch):
    from agent.hardware.character_display import NativeCharacterDisplay

    native = CharacterDisplayProfileV1(driver="pcf8574")
    assert native.contract().digest() != CharacterDisplayProfileV1().contract().digest()
    assert builder.manifest(native)["module_id"] != builder.manifest(CharacterDisplayProfileV1())["module_id"]
    assert validate_module_package(builder.build_package(native)).manifest.registrations[0].metadata["simulated"] is False
    for approval in ('', CharacterDisplayProfileV1().digest()):
        with pytest.raises(ModuleLifecycleError, match='approval'):
            installed(tmp_path, builder, profile=native, approved_profile=approval)
    def forbidden(*_args, **_kwargs):
        pytest.fail("Activation/probe/close must not write to hardware")
    monkeypatch.setattr(NativeCharacterDisplay, "write_frame", forbidden)
    monkeypatch.setattr(NativeCharacterDisplay, "is_available", lambda self: False)
    runtime = installed(tmp_path, builder, profile=native, approved_profile=native.digest())
    assert runtime.capability_states()[DISPLAY_CAPABILITY]["has_frame"] is False
    assert not runtime.capability_healthy(DISPLAY_CAPABILITY)
    runtime.close()


def test_native_is_refused_on_a_mock_agent_even_with_an_approved_profile(tmp_path, builder):
    profile = CharacterDisplayProfileV1(driver="pcf8574")
    blob = builder.build_package(profile)
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l", device_id=DEVICE_ID, runtime_handlers={
        DISPLAY_ENTRYPOINT: character_display_handler(native_allowed=False, lock_dir=tmp_path / "display-locks")})
    with pytest.raises(ModuleLifecycleError, match="native Agent hardware profile"):
        sha = hashlib.sha256(blob).hexdigest()
        runtime.install(blob, expected_sha256=sha, hardware_profile_approval={
            'device_id': DEVICE_ID, 'package_sha256': sha, 'profile_sha256': profile.digest()})


def test_authoritative_command_deadline_reaches_native_worker(tmp_path, builder, monkeypatch):
    from agent.hardware.character_display import NativeCharacterDisplay

    profile = CharacterDisplayProfileV1(driver="pcf8574")
    runtime = installed(tmp_path, builder, profile=profile, approved_profile=profile.digest())
    received = []
    monkeypatch.setattr(NativeCharacterDisplay, "write_frame",
                        lambda self, *args, not_after: received.append(not_after))
    deadline = datetime.now(UTC) + timedelta(seconds=2)
    result = runtime.invoke(DISPLAY_CAPABILITY, "write_frame", arguments(profile),
        contract_version="2.0", contract_digest=profile.contract().digest(), not_after=deadline)
    assert received == [deadline]
    assert result["simulated"] is False
    runtime.close()
