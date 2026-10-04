"""Reference HTTP adapter and rollback-compatible outbox codec.

Only this boundary knows device paths, headers, HTTP acknowledgement/status
codes and long-poll parameters. The logical port accepts protocol objects.
"""

import requests
import time
import threading
import subprocess

from three_mm_protocol import (
    AgentCommand,
    AgentCommandResult,
    AgentHeartbeat,
    AgentInventory,
    AgentReportedState,
    CapabilityStateReportV1,
    CapabilityProviderReportV1,
    DeviceDesiredState,
    DeviceEventV1,
    DeviceInventoryV2,
    CoreNodeProtocolV1,
    DeviceRuntimeFeaturesSnapshotV1,
)
from three_mm_protocol.fleet_pairing import NodeEnrollmentResponse
from three_mm_protocol.node_updates import NodeUpdateOperation
from three_mm_protocol.transport import DeviceTransportError
from three_mm_protocol.device_platform import challenge, DevicePlatformSnapshotV1
from three_mm_protocol.capability_availability import CapabilityAvailabilityReportV1


class HttpTransportError(DeviceTransportError, requests.RequestException):
    pass


class HttpRejected(DeviceTransportError, requests.HTTPError):
    pass


def legacy_outbox_record(report):
    """Keep existing disk records readable by pre-C10 rollback releases."""
    if isinstance(report, AgentHeartbeat):
        suffix = "heartbeat"
    elif isinstance(report, (AgentInventory, DeviceInventoryV2)):
        suffix = "inventory"
    elif isinstance(report, AgentCommandResult):
        suffix = f"commands/{report.command_id}/result"
    elif isinstance(report, AgentReportedState):
        suffix = "reported-state"
    elif isinstance(report, CapabilityStateReportV1):
        suffix = f"capabilities/{report.capability_id}/state"
    elif isinstance(report, DeviceEventV1):
        suffix = "events"
    elif isinstance(report, NodeUpdateOperation):
        suffix = f"node-updates/{report.operation_id}/report"
    else:
        raise ValueError("Report is not supported by the legacy outbox")
    return suffix, report.model_dump(mode="json")


def legacy_outbox_message(suffix, payload):
    """Validate legacy persisted evidence before handing it to any transport."""
    if suffix == "heartbeat":
        model = AgentHeartbeat
    elif suffix == "inventory":
        model = (
            DeviceInventoryV2 if payload.get("schema_version") == 2 else AgentInventory
        )
    elif suffix == "events":
        model = DeviceEventV1
    elif suffix == "reported-state":
        model = AgentReportedState
    elif suffix == f"commands/{payload.get('command_id')}/result":
        model = AgentCommandResult
    elif suffix == f"capabilities/{payload.get('capability_id')}/state":
        model = CapabilityStateReportV1
    elif suffix == f"node-updates/{payload.get('operation_id')}/report":
        model = NodeUpdateOperation
    else:
        raise DeviceTransportError(
            "Stored message identity/type mismatch; pending evidence retained"
        )
    try:
        return model.model_validate(payload)
    except ValueError as exc:
        raise DeviceTransportError(
            "Stored message cannot satisfy the Node contract; pending evidence retained"
        ) from exc


class HttpDeviceTransport:
    def __init__(self, core_url, credential, *, authority_store=None):
        self.origin = core_url.rstrip("/")
        self.credential = credential
        self.device_id = credential.device_id
        self.url = f"{self.origin}/api/v1/devices/{self.device_id}"
        self.authority_store = authority_store
        self._authority_mode = None
        self._verified_at = 0
        self._authority_lock = threading.RLock()

    def _ensure_authority(self):
        if self.authority_store is None:
            return False  # Existing embedding adapters retain their old contract.
        with self._authority_lock:
            try:
                binding = self.authority_store.check_current()
                if self._authority_mode == "legacy" and binding is None:
                    return False
                if (
                    self._authority_mode == "signed"
                    and time.monotonic() - self._verified_at < 30
                ):
                    return True
                request = challenge(
                    self.device_id, self.credential.credential_id, "identity"
                )
                # No secret is sent until the endpoint proves the pinned key.
                response = requests.post(
                    self.origin + "/api/v1/pairing/authority-proof",
                    json=request.model_dump(mode="json"),
                    headers={},
                    timeout=10,
                    allow_redirects=False,
                )
                if response.status_code in {404, 405} and binding is None:
                    self._authority_mode = "legacy"
                    return False
                if response.status_code != 200:
                    raise ValueError(
                        "Authority proof unavailable; unsigned fallback refused"
                    )
                self.authority_store.verify(response.json(), request, bootstrap=True)
                self._authority_mode, self._verified_at = "signed", time.monotonic()
                return True
            except (
                ValueError,
                OSError,
                subprocess.SubprocessError,
                requests.RequestException,
            ) as exc:
                raise HttpRejected(
                    "Installation authority could not be verified"
                ) from exc

    def _exchange(self, operation, *, command_id=None, timeout_seconds=0):
        request = challenge(
            self.device_id,
            self.credential.credential_id,
            operation,
            command_id=command_id,
        )
        response = self._request(
            "post",
            "authority-exchange",
            payload=request.model_dump(mode="json"),
            params={"wait_seconds": timeout_seconds},
            timeout=(
                2 if operation == "execution_permit" else max(10, timeout_seconds + 5)
            ),
        )
        try:
            return self.authority_store.verify(response.json(), request)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            raise HttpRejected(
                "Management response is not from the pinned installation"
            ) from exc

    @property
    def headers(self):
        return {
            "Authorization": f"Device {self.credential.credential_id}:{self.credential.credential_secret}"
        }

    def _request(
        self,
        method,
        suffix,
        *,
        payload=None,
        timeout=10,
        params=None,
        legacy_missing=False,
        enrollment=False,
    ):
        if not enrollment:
            self._ensure_authority()
        url = (
            self.origin + "/api/v1/pairing/enroll"
            if enrollment
            else self.url + "/" + suffix
        )
        kwargs = dict(
            headers={} if enrollment else self.headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if payload is not None:
            kwargs["json"] = payload
        if params is not None:
            kwargs["params"] = params
        try:
            response = getattr(requests, method)(url, **kwargs)
            code = getattr(response, "status_code", 200)
            if legacy_missing and code in {404, 405}:
                return None
            if 300 <= code < 400:
                raise HttpRejected("Core redirect is not a message acknowledgement")
            response.raise_for_status()
            return response
        except DeviceTransportError:
            raise
        except requests.HTTPError as exc:
            raise HttpRejected("Core rejected the device operation") from exc
        except requests.RequestException as exc:
            raise HttpTransportError(
                "Device transport unavailable; acknowledgement unconfirmed"
            ) from exc

    def enroll(self, request):
        if (
            request.device_id != self.device_id
            or request.credential_id != self.credential.credential_id
        ):
            raise ValueError("Enrollment identity mismatch")
        response = NodeEnrollmentResponse.model_validate(
            self._request(
                "post", "", payload=request.model_dump(mode="json"), enrollment=True
            ).json()
        )
        if (
            response.device_id != request.device_id
            or response.credential_id != request.credential_id
        ):
            raise HttpRejected("Enrollment response identity mismatch")
        return response

    def publish(self, report):
        if report.device_id != self.device_id:
            raise ValueError("Report device identity mismatch")
        if isinstance(report, CapabilityAvailabilityReportV1):
            # Ephemeral health is not durable execution evidence and must never
            # be replayed through the outbox with a fresh receipt timestamp.
            self._request("post", "capability-availability", payload=report.model_dump(mode="json"))
        elif isinstance(report, CapabilityProviderReportV1):
            self._request(
                "put",
                f"capability-providers/{report.provider_type}/{report.provider_id}",
                payload=report.model_dump(mode="json"),
            )
        else:
            suffix, payload = legacy_outbox_record(report)
            self._request("post", suffix, payload=payload)

    def receive_command(self, *, timeout_seconds=0):
        if not 0 <= timeout_seconds <= 20:
            raise ValueError("Command receive timeout must be bounded to 0..20 seconds")
        if self._ensure_authority():
            payload = self._exchange("command", timeout_seconds=timeout_seconds)
            return (
                AgentCommand.model_validate(payload["command"])
                if payload["command"] is not None
                else None
            )
        response = self._request(
            "get",
            "commands/next",
            params={"wait_seconds": timeout_seconds},
            timeout=max(10.0, timeout_seconds + 5.0),
        )
        if response.status_code == 204:
            return None
        return AgentCommand.model_validate(response.json())

    def desired_state(self):
        if self._ensure_authority():
            return DeviceDesiredState.model_validate(self._exchange("desired_state"))
        return DeviceDesiredState.model_validate(
            self._request("get", "desired-state").json()
        )

    def protocol(self):
        response = self._request("get", "protocol", legacy_missing=True)
        return (
            CoreNodeProtocolV1.model_validate(response.json())
            if response is not None
            else None
        )

    def report_features(self, report):
        return DeviceRuntimeFeaturesSnapshotV1.model_validate(
            self._request(
                "put", "runtime-features", payload=report.model_dump(mode="json")
            ).json()
        )

    def authorize_execution(self, command_id):
        if self._ensure_authority():
            return self._exchange("execution_permit", command_id=command_id)
        return self._request(
            "post", f"commands/{command_id}/authorize-execution", timeout=2
        ).json()

    def platform(self):
        if not self._ensure_authority():
            return None
        return DevicePlatformSnapshotV1.model_validate(self._exchange("platform"))

    def report_lifecycle(self, report):
        if report.device_id != self.device_id:
            raise ValueError("Lifecycle device identity mismatch")
        return DevicePlatformSnapshotV1.model_validate(
            self._request(
                "put", "lifecycle", payload=report.model_dump(mode="json")
            ).json()
        )
