"""Transactional, data-preserving Agent module lifecycle."""
from __future__ import annotations
import hashlib, io, json, os, shutil, tempfile, zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from pydantic import ValidationError
from three_mm_protocol import ModuleManifestV2, meets_minimum_version
from agent import __version__

AGENT_ALLOWED_PERMISSIONS = {"data.read", "data.write", "events.publish", "network.outbound", "process.spawn", "hardware.inventory", "hardware.gpio"}

class ModuleLifecycleError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class ModuleRuntimeResult:
    module_id: str
    version: str
    status: str
    previous_version: str | None = None

RuntimeHandler = Callable[[ModuleManifestV2, Path], None]

class AgentModuleRuntime:
    def __init__(self, data_dir: Path, *, architecture: str, protocol_version: str = "1.0", runtime_handlers: dict[str, RuntimeHandler] | None = None):
        self.root = data_dir / "modules"
        self.architecture = architecture
        self.protocol_version = protocol_version
        self.runtime_handlers = dict(runtime_handlers or {})

    def _state_path(self, module_id: str) -> Path:
        return self.root / "state" / f"{module_id}.json"

    def state(self, module_id: str) -> dict:
        path = self._state_path(module_id)
        return json.loads(path.read_text()) if path.exists() else {}

    def _save_state(self, module_id: str, state: dict) -> None:
        path = self._state_path(module_id); path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp"); temp.write_text(json.dumps(state, indent=2) + "\n")
        os.chmod(temp, 0o600); os.replace(temp, path)

    def install(self, package: bytes, *, expected_sha256: str) -> ModuleRuntimeResult:
        if hashlib.sha256(package).hexdigest() != expected_sha256:
            raise ModuleLifecycleError("package integrity mismatch")
        try:
            archive = zipfile.ZipFile(io.BytesIO(package))
            manifest = ModuleManifestV2.model_validate(json.loads(archive.read("manifest.json")))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValidationError) as exc:
            raise ModuleLifecycleError("invalid module package") from exc
        if "agent" not in manifest.runtimes:
            raise ModuleLifecycleError("package does not target Agent")
        if manifest.compatibility.protocol != self.protocol_version:
            raise ModuleLifecycleError("incompatible protocol")
        if not meets_minimum_version(__version__, manifest.compatibility.agent):
            raise ModuleLifecycleError("incompatible Agent runtime version")
        if self.architecture not in manifest.compatibility.architectures and "any" not in manifest.compatibility.architectures:
            raise ModuleLifecycleError("incompatible architecture")
        if set(manifest.permissions) - AGENT_ALLOWED_PERMISSIONS:
            raise ModuleLifecycleError("permission policy rejected package")
        previous = self.state(manifest.module_id).get("active_version")
        release = self.root / "releases" / manifest.module_id / manifest.version
        release.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=release.parent))
        try:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise ModuleLifecycleError("unsafe package path")
            archive.extractall(stage)
            self._health_check(stage, manifest)
            if release.exists(): shutil.rmtree(release)
            os.replace(stage, release)
            data_dir = self.root / "data" / manifest.module_id
            data_dir.mkdir(parents=True, exist_ok=True)
            self._activate(manifest, data_dir)
            self._save_state(manifest.module_id, {"active_version": manifest.version, "enabled": True, "permissions": list(manifest.permissions), "capabilities": list(manifest.capabilities.provides), "registrations": [item.model_dump() for item in manifest.registrations]})
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return ModuleRuntimeResult(manifest.module_id, manifest.version, "active", previous)

    def _health_check(self, release: Path, manifest: ModuleManifestV2) -> None:
        target = release / manifest.health_check.path
        if not target.is_file(): raise ModuleLifecycleError("module health check failed")
        if manifest.health_check.type == "json_file":
            try: json.loads(target.read_text())
            except (OSError, json.JSONDecodeError) as exc: raise ModuleLifecycleError("module health check failed") from exc

    def _activate(self, manifest: ModuleManifestV2, data_dir: Path) -> None:
        entrypoint = manifest.entrypoints.get("agent")
        if entrypoint is None:
            return
        handler = self.runtime_handlers.get(entrypoint)
        if handler is None:
            raise ModuleLifecycleError("unsupported Agent runtime entrypoint")
        try:
            handler(manifest, data_dir)
        except ModuleLifecycleError:
            raise
        except Exception as exc:
            raise ModuleLifecycleError("module activation failed") from exc

    def start_active(self) -> None:
        """Restore enabled trusted modules without letting one failure stop Agent boot."""
        state_dir = self.root / "state"
        if not state_dir.exists():
            return
        for state_path in state_dir.glob("*.json"):
            state = json.loads(state_path.read_text())
            if not state.get("enabled") or not state.get("active_version"):
                continue
            module_id = state_path.stem
            manifest_path = self.root / "releases" / module_id / state["active_version"] / "manifest.json"
            try:
                manifest = ModuleManifestV2.model_validate_json(manifest_path.read_text())
                self._activate(manifest, self.root / "data" / module_id)
            except (OSError, ValidationError, ModuleLifecycleError) as exc:
                state["runtime_error"] = str(exc)
                self._save_state(module_id, state)

    def disable(self, module_id: str) -> ModuleRuntimeResult:
        state = self.state(module_id)
        if not state.get("active_version"): raise ModuleLifecycleError("module is not installed")
        state["enabled"] = False; self._save_state(module_id, state)
        return ModuleRuntimeResult(module_id, state["active_version"], "disabled")

    def registrations(self) -> list[dict]:
        result = []
        state_dir = self.root / "state"
        if not state_dir.exists(): return result
        for path in state_dir.glob("*.json"):
            state = json.loads(path.read_text())
            if state.get("enabled"):
                result.extend(state.get("registrations", []))
        return result
