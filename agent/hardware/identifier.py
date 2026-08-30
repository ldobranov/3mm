"""Generic identifier reader contract and deterministic test adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from three_mm_protocol import IdentifierScanPayloadV1


@dataclass(slots=True)
class MockIdentifierAdapter:
    """Loopback-driven mock reader with a restart-safe sequence counter."""

    state_path: Path
    reader_id: str = "reader.mock.1"

    def _sequence(self) -> int:
        if not self.state_path.exists():
            return 0
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            sequence = value.get("sequence")
        except (OSError, ValueError):
            return 0
        return sequence if isinstance(sequence, int) and sequence >= 0 else 0

    def _save_sequence(self, sequence: int) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"sequence": sequence}, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_path)
        os.chmod(self.state_path, 0o600)

    def scan(
        self,
        opaque_identifier: str,
        *,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> dict[str, object]:
        sequence = self._sequence() + 1
        payload = IdentifierScanPayloadV1(
            opaque_identifier=opaque_identifier,
            reader_id=self.reader_id,
            adapter_kind="mock",
            sequence=sequence,
            scan_metadata=metadata or {},
        )
        self._save_sequence(sequence)
        return {
            "event_type": "identifier.scan.v1",
            "payload": payload.model_dump(mode="json"),
        }
