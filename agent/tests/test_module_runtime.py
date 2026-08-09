import hashlib, io, json, zipfile
import pytest
from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError

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
