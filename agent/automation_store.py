"""Atomic persistent storage for approved declarative automations."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from three_mm_protocol.automation import AutomationDefinitionV1


class StoredAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    automation_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    revision_id: str = Field(min_length=1, max_length=64)
    definition: AutomationDefinitionV1


class AutomationStore:
    def __init__(self, data_dir: Path, runtime=None) -> None:
        self.path = data_dir / "automations.json"
        self.runtime = runtime

    def load(self) -> dict[str, StoredAutomation]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {key: StoredAutomation.model_validate(value) for key, value in raw.items()}
        except (OSError, ValueError, ValidationError) as exc:
            raise RuntimeError(f"Cannot load automation state from {self.path}") from exc

    def _save(self, items: dict[str, StoredAutomation]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({key: value.model_dump(mode="json") for key, value in items.items()}, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def apply(self, automation: StoredAutomation, *, device_id: str) -> dict:
        if automation.definition.execution != "local":
            raise ValueError("Agent accepts only local automations")
        targets = {automation.definition.trigger.device_id, *(action.device_id for action in automation.definition.actions)}
        if targets != {device_id}:
            raise ValueError("Automation targets a different device")
        items = self.load()
        current = items.get(automation.automation_id)
        if current and automation.revision < current.revision:
            raise ValueError("Automation revision is older than the active revision")
        items[automation.automation_id] = automation
        if self.runtime is not None:
            self.runtime.activate_automation(automation.automation_id, automation.definition)
        self._save(items)
        return {"automation_id": automation.automation_id, "revision": automation.revision, "active": True}

    def remove(self, automation_id: str, revision: int) -> dict:
        items = self.load()
        current = items.get(automation_id)
        if current and revision < current.revision:
            raise ValueError("Automation revision is older than the active revision")
        items.pop(automation_id, None)
        if self.runtime is not None:
            self.runtime.remove_automation(automation_id)
        self._save(items)
        return {"automation_id": automation_id, "revision": revision, "active": False}

    def activate_all(self, *, device_id: str) -> None:
        if self.runtime is None:
            return
        for automation in self.load().values():
            targets = {automation.definition.trigger.device_id, *(action.device_id for action in automation.definition.actions)}
            if targets != {device_id}:
                raise RuntimeError("Stored automation targets a different device")
            self.runtime.activate_automation(automation.automation_id, automation.definition)
