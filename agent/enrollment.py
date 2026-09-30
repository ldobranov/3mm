"""Restart-safe background enrollment; no shared password or server-side secret delivery."""
import hashlib
import os
from pathlib import Path
import random
import secrets
import threading
from urllib.parse import urlsplit, urlunsplit

import requests
from pydantic import BaseModel, ConfigDict, Field

from agent.core_client import DeviceCredential, DeviceCredentialStore
from agent.hub_connection import normalize_hub_endpoint
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest, NodeEnrollmentResponse


class EnrollmentState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_token: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    credential: DeviceCredential


class NodeEnrollmentWorker:
    def __init__(self, data_dir: Path, endpoint: str, device_id: str,
                 display_name: str, on_approved, on_status, *, transport=requests):
        self.path = data_dir / "hub-enrollment.json"
        self.store = DeviceCredentialStore(data_dir)
        self.endpoint = normalize_hub_endpoint(endpoint)
        self.device_id = device_id
        self.display_name = display_name[:100]
        self.on_approved, self.on_status = on_approved, on_status
        self.transport = transport
        self._stop = threading.Event()
        self._thread = None

    def _state(self):
        if self.path.exists():
            state = EnrollmentState.model_validate_json(self.path.read_text(encoding="utf-8"))
            if state.credential.device_id != self.device_id or state.credential.hub_endpoint != self.endpoint:
                raise ValueError("Enrollment reassignment requires explicit recovery")
            return state
        state = EnrollmentState(request_token=secrets.token_hex(32), credential=DeviceCredential(
            device_id=self.device_id, credential_id="cred_" + secrets.token_hex(16),
            credential_secret=secrets.token_urlsafe(32), hub_endpoint=self.endpoint,
        ))
        self._save(state)
        return state

    def _save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(state.model_dump_json() + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.path)

    def _api_endpoint(self):
        # Full installations expose a static web port and a separate Core port.
        # Read only a same-host port hint; never follow a backend_url to another host.
        parsed = urlsplit(self.endpoint)
        if parsed.scheme == "http" and parsed.port in (None, 80, 8080) and not parsed.path:
            response = self.transport.get(self.endpoint + "/runtime-config.json", timeout=5, allow_redirects=False)
            if response.status_code == 200:
                try:
                    config = response.json()
                except ValueError:
                    config = {}
                port = config.get("backend_port") if isinstance(config, dict) else None
                if type(port) is int and 1 <= port <= 65535:
                    host = parsed.hostname
                    if ":" in host:
                        host = f"[{host}]"
                    return urlunsplit((parsed.scheme, f"{host}:{port}", "", "", ""))
        return self.endpoint

    def tick(self):
        state = self._state()  # Persist BEFORE sending, including the first attempt.
        api = state.credential.api_endpoint
        if api is None:
            api = self._api_endpoint()
            state = state.model_copy(update={"credential": state.credential.model_copy(update={"api_endpoint": api})})
            self._save(state)
        if self._stop.is_set():
            return True
        payload = NodeEnrollmentRequest(
            device_id=self.device_id, display_name=self.display_name,
            request_token=state.request_token, credential_id=state.credential.credential_id,
            credential_secret_hash=hashlib.sha256(state.credential.credential_secret.encode()).hexdigest(),
        )
        response = self.transport.post(api + "/api/v1/pairing/enroll",
                                       json=payload.model_dump(), timeout=5, allow_redirects=False)
        if response.status_code == 409:
            self.on_status("enrollment_conflict")
            return True
        if response.status_code in (404, 405):
            self.on_status("enrollment_unavailable")
            return False
        if response.status_code != 200:
            raise requests.RequestException("Enrollment transport unavailable")
        result = NodeEnrollmentResponse.model_validate(response.json())
        if result.device_id != self.device_id or result.credential_id != state.credential.credential_id:
            raise ValueError("Enrollment response identity mismatch")
        if self._stop.is_set():
            return True
        if result.status == "approved":
            credential = state.credential.model_copy(update={"api_endpoint": api})
            self.store.save(credential)
            if self._stop.is_set():
                return True
            self.on_approved(credential)
            self.on_status("credential_available")
            return True
        self.on_status(result.status)
        return result.status in {"expired", "rejected", "revoked"}

    def start(self):
        self._thread = threading.Thread(target=self._run, name="3mm-enrollment", daemon=True)
        self._thread.start()

    def _run(self):
        delay = 5
        while not self._stop.is_set():
            try:
                if self.tick():
                    return
            except (requests.RequestException, OSError):
                self.on_status("hub_unavailable")
            except ValueError:
                self.on_status("enrollment_conflict")
                return
            if self._stop.wait(delay + random.uniform(0, 1)):
                return
            delay = min(delay * 2, 30)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=12)
