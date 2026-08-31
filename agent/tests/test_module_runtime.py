import hashlib, io, json, time, zipfile
import pytest
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from agent.hardware import MockDigitalGpioDriver
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler

def package(version="1.0.0", healthy=True):
    manifest = {"manifest_version":2,"module_id":"org.3mm.demo","name":"Demo","version":version,"runtimes":["agent"],"compatibility":{"protocol":"1.0","architectures":["aarch64"]},"permissions":["data.write"],"capabilities":{"provides":["demo.ready"]},"health_check":{"type":"file_exists","path":"health/ready"},"registrations":[{"kind":"capability","registration_id":"demo.ready"}]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        z.writestr("manifest.json",json.dumps(manifest))
        if healthy:z.writestr("health/ready","ok")
    return out.getvalue()

def install(runtime, blob): return runtime.install(blob, expected_sha256=hashlib.sha256(blob).hexdigest())

def test_install_disable_preserves_data_and_registrations(tmp_path):
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64"); install(runtime,package())
    data=tmp_path/"modules/data/org.3mm.demo/value"; data.write_text("keep")
    assert runtime.registrations()[0]["registration_id"]=="demo.ready"
    runtime.disable("org.3mm.demo")
    assert data.read_text()=="keep" and runtime.registrations()==[]

def test_failed_update_keeps_prior_active_version(tmp_path):
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64"); install(runtime,package())
    with pytest.raises(ModuleLifecycleError,match="health"):
        install(runtime,package("2.0.0",healthy=False))
    assert runtime.state("org.3mm.demo")["active_version"]=="1.0.0"

def test_integrity_and_architecture_fail_closed(tmp_path):
    runtime=AgentModuleRuntime(tmp_path,architecture="x86_64"); blob=package()
    with pytest.raises(ModuleLifecycleError,match="integrity"): runtime.install(blob,expected_sha256="0"*64)
    with pytest.raises(ModuleLifecycleError,match="architecture"): install(runtime,blob)

def gpio_package(*, outputs={"gpio.output.1": True}, entrypoint=GPIO_ENTRYPOINT, rules=[], pulse_min_ms=50, pulse_max_ms=10000, pulse_cooldown_ms=0):
    manifest = {"manifest_version":2,"module_id":"org.3mm.gpio-test","name":"GPIO test","version":"1.0.0","runtimes":["agent"],"entrypoints":{"agent":entrypoint},"compatibility":{"protocol":"1.0","architectures":["aarch64"]},"permissions":["hardware.gpio","data.write"],"capabilities":{"provides":["gpio.digital.input","gpio.digital.output"]},"configuration_defaults":{"inputs":["gpio.input.1"],"outputs":outputs,"rules":rules,"pulse_min_ms":pulse_min_ms,"pulse_max_ms":pulse_max_ms,"pulse_cooldown_ms":pulse_cooldown_ms},"health_check":{"type":"file_exists","path":"health/ready"},"registrations":[{"kind":"capability","registration_id":"gpio.digital.input"},{"kind":"capability","registration_id":"gpio.digital.control"}]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        z.writestr("manifest.json",json.dumps(manifest)); z.writestr("health/ready","ok")
    return out.getvalue()

def test_trusted_gpio_entrypoint_activates_declared_capabilities(tmp_path):
    gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio)})
    install(runtime,gpio_package())
    assert gpio.output("gpio.output.1").read() is True
    result = runtime.invoke("gpio.digital.control", "set_output", {"capability_id": "gpio.output.1", "value": False})
    assert result["outputs"]["gpio.output.1"] is False
    state=json.loads((tmp_path/"modules/data/org.3mm.gpio-test/gpio-runtime.json").read_text())
    assert state["outputs"]=={"gpio.output.1":False}
    assert runtime.capability_states()["gpio.digital.input"] == {"gpio.input.1": False}
    assert runtime.capability_states()["gpio.digital.control"] == {"gpio.output.1": False}

def test_gpio_module_fails_closed_without_declared_capability_or_handler(tmp_path):
    gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio)})
    with pytest.raises(ModuleLifecycleError,match="capability"):
        install(runtime,gpio_package(outputs={"missing":True}))
    no_handler=AgentModuleRuntime(tmp_path/"other",architecture="aarch64")
    with pytest.raises(ModuleLifecycleError,match="entrypoint"):
        install(no_handler,gpio_package())

def test_gpio_module_is_reactivated_after_agent_runtime_restart(tmp_path):
    first_gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(first_gpio)})
    install(runtime,gpio_package())
    restarted_gpio=MockDigitalGpioDriver(outputs={"gpio.output.1":False})
    restarted=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(restarted_gpio)})
    restarted.start_active()
    assert restarted_gpio.output("gpio.output.1").read() is True

def test_gpio_local_rule_runs_and_emits_event_without_core(tmp_path):
    gpio=MockDigitalGpioDriver(); events=[]
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio,events.append)})
    blob=gpio_package(outputs={"gpio.output.1":False},rules=[{"input":"gpio.input.1","output":"gpio.output.1","when":True,"set":True}])
    install(runtime,blob); gpio.set_input("gpio.input.1",True)
    input_event = next(event for event in events if event["event_type"] == "gpio.input.changed")
    assert gpio.output("gpio.output.1").read() is True
    assert input_event["payload"] == {
        "capability_id": "gpio.digital.input",
        "channel": "gpio.input.1",
        "value": True,
        "sequence": 1,
    }


def test_gpio_pulse_restores_safe_state_and_emits_output_events(tmp_path):
    gpio=MockDigitalGpioDriver(); events=[]
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio,events.append)})
    install(runtime,gpio_package(outputs={"gpio.output.1":False},pulse_min_ms=20))

    result = runtime.invoke(
        "gpio.digital.control",
        "pulse_output",
        {"channel": "gpio.output.1", "duration_ms": 20},
    )

    assert result["pulse"] == {
        "channel": "gpio.output.1",
        "duration_ms": 20,
        "active_value": True,
        "safe_value": False,
    }
    assert gpio.output("gpio.output.1").read() is True
    deadline = time.monotonic() + 0.5
    while (
        (gpio.output("gpio.output.1").read() or len(events) < 2)
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)
    assert gpio.output("gpio.output.1").read() is False
    assert [event["payload"]["reason"] for event in events] == [
        "pulse_started",
        "pulse_completed",
    ]


def test_gpio_pulse_rejects_unsafe_duration_and_disable_restores_output(tmp_path):
    gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio)})
    install(runtime,gpio_package(outputs={"gpio.output.1":False},pulse_min_ms=20,pulse_max_ms=100))

    with pytest.raises(ModuleLifecycleError, match="between 20 and 100"):
        runtime.invoke(
            "gpio.digital.control",
            "pulse_output",
            {"channel": "gpio.output.1", "duration_ms": 101},
        )
    runtime.invoke(
        "gpio.digital.control",
        "pulse_output",
        {"channel": "gpio.output.1", "duration_ms": 100},
    )
    runtime.disable("org.3mm.gpio-test")

    assert gpio.output("gpio.output.1").read() is False


def test_gpio_runtime_shutdown_restores_output_without_disabling_module(tmp_path):
    gpio=MockDigitalGpioDriver()
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio)})
    install(runtime,gpio_package(outputs={"gpio.output.1":False},pulse_min_ms=20))
    runtime.invoke(
        "gpio.digital.control",
        "pulse_output",
        {"channel": "gpio.output.1", "duration_ms": 100},
    )

    runtime.close()

    assert gpio.output("gpio.output.1").read() is False
    assert runtime.state("org.3mm.gpio-test")["enabled"] is True


def test_gpio_input_change_is_published_without_an_automation_rule(tmp_path):
    gpio=MockDigitalGpioDriver(); events=[]
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio,events.append)})
    install(runtime,gpio_package(rules=[]))
    gpio.set_input("gpio.input.1",True)
    assert events == [{
        "event_type": "gpio.input.changed",
        "payload": {
            "capability_id": "gpio.digital.input",
            "channel": "gpio.input.1",
            "value": True,
            "sequence": 1,
        },
    }]


def test_gpio_update_replaces_old_event_subscriptions(tmp_path):
    gpio=MockDigitalGpioDriver(); events=[]
    runtime=AgentModuleRuntime(tmp_path,architecture="aarch64",runtime_handlers={GPIO_ENTRYPOINT:gpio_runtime_handler(gpio,events.append)})
    blob=gpio_package(rules=[])
    install(runtime,blob)
    install(runtime,blob)
    gpio.set_input("gpio.input.1",True)
    assert len(events) == 1
