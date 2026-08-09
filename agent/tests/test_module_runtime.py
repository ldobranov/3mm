import hashlib, io, json, zipfile
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

def gpio_package(*, outputs={"gpio.output.1": True}, entrypoint=GPIO_ENTRYPOINT, rules=[]):
    manifest = {"manifest_version":2,"module_id":"org.3mm.gpio-test","name":"GPIO test","version":"1.0.0","runtimes":["agent"],"entrypoints":{"agent":entrypoint},"compatibility":{"protocol":"1.0","architectures":["aarch64"]},"permissions":["hardware.gpio","data.write"],"capabilities":{"provides":["gpio.digital.output"]},"configuration_defaults":{"inputs":["gpio.input.1"],"outputs":outputs,"rules":rules},"health_check":{"type":"file_exists","path":"health/ready"},"registrations":[{"kind":"capability","registration_id":"gpio.digital.control"}]}
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
    assert gpio.output("gpio.output.1").read() is True and events[0]["event_type"]=="gpio.input.changed"
