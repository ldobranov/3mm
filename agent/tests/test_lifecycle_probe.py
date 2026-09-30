"""Acceptance fixture: real package validation/lifecycle, simulated ARMv6 target."""

import hashlib
import importlib.util
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from agent.module_runtime import AgentModuleRuntime, ModuleLifecycleError
from backend.services.module_packages import validate_module_package


BUILDER = Path(__file__).resolve().parents[2] / "modules/agent-probe/build_package.py"
spec = importlib.util.spec_from_file_location("probe_builder", BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
MODULE_ID = "org.3mm.agent-probe"


def test_probe_is_deterministic_and_hardware_free():
    payload = builder.build_package()
    assert payload == builder.build_package()
    package = validate_module_package(payload, architecture="armv6l")
    assert package.manifest.module_id == MODULE_ID
    assert package.manifest.entrypoints == {}
    assert package.manifest.permissions == ()
    assert package.manifest.registrations == ()
    assert package.manifest.capabilities.provides == ()


def test_probe_install_restart_disable_retains_data(tmp_path):
    payload = builder.build_package()
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l")
    result = runtime.install(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    assert result.module_id == MODULE_ID and result.status == "active"
    assert runtime.state(MODULE_ID)["enabled"] is True
    data = runtime.root / "data" / MODULE_ID / "acceptance.txt"
    data.write_text("keep", encoding="utf-8")
    runtime.close()

    restarted = AgentModuleRuntime(tmp_path, architecture="armv6l")
    restarted.start_active()
    assert restarted.state(MODULE_ID)["enabled"] is True
    assert "runtime_error" not in restarted.state(MODULE_ID)
    assert restarted.registrations() == []
    assert restarted.capability_states() == {}
    assert restarted.disable(MODULE_ID).status == "disabled"
    assert restarted.state(MODULE_ID)["enabled"] is False
    assert data.read_text(encoding="utf-8") == "keep"


def test_probe_invalid_health_is_not_installed(tmp_path):
    payload = builder.build_package()
    damaged = io.BytesIO()
    with ZipFile(io.BytesIO(payload)) as source, ZipFile(damaged, "w") as target:
        target.writestr("manifest.json", source.read("manifest.json"))
        target.writestr("health/ready.json", "not-json")
    payload = damaged.getvalue()
    runtime = AgentModuleRuntime(tmp_path, architecture="armv6l")
    with pytest.raises(ModuleLifecycleError, match="health check"):
        runtime.install(payload, expected_sha256=hashlib.sha256(payload).hexdigest())
    assert runtime.state(MODULE_ID) == {}
