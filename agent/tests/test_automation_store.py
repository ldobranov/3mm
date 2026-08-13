import pytest

from agent.automation_store import AutomationStore, StoredAutomation
from agent.hardware.gpio import MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from agent.tests.test_module_runtime import gpio_package, install


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def definition(device_id=DEVICE_ID):
    return {
        "schema_version": 1,
        "name": "Mirror input",
        "execution": "local",
        "enabled": True,
        "trigger": {"kind": "capability_event", "device_id": device_id, "capability_id": "gpio.digital.input", "event": "changed", "conditions": {"channel": "gpio.input.1", "value": True}},
        "actions": [{"kind": "capability_command", "device_id": device_id, "capability_id": "gpio.digital.control", "action": "set_output", "arguments": {"channel": "gpio.output.1", "value": True}}],
    }


def test_store_applies_and_removes_atomic_declarative_revision(tmp_path):
    store = AutomationStore(tmp_path)
    applied = store.apply(StoredAutomation(
        automation_id="ap_test", revision=1, revision_id="ar_one", definition=definition()
    ), device_id=DEVICE_ID)
    assert applied == {"automation_id": "ap_test", "revision": 1, "active": True}
    assert store.load()["ap_test"].definition.name == "Mirror input"
    assert store.remove("ap_test", 2)["active"] is False
    assert store.load() == {}


def test_store_rejects_wrong_device_and_stale_revision(tmp_path):
    store = AutomationStore(tmp_path)
    with pytest.raises(ValueError, match="different device"):
        store.apply(StoredAutomation(
            automation_id="ap_test", revision=1, revision_id="ar_one", definition=definition("dev_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        ), device_id=DEVICE_ID)
    store.apply(StoredAutomation(automation_id="ap_test", revision=2, revision_id="ar_two", definition=definition()), device_id=DEVICE_ID)
    with pytest.raises(ValueError, match="older"):
        store.apply(StoredAutomation(automation_id="ap_test", revision=1, revision_id="ar_one", definition=definition()), device_id=DEVICE_ID)


def test_deployed_automation_runs_locally_and_restores_after_restart(tmp_path):
    gpio = MockDigitalGpioDriver()
    runtime = AgentModuleRuntime(tmp_path, architecture="aarch64", runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio)})
    install(runtime, gpio_package(outputs={"gpio.output.1": False}))
    store = AutomationStore(tmp_path, runtime)
    store.apply(StoredAutomation(automation_id="ap_test", revision=1, revision_id="ar_one", definition=definition()), device_id=DEVICE_ID)

    gpio.set_input("gpio.input.1", True)
    assert gpio.output("gpio.output.1").read() is True

    restarted_gpio = MockDigitalGpioDriver()
    restarted = AgentModuleRuntime(tmp_path, architecture="aarch64", runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(restarted_gpio)})
    restarted.start_active()
    AutomationStore(tmp_path, restarted).activate_all(device_id=DEVICE_ID)
    restarted_gpio.set_input("gpio.input.1", True)
    assert restarted_gpio.output("gpio.output.1").read() is True
