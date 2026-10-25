"""Root-owned, one-at-a-time Wi-Fi transaction with an external rollback deadline.

No SSID or credential is journaled. Uncommitted profiles never autoconnect.
The helper and timer share a POSIX lock; startup compensates an interrupted apply.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import re
import time

from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_capabilities import require_interface
from three_mm_provisioning.network_manager_mutation import NetworkManagerMutationBoundary
from three_mm_provisioning.setup_journal import atomic_json

TRANSACTION_DIR = Path("/var/lib/3mm-setup-helper")
IDENTIFIER = re.compile(r"[0-9a-f]{32}\Z")


class NetworkTransaction:
    def __init__(self, data_dir=TRANSACTION_DIR, boundary=None, validate_interface=require_interface):
        self.directory = Path(data_dir)
        self.path = self.directory / "pending.json"
        self.boundary = boundary or NetworkManagerMutationBoundary()
        self.validate_interface = validate_interface

    @contextmanager
    def locked(self):
        import fcntl
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.directory / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _load(self):
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 4096:
            raise NetworkAdapterError("Invalid network transaction")
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or set(value) != {"id", "interface", "previous", "old_owned", "staged", "deadline", "phase", "finalized", "owned"}
                or not IDENTIFIER.fullmatch(value["id"]) or value["phase"] not in {"applying", "verified", "committed", "rolled_back"}):
            raise NetworkAdapterError("Invalid network transaction")
        if not isinstance(value["owned"], dict) or len(value["owned"]) > 16:
            raise NetworkAdapterError("Invalid network ownership ledger")
        return value

    def recover(self):
        with self.locked():
            value = self._load()
            if value and value["phase"] not in {"committed", "rolled_back"}:
                self._rollback(value)
            elif value and value["phase"] == "committed":
                self._finish_commit(value)

    def handle(self, payload):
        identifier = payload.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise NetworkAdapterError("Invalid attempt")
        action = payload["action"]
        with self.locked():
            value = self._load()
            if value and value["phase"] in {"applying", "verified"} and time.time() >= value["deadline"]:
                self._rollback(value)
            if action == "wifi.apply":
                if value and value["id"] == identifier:
                    return {"ok": True, "phase": value["phase"]}
                if value and value["phase"] not in {"committed", "rolled_back"}:
                    raise NetworkAdapterError("Another network attempt is pending")
                interface = payload["interface"]
                self.validate_interface(interface)
                owned = dict(value["owned"]) if value else {}
                if interface not in owned and len(owned) >= 16:
                    raise NetworkAdapterError("Managed adapter budget reached")
                try:
                    previous = self.boundary.active_connection_uuid(interface)
                    if previous == "--":
                        previous = None
                except NetworkAdapterError:
                    previous = None
                value = {"id": identifier, "interface": interface, "previous": previous,
                         "old_owned": owned.get(interface), "owned": owned,
                         "staged": None, "deadline": time.time() + 120, "phase": "applying", "finalized": False}
                atomic_json(self.path, value)
                try:
                    self.boundary.schedule_setup_rollback(identifier)
                    self.boundary.connect_persistent_wifi(
                        interface=interface, connection_name=f"3mm-staged-{identifier}",
                        network_name=payload["network_name"], passphrase=payload["passphrase"], autoconnect=False)
                    value["staged"] = self.boundary.connection_uuid(f"3mm-staged-{identifier}")
                    if (not value["staged"] or self.boundary.active_connection_uuid(interface) != value["staged"]
                            or not self.boundary.has_local_address(interface) or time.time() >= value["deadline"]):
                        raise NetworkAdapterError("Local connectivity verification failed")
                    value["phase"] = "verified"
                    atomic_json(self.path, value)
                except Exception:
                    self._rollback(value)
                    raise NetworkAdapterError("Network apply failed") from None
            else:
                if value is None or value["id"] != identifier:
                    return {"ok": True, "phase": "missing"}
                if action == "wifi.commit" and value["phase"] == "verified":
                    self.validate_interface(value["interface"])
                    if (self.boundary.active_connection_uuid(value["interface"]) != value["staged"]
                            or not self.boundary.has_local_address(value["interface"])):
                        self._rollback(value)
                        raise NetworkAdapterError("Connection no longer verified")
                    self.boundary.rename_connection(value["staged"], "3mm-wifi")
                    if time.time() >= value["deadline"]:
                        self._rollback(value)
                        raise NetworkAdapterError("Network deadline exceeded")
                    # Commit intent is durable before enabling autoconnect. Startup
                    # finishes this idempotently; a pending timer observes this phase.
                    value["phase"] = "committed"
                    atomic_json(self.path, value)
                    self._finish_commit(value)
                elif action == "wifi.rollback" and value["phase"] not in {"committed", "rolled_back"}:
                    self._rollback(value)
                elif action == "wifi.status" and value["phase"] == "committed":
                    self._finish_commit(value)
            return {"ok": True, "phase": value["phase"]}

    def _finish_commit(self, value):
        if value["finalized"]:
            return
        self.boundary.set_autoconnect(value["staged"], True)
        value["owned"][value["interface"]] = value["staged"]
        old = value["old_owned"]
        if old and old != value["staged"]:
            try:
                self.boundary.delete_connection(old)
            except NetworkAdapterError:
                pass
        value["finalized"] = True
        atomic_json(self.path, value)

    def _rollback(self, value):
        staged = value["staged"] or self.boundary.connection_uuid(f"3mm-staged-{value['id']}")
        if staged and self.boundary.connection_uuid(staged):
            self.boundary.delete_connection(staged)
        if value["previous"]:
            self.boundary.restore_connection(value["previous"])
        value["phase"] = "rolled_back"
        atomic_json(self.path, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", required=True)
    arguments = parser.parse_args()
    NetworkTransaction().handle({"action": "wifi.rollback", "id": arguments.rollback})


if __name__ == "__main__":
    main()
