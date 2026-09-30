"""GPIO configuration safety with isolated mock drivers, never physical pins."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from agent.config import AgentSettings
from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredential, OutboxStore, ReconciliationStore,
)
from agent.gpio_configuration import CHANNEL, GpioConfigurationManager
from agent.hardware import HardwareProfile, MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.modules.gpio import GPIO_ENTRYPOINT
from agent.physical_command_journal import PhysicalCommandFailure, PhysicalCommandJournal
from three_mm_protocol import AgentCommand, ModuleManifestV2


class RecordingDriver(MockDigitalGpioDriver):
    def __init__(self, factory, config):
        super().__init__(outputs={channel: False for channel in config["outputs"]} or None)
        self.factory = factory
        self.config = config
        self.closed = False

    def output(self, channel):
        if self.closed:
            raise RuntimeError("closed driver")
        original = super().output(channel)

        def write(value):
            self.factory.events.append(("write", self, channel, value))
            original.write(value)

        return SimpleNamespace(write=write, read=original.read)

    def close(self):
        self.factory.events.append(("close", self))
        self.closed = True
        super().close()


class RecordingFactory:
    def __init__(self):
        self.calls = []
        self.drivers = []
        self.events = []
        self.fail_calls = set()

    def __call__(self, profile, *, driver_name, chip, inputs, outputs):
        config = {"driver": driver_name, "chip": chip, "inputs": inputs, "outputs": outputs}
        self.calls.append(config)
        self.events.append(("create", config))
        if len(self.calls) in self.fail_calls:
            raise OSError("injected driver construction failure")
        driver = RecordingDriver(self, config)
        self.drivers.append(driver)
        return driver


def case(tmp_path, model="Raspberry Pi 3 Model B Plus Rev 1.3"):
    settings = AgentSettings(data_dir=tmp_path, hardware_profile=HardwareProfile.NATIVE)
    factory = RecordingFactory()
    manager = GpioConfigurationManager(settings, model=model, driver_factory=factory)
    runtime = AgentModuleRuntime(tmp_path, architecture="aarch64",
        runtime_handlers={GPIO_ENTRYPOINT: manager.handler(lambda _event: None)})
    return SimpleNamespace(settings=settings, factory=factory, manager=manager, runtime=runtime)


def request(subject, *, pin=17, driver="mock", revision=None):
    return {"expected_revision": revision or subject.manager.describe(subject.runtime)["revision"],
        "confirmed_safe": True, "configuration": {"driver": driver, "bcm_pin": pin}}


def manifest(configuration):
    return ModuleManifestV2.model_validate({
        "manifest_version": 2, "module_id": "org.3mm.configuration-test", "name": "Configuration test",
        "version": "1.0.0", "runtimes": ["agent"], "entrypoints": {"agent": GPIO_ENTRYPOINT},
        "compatibility": {"protocol": "1.0", "architectures": ["aarch64"]},
        "permissions": ["hardware.gpio", "data.write"],
        "capabilities": {"provides": ["gpio.digital.output"], "consumes": []},
        "configuration_defaults": configuration,
        "health_check": {"type": "file_exists", "path": "health/ready"},
        "registrations": [{"kind": "capability", "registration_id": "gpio.digital.control"}],
    })


def command(payload, *, key="configure-1", identifier="a", expired=False):
    now = datetime.now(UTC)
    return AgentCommand(command_id="cmd_" + identifier * 32, device_id="dev_" + "b" * 32,
        command_type="agent.gpio.configure", payload=payload, idempotency_key=key,
        created_at=now - timedelta(seconds=5) if expired else now,
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(seconds=10))


@pytest.mark.parametrize("pin", [True, 2, 14, 26])
def test_invalid_or_reserved_pin_is_rejected_without_hardware_touch(tmp_path, pin):
    subject = case(tmp_path)
    before = list(subject.factory.events)
    with pytest.raises(PhysicalCommandFailure) as failure:
        subject.manager.apply(request(subject, pin=pin), subject.runtime)
    assert failure.value.execution_state == "not_executed"
    assert subject.factory.events == before
    assert not subject.manager.path.exists()


def test_stale_revision_is_rejected_before_hardware_touch(tmp_path):
    subject = case(tmp_path)
    before = list(subject.factory.events)
    with pytest.raises(PhysicalCommandFailure, match="revision changed") as failure:
        subject.manager.apply(request(subject, revision="f" * 64), subject.runtime)
    assert failure.value.execution_state == "not_executed"
    assert subject.factory.events == before


def test_enabled_gpio_module_blocks_configuration_until_disabled(tmp_path):
    subject = case(tmp_path)
    subject.runtime._save_state("org.3mm.generic-device-module",
        {"enabled": True, "permissions": ["hardware.gpio"]})
    assert subject.manager.describe(subject.runtime)["blocking_modules"] == ["org.3mm.generic-device-module"]
    before = list(subject.factory.events)
    with pytest.raises(PhysicalCommandFailure, match="Disable all GPIO modules"):
        subject.manager.apply(request(subject), subject.runtime)
    assert subject.factory.events == before
    subject.runtime._save_state("org.3mm.generic-device-module",
        {"enabled": False, "permissions": ["hardware.gpio"]})
    assert subject.manager.apply(request(subject), subject.runtime)["gpio_configuration"]["source"] == "managed"


def test_valid_configuration_is_inactive_persistent_and_reloaded_before_modules(tmp_path):
    subject = case(tmp_path)
    original = subject.manager.driver
    original.output(CHANNEL).write(True)
    result = subject.manager.apply(request(subject, driver="gpiod", pin=27), subject.runtime)
    report = result["gpio_configuration"]
    assert original.closed
    assert report["source"] == "managed"
    assert report["outputs"] == {CHANNEL: 27}
    assert report["driver"] == "gpiod"
    assert subject.manager.driver.output(CHANNEL).read() is False
    assert json.loads(subject.manager.path.read_text()) == {"schema_version": 1, "driver": "gpiod", "bcm_pin": 27}
    assert subject.settings.gpio_driver == "mock"  # Startup/env configuration was not rewritten.
    writes = [event[3] for event in subject.factory.events if event[0] == "write" and event[1] is original]
    assert writes[-1] is False
    subject.manager.close()
    restored = GpioConfigurationManager(subject.settings, model="Raspberry Pi 3 Model B Plus Rev 1.3",
        driver_factory=subject.factory)
    assert restored.describe(subject.runtime)["revision"] == report["revision"]
    assert restored.driver.output(CHANNEL).read() is False
    assert subject.factory.calls[-1]["outputs"] == {CHANNEL: 27}
    restored.close()


def test_unsupported_board_allows_mock_but_refuses_native_mapping(tmp_path):
    subject = case(tmp_path, model="generic desktop")
    with pytest.raises(PhysicalCommandFailure, match="not supported on this board"):
        subject.manager.apply(request(subject, driver="gpiod"), subject.runtime)
    assert len(subject.factory.calls) == 1
    assert subject.manager.apply(request(subject), subject.runtime)["gpio_configuration"]["driver"] == "mock"


def test_shutdown_preserves_legacy_high_but_forces_managed_output_inactive(tmp_path):
    legacy = case(tmp_path / "legacy")
    legacy_driver = legacy.manager.driver
    legacy_driver.output(CHANNEL).write(True)
    before = len(legacy.factory.events)
    legacy.manager.close()
    assert legacy.factory.events[before:] == [("close", legacy_driver)]

    managed = case(tmp_path / "managed")
    managed.manager.apply(request(managed), managed.runtime)
    managed_driver = managed.manager.driver
    managed_driver.output(CHANNEL).write(True)
    before = len(managed.factory.events)
    managed.manager.close()
    assert managed.factory.events[before:] == [
        ("write", managed_driver, CHANNEL, False), ("close", managed_driver)]


@pytest.mark.parametrize("failure_kind", ["construction", "persistence"])
def test_failed_configuration_restores_previous_mapping_and_persistent_file(tmp_path, monkeypatch, failure_kind):
    subject = case(tmp_path)
    previous = subject.manager.apply(request(subject), subject.runtime)["gpio_configuration"]
    persisted = subject.manager.path.read_bytes()
    old_driver = subject.manager.driver
    if failure_kind == "construction":
        subject.factory.fail_calls.add(len(subject.factory.calls) + 1)
    else:
        import agent.gpio_configuration as gpio_configuration

        def fail_replace(*_args):
            raise OSError("injected atomic persistence failure")

        monkeypatch.setattr(gpio_configuration.os, "replace", fail_replace)
    queued = command(request(subject, pin=27))
    invoke = lambda: subject.manager.apply(queued.payload, subject.runtime)
    journal = PhysicalCommandJournal(tmp_path)
    failure = journal.execute(queued, invoke)
    assert failure.status == "failed"
    assert failure.output["execution_state"] == "rolled_back"
    assert "previous mapping restored" in failure.error
    assert old_driver.closed
    assert subject.manager.describe(subject.runtime)["revision"] == previous["revision"]
    assert subject.manager.path.read_bytes() == persisted
    assert subject.manager.driver.output(CHANNEL).read() is False
    assert subject.factory.calls[-1]["outputs"] == {CHANNEL: 17}
    if failure_kind == "persistence":
        assert subject.factory.drivers[-2].closed  # Candidate is released before rollback.
    before = list(subject.factory.events)
    assert PhysicalCommandJournal(tmp_path).execute(queued, invoke) == failure
    assert subject.factory.events == before


def test_rollback_failure_disables_control_and_fails_closed(tmp_path):
    subject = case(tmp_path)
    subject.manager.apply(request(subject), subject.runtime)
    persisted = subject.manager.path.read_bytes()
    subject.factory.fail_calls.update({len(subject.factory.calls) + 1, len(subject.factory.calls) + 2})
    with pytest.raises(PhysicalCommandFailure, match="rollback failed") as failure:
        subject.manager.apply(request(subject, pin=27), subject.runtime)
    assert failure.value.execution_state == "unknown"
    assert subject.manager.driver is None
    assert subject.manager.describe(subject.runtime)["configurable"] is False
    assert subject.manager.path.read_bytes() == persisted
    safe = manifest({"inputs": [], "outputs": {CHANNEL: False}, "rules": []})
    with pytest.raises(ModuleLifecycleError, match="operator recovery"):
        subject.manager.handler(lambda _event: None)(safe, tmp_path / "service")
    before = len(subject.factory.calls)
    with pytest.raises(PhysicalCommandFailure):
        subject.manager.apply(request(subject), subject.runtime)
    assert len(subject.factory.calls) == before


@pytest.mark.parametrize("unsafe", [
    {"inputs": [], "outputs": {CHANNEL: True}, "rules": []},
    {"inputs": ["gpio.input.1"], "outputs": {CHANNEL: False}, "rules": []},
    {"inputs": [], "outputs": {CHANNEL: False}, "rules": [{"set": True}]},
])
def test_managed_configuration_refuses_unsafe_module_defaults(tmp_path, unsafe):
    subject = case(tmp_path)
    subject.manager.apply(request(subject), subject.runtime)
    before = list(subject.factory.events)
    with pytest.raises(ModuleLifecycleError, match="inactive default"):
        subject.manager.handler(lambda _event: None)(manifest(unsafe), tmp_path / "service")
    assert subject.factory.events == before
    assert subject.manager.driver.output(CHANNEL).read() is False


def test_journal_replays_configuration_after_restart_and_expiry_without_new_attempt(tmp_path):
    subject = case(tmp_path)
    queued = command(request(subject))
    invoke = lambda: subject.manager.apply(queued.payload, subject.runtime)
    result = PhysicalCommandJournal(tmp_path).execute(queued, invoke, now=lambda: queued.created_at)
    assert result.status == "succeeded"
    before = list(subject.factory.events)
    replay = queued.model_copy(update={"command_id": "cmd_" + "c" * 32})
    cached = PhysicalCommandJournal(tmp_path).execute(replay, invoke, now=lambda: queued.expires_at)
    assert cached.status == "succeeded"
    assert cached.command_id == replay.command_id
    assert subject.factory.events == before
    expired = command(request(subject), key="expired", identifier="d", expired=True)
    rejected = PhysicalCommandJournal(tmp_path).execute(expired, invoke)
    assert rejected.output["execution_state"] == "not_executed"
    assert subject.factory.events == before


def test_publisher_routes_configure_and_reports_stale_revision_failure(tmp_path, monkeypatch):
    subject = case(tmp_path)
    initial_payload = request(subject)
    queued = command(initial_payload)
    posted = []
    selected = [queued]

    def get(url, **_kwargs):
        body = selected[0].model_dump(mode="json") if url.endswith("commands/next") else {
            "device_id": queued.device_id, "revision": 0, "state": {}, "updated_at": datetime.now(UTC).isoformat()}
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: body)

    monkeypatch.setattr("agent.core_client.requests.get", get)
    monkeypatch.setattr(CorePublisher, "_post", lambda _self, suffix, payload: posted.append((suffix, payload)))
    publisher = CorePublisher(core_url="http://invalid.test", credential=DeviceCredential(
        device_id=queued.device_id, credential_id="cred_" + "e" * 32, credential_secret="s" * 43),
        inventory_provider=lambda: None, command_journal=CommandJournal(tmp_path),
        reconciliation_store=ReconciliationStore(tmp_path), outbox=OutboxStore(tmp_path),
        started_monotonic=0, module_runtime=subject.runtime, gpio_configuration=subject.manager)
    excessive_ttl = command(initial_payload, key="long-deadline", identifier="c")
    selected[0] = excessive_ttl.model_copy(update={
        "expires_at": excessive_ttl.created_at + timedelta(seconds=11)})
    before = list(subject.factory.events)
    publisher._poll_command()
    assert posted[0][1]["status"] == "failed"
    assert posted[0][1]["output"]["execution_state"] == "not_executed"
    assert "at most ten seconds" in posted[0][1]["error"]
    assert subject.factory.events == before
    assert not subject.manager.path.exists()
    posted.clear()
    selected[0] = queued
    publisher._poll_command()
    assert posted[0][1]["status"] == "succeeded"
    assert posted[1][0] == "reported-state"
    assert posted[1][1]["state"]["gpio_configuration"]["source"] == "managed"
    before = list(subject.factory.events)
    publisher._poll_command()
    assert subject.factory.events == before
    selected[0] = command(initial_payload, key="stale-revision", identifier="f")
    publisher._poll_command()
    assert posted[-2][1]["status"] == "failed"
    assert posted[-2][1]["output"]["execution_state"] == "not_executed"
    assert "revision changed" in posted[-2][1]["error"]
    assert subject.factory.events == before
