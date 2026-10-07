"""Transactional, data-preserving Agent module lifecycle."""
from __future__ import annotations
import hashlib, io, json, os, shutil, tempfile, zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
from pydantic import ValidationError
from three_mm_protocol import (
    EXTENSION_API_VERSION,
    ModuleManifestV2,
    module_compatibility_issues,
)
from three_mm_protocol.capability_contracts import CapabilityContractError, validate_value
from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1, declaration_digest
from datetime import UTC, datetime
from agent import __version__

AGENT_ALLOWED_PERMISSIONS = {"data.read", "data.write", "events.publish", "network.outbound", "process.spawn", "hardware.inventory", "hardware.gpio"}

class ModuleLifecycleError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class ModuleRuntimeResult:
    module_id: str
    version: str
    status: str
    previous_version: str | None = None

class CapabilityService(Protocol):
    def invoke(self, action: str, arguments: dict) -> dict: ...

RuntimeHandler = Callable[[ModuleManifestV2, Path], dict[str, CapabilityService] | None]

class AgentModuleRuntime:
    def __init__(
        self,
        data_dir: Path,
        *,
        architecture: str,
        protocol_version: str = "1.0",
        extension_api_version: str = EXTENSION_API_VERSION,
        runtime_handlers: dict[str, RuntimeHandler] | None = None,
    ):
        self.root = data_dir / "modules"
        self.architecture = architecture
        self.protocol_version = protocol_version
        self.extension_api_version = extension_api_version
        self.runtime_handlers = dict(runtime_handlers or {})
        self._services: dict[str, CapabilityService] = {}
        self._contracts = {}
        self._owners = {}

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
        compatibility_issues = module_compatibility_issues(
            manifest,
            runtime="agent",
            runtime_version=__version__,
            architecture=self.architecture,
            protocol_version=self.protocol_version,
            extension_api_version=self.extension_api_version,
            require_runtime=True,
        )
        if "runtime" in compatibility_issues:
            raise ModuleLifecycleError("package does not target Agent")
        if "protocol" in compatibility_issues:
            raise ModuleLifecycleError("incompatible protocol")
        if "extension_api" in compatibility_issues:
            raise ModuleLifecycleError("incompatible Extension API")
        if {"runtime_version", "runtime_version_invalid"} & set(compatibility_issues):
            raise ModuleLifecycleError("incompatible Agent runtime version")
        if "architecture" in compatibility_issues:
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
            services = handler(manifest, data_dir) or {}
        except ModuleLifecycleError:
            raise
        except Exception as exc:
            raise ModuleLifecycleError("module activation failed") from exc
        declared = {item.registration_id for item in manifest.registrations if item.kind in {"capability", "service"}}
        if not set(services).issubset(declared):
            raise ModuleLifecycleError("runtime exposed an undeclared capability")
        withdrawn = {capability_id for capability_id, owner in self._owners.items()
                     if owner == manifest.module_id and capability_id not in services}
        replaced = {
            id(self._services[capability_id]): self._services[capability_id]
            for capability_id in set(services) | withdrawn
            if capability_id in self._services
        }
        for previous_service in replaced.values():
            if hasattr(previous_service, "close"):
                previous_service.close()
        for capability_id in withdrawn:
            self._services.pop(capability_id, None)
            self._contracts.pop(capability_id, None)
            self._owners.pop(capability_id, None)
        self._services.update(services)
        registrations = {item.registration_id: item for item in manifest.registrations}
        for capability_id in services:
            self._contracts[capability_id] = registrations[capability_id].contract
            self._owners[capability_id] = manifest.module_id

    def validate_invocation(self, payload):
        if payload.get('capability_id') not in self._services:
            raise CapabilityContractError('Capability is unavailable')
        contract = self._contracts.get(payload['capability_id'])
        if contract is None:
            if payload.get('contract_version') is not None or payload.get('contract_digest') is not None:
                raise CapabilityContractError('Versioned capability contract is unavailable')
            return None
        return contract.invocation(payload, require_digest=True)

    def invoke(self, capability_id: str, action: str, arguments: dict, *, contract_version=None, contract_digest=None) -> dict:
        service = self._services.get(capability_id)
        if service is None:
            raise ModuleLifecycleError("capability is unavailable")
        definition = self.validate_invocation({'capability_id': capability_id, 'action': action,
            'arguments': arguments, 'contract_version': contract_version, 'contract_digest': contract_digest})
        try:
            result = service.invoke(action, arguments)
            if definition is not None:
                validate_value(result, definition.result_schema)
            return result
        except ModuleLifecycleError:
            raise
        except Exception as exc:
            raise ModuleLifecycleError("capability invocation failed") from exc

    def capability_states(self) -> dict[str, dict]:
        """Return current state from active services that expose a read boundary."""
        result: dict[str, dict] = {}
        for capability_id, service in self._services.items():
            try:
                if hasattr(service, "state_for"):
                    state = service.state_for(capability_id)
                elif hasattr(service, "state"):
                    state = service.state()
                else:
                    continue
            except Exception as exc:
                raise ModuleLifecycleError(
                    f"capability state read failed for {capability_id}"
                ) from exc
            if isinstance(state, dict) and state:
                contract = self._contracts.get(capability_id)
                if contract is not None and contract.state_schema is not None:
                    try:
                        validate_value(state, contract.state_schema)
                    except CapabilityContractError as exc:
                        raise ModuleLifecycleError('Capability state violates its contract') from exc
                result[capability_id] = state
        return result

    def capability_healthy(self, capability_id):
        """Non-mutating runtime probe; not electrical/mechanical confirmation."""
        service = self._services.get(capability_id)
        if service is None:
            return False
        try:
            if hasattr(service, "is_available") and service.is_available() is not True:
                return False
            state = (service.state_for(capability_id) if hasattr(service, "state_for")
                     else service.state() if hasattr(service, "state") else None)
            contract = self._contracts.get(capability_id)
            if contract is not None and contract.state_schema is not None:
                validate_value(state, contract.state_schema)
            return True
        except Exception:
            return False

    def availability_reports(self, device_id):
        observed = datetime.now(UTC)
        for path in (self.root / "state").glob("*.json"):
            state = json.loads(path.read_text())
            if not state.get("enabled") or not state.get("active_version"):
                continue
            declarations = [{"capability_id": item["registration_id"], "metadata": item.get("metadata", {}),
                             **({"contract": item["contract"]} if item.get("contract") is not None else {})}
                            for item in state.get("registrations", []) if item.get("kind") == "capability"]
            if not declarations:
                continue
            yield CapabilityAvailabilityReportV1(
                device_id=device_id, provider_type="agent_module", provider_id=path.stem,
                provider_version=state["active_version"], observed_at=observed,
                declaration_digest=declaration_digest("agent_module", path.stem, state["active_version"], declarations),
                capabilities=tuple({"capability_id": item["capability_id"],
                                    "healthy": self.capability_healthy(item["capability_id"])} for item in declarations))

    def activate_automation(self, automation_id: str, definition) -> None:
        trigger_service = self._services.get(definition.trigger.capability_id)
        if trigger_service is None or not hasattr(trigger_service, "subscribe"):
            raise ModuleLifecycleError("trigger capability does not support automation events")

        def execute_actions() -> None:
            for action in definition.actions:
                self.invoke(action.capability_id, action.action, action.arguments)

        trigger_service.subscribe(automation_id, definition.trigger.event, definition.trigger.conditions, execute_actions)

    def remove_automation(self, automation_id: str) -> None:
        for capability_service in self._services.values():
            if hasattr(capability_service, "unsubscribe"):
                capability_service.unsubscribe(automation_id)

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
        for registration in state.get("registrations", []):
            service = self._services.pop(registration.get("registration_id"), None)
            self._contracts.pop(registration.get("registration_id"), None)
            self._owners.pop(registration.get("registration_id"), None)
            if service is not None and hasattr(service, "close"):
                service.close()
        return ModuleRuntimeResult(module_id, state["active_version"], "disabled")

    def close(self) -> None:
        """Release active services without changing their persistent enabled state."""
        services = {id(service): service for service in self._services.values()}
        self._services.clear()
        self._contracts.clear()
        self._owners.clear()
        for service in services.values():
            if hasattr(service, "close"):
                service.close()

    def registrations(self) -> list[dict]:
        result = []
        state_dir = self.root / "state"
        if not state_dir.exists(): return result
        for path in state_dir.glob("*.json"):
            state = json.loads(path.read_text())
            if state.get("enabled"):
                result.extend(state.get("registrations", []))
        return result

    def enabled_hardware_modules(self, permission: str) -> list[str]:
        """Fail closed when persistent module state cannot be inspected."""
        result = []
        for path in (self.root / "state").glob("*.json"):
            state = json.loads(path.read_text())
            if state.get("enabled") and permission in state.get("permissions", []):
                result.append(path.stem)
        return sorted(result)
