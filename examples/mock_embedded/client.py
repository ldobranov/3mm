"""A separate runtime using only shared contracts and the existing Core HTTP API.

The output is SQLite-backed simulation, not GPIO. A mock action and its receipt
commit together; this transaction must NOT be reused for real physical effects.
"""

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import requests

from three_mm_protocol import (
    AgentCommand,
    AgentCommandResult,
    AgentHeartbeat,
    AgentReportedState,
    CapabilityProviderReportV1,
    CapabilityProviderSnapshotV1,
    CapabilityStateReportV1,
    DeviceDesiredState,
    DeviceEventV1,
    DeviceInventoryV2,
    CoreNodeProtocolV1,
    DeviceRuntimeFeaturesReportV1,
    DeviceRuntimeFeaturesSnapshotV1,
)
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES
from three_mm_protocol.fleet_pairing import (
    NodeEnrollmentRequest,
    NodeEnrollmentResponse,
)

CAPABILITY = "gpio.digital.control"
PROVIDER = "conerax-embedded-test"
CHANNEL = "gpio.output.1"
VERSION = "0.2.0"


class ProtocolRejected(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Core rejected the request (HTTP {status_code})")


class MockEmbeddedClient:
    """Single foreground client with durable identity, receipts and bounded outbox."""

    def __init__(
        self,
        core_url: str,
        data_dir: Path,
        *,
        display_name="Mock embedded",
        transport=None,
    ):
        parsed = urlsplit(core_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("Use an explicit Core API HTTP(S) origin")
        self.core_url = core_url.rstrip("/")
        if not 1 <= len(display_name) <= 100:
            raise ValueError("Device name must be 1-100 characters")
        self.display_name = display_name
        self.transport = transport or requests.Session()
        if isinstance(self.transport, requests.Session):
            self.transport.trust_env = False
        self.started = time.monotonic()
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = data_dir / "node.sqlite3"
        if path.is_symlink():
            raise ValueError("Node state cannot be a symbolic link")
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if os.name != "nt":
            path.chmod(0o600)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts (
                key TEXT PRIMARY KEY, command_id TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL, result TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE,
                path TEXT NOT NULL, payload TEXT NOT NULL
            );
        """
        )
        authority = self._get("authority")
        if authority is not None and authority != self.core_url:
            self.close()
            raise ValueError("Persisted identity is bound to a different Core")
        with self.db:
            self._set("authority", self.core_url)
            if self._get("identity") is None:
                self._set(
                    "identity",
                    {
                        "device_id": f"dev_{uuid4().hex}",
                        "credential_id": f"cred_{uuid4().hex}",
                        "secret": secrets.token_hex(32),
                        "request_token": secrets.token_hex(32),
                    },
                )
        self.identity = self._get("identity")
        self.device_id = self.identity["device_id"]

    def close(self):
        self.db.close()
        if isinstance(self.transport, requests.Session):
            self.transport.close()

    def _get(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, key, value):
        self.db.execute(
            "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, allow_nan=False)),
        )

    def _request(self, method, path, payload=None, *, authenticated=True, timeout=10):
        headers = (
            {
                "Authorization": f"Device {self.identity['credential_id']}:{self.identity['secret']}"
            }
            if authenticated
            else {}
        )
        return self.transport.request(
            method,
            self.core_url + path,
            headers=headers,
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )

    @staticmethod
    def _body(response):
        if not 200 <= response.status_code < 300:
            raise ProtocolRejected(response.status_code)
        return response.json()

    @property
    def prefix(self):
        return f"/api/v1/devices/{self.device_id}"

    @property
    def output(self):
        return self._get("output", False)

    @property
    def executions(self):
        return self._get("executions", 0)

    @property
    def pending_count(self):
        return self.db.execute("SELECT count(*) FROM outbox").fetchone()[0]

    def enroll(self):
        request = NodeEnrollmentRequest(
            device_id=self.device_id,
            display_name=self.display_name,
            request_token=self.identity["request_token"],
            credential_id=self.identity["credential_id"],
            credential_secret_hash=hashlib.sha256(
                self.identity["secret"].encode()
            ).hexdigest(),
        )
        result = NodeEnrollmentResponse.model_validate(
            self._body(
                self._request(
                    "POST",
                    "/api/v1/pairing/enroll",
                    request.model_dump(mode="json"),
                    authenticated=False,
                )
            )
        )
        if (
            result.device_id != self.device_id
            or result.credential_id != self.identity["credential_id"]
        ):
            raise ValueError("Enrollment acknowledgement identity mismatch")
        return result.status

    def negotiate(self):
        protocol = CoreNodeProtocolV1.model_validate(
            self._body(self._request("GET", self.prefix + "/protocol"))
        )
        if (
            protocol.device_id != self.device_id
            or 2 not in protocol.inventory_schema_versions
            or 1 not in protocol.runtime_feature_schema_versions
            or 2 not in protocol.capability_registry_versions
            or 1 not in protocol.capability_provider_report_versions
        ):
            raise ValueError("Core does not support this runtime's contracts")
        report = DeviceRuntimeFeaturesReportV1(
            device_id=self.device_id,
            runtime_name=PROVIDER,
            runtime_version=VERSION,
            features=tuple(
                sorted(MANDATORY_NODE_FEATURES | {"application_execution_permits"})
            ),
            command_types=("capability.invoke", "application.capability.invoke"),
            expected_revision=protocol.runtime_features_revision,
        )
        snapshot = DeviceRuntimeFeaturesSnapshotV1.model_validate(
            self._body(
                self._request(
                    "PUT",
                    self.prefix + "/runtime-features",
                    report.model_dump(mode="json"),
                )
            )
        )
        if (
            snapshot.device_id != self.device_id
            or snapshot.source != "advertised"
            or snapshot.revision
            not in {
                protocol.runtime_features_revision,
                protocol.runtime_features_revision + 1,
            }
            or snapshot.declaration is None
            or snapshot.declaration.model_dump(mode="json")
            != report.model_dump(mode="json", exclude={"expected_revision"})
        ):
            raise ValueError("Runtime feature acknowledgement mismatch")

    def publish_inventory(self):
        inventory = DeviceInventoryV2(
            schema_version=2,
            device_id=self.device_id,
            collected_at=datetime.now(UTC),
            platform={
                "family": "embedded",
                "system": "mock-embedded",
                "model": "Reference simulation",
            },
            runtime={"name": PROVIDER, "version": VERSION},
            resources={"memory_total_bytes": 409600, "flash_total_bytes": 4194304},
            capabilities=(CAPABILITY,),
        )
        self._body(
            self._request(
                "POST", self.prefix + "/inventory", inventory.model_dump(mode="json")
            )
        )

    def heartbeat(self):
        report = AgentHeartbeat(
            device_id=self.device_id,
            sent_at=datetime.now(UTC),
            uptime_seconds=max(0, time.monotonic() - self.started),
        )
        self._body(
            self._request(
                "POST", self.prefix + "/heartbeat", report.model_dump(mode="json")
            )
        )

    def register_capability(self):
        path = self.prefix + f"/capability-providers/embedded_firmware/{PROVIDER}"
        previous = self._request("GET", path)
        revision = 0
        if previous.status_code != 404:
            current = CapabilityProviderSnapshotV1.model_validate(self._body(previous))
            self._check_provider(current)
            revision = current.revision
        report = CapabilityProviderReportV1(
            schema_version=1,
            device_id=self.device_id,
            provider_type="embedded_firmware",
            provider_id=PROVIDER,
            provider_version=VERSION,
            expected_revision=revision,
            capabilities=(
                {
                    "capability_id": CAPABILITY,
                    "metadata": {
                        "automation_channels": CHANNEL,
                        "automation_actions": "set_output",
                        "automation_required_fields": "channel,value",
                        "automation_value_type": "boolean",
                    },
                },
            ),
        )
        result = CapabilityProviderSnapshotV1.model_validate(
            self._body(self._request("PUT", path, report.model_dump(mode="json")))
        )
        self._check_provider(result)
        with self.db:
            self._set("enabled", result.enabled)
        return result

    def _check_provider(self, snapshot):
        if (snapshot.device_id, snapshot.provider_type, snapshot.provider_id) != (
            self.device_id,
            "embedded_firmware",
            PROVIDER,
        ):
            raise ValueError("Provider acknowledgement identity mismatch")

    def _enqueue(self, key, path, payload):
        serialized = json.dumps(payload, sort_keys=True, allow_nan=False)
        if len(serialized.encode()) > 65536:
            raise ValueError("Outbox payload limit reached")
        exists = self.db.execute("SELECT id FROM outbox WHERE key=?", (key,)).fetchone()
        if exists is None and self.pending_count >= 128:
            raise ValueError("Outbox capacity reached; refusing to lose pending data")
        self.db.execute(
            "INSERT INTO outbox(key,path,payload) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
            (key, path, serialized),
        )

    def flush(self):
        while (
            row := self.db.execute(
                "SELECT * FROM outbox ORDER BY id LIMIT 1"
            ).fetchone()
        ) is not None:
            # Delete only after acknowledgement; lost replies leave durable retries.
            self._body(
                self._request(
                    "POST", self.prefix + row["path"], json.loads(row["payload"])
                )
            )
            with self.db:
                self.db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))

    def _queue_state(self, now):
        state = CapabilityStateReportV1(
            device_id=self.device_id,
            capability_id=CAPABILITY,
            values={CHANNEL: self.output},
            observed_at=now,
        )
        self._enqueue(
            "capability-state",
            f"/capabilities/{CAPABILITY}/state",
            state.model_dump(mode="json"),
        )

    def reconcile(self):
        desired = DeviceDesiredState.model_validate(
            self._body(self._request("GET", self.prefix + "/desired-state"))
        )
        if desired.device_id != self.device_id:
            raise ValueError("Desired state identity mismatch")
        if desired.revision != self._get("desired_revision", -1):
            report = AgentReportedState(
                device_id=self.device_id,
                desired_revision=desired.revision,
                applied_revision=desired.revision,
                state=desired.state,
                reported_at=datetime.now(UTC),
            )
            with self.db:
                self._set("desired_revision", desired.revision)
                self._set("desired_state", desired.state)
                self._enqueue(
                    "reported-state", "/reported-state", report.model_dump(mode="json")
                )

    def execute(self, command: AgentCommand):
        """Atomic simulation; a durable intent precedes any one-time permit."""
        if command.device_id != self.device_id:
            raise ValueError("Command identity mismatch")
        if (
            command.expires_at.utcoffset() is None
            or command.created_at.utcoffset() is None
        ):
            raise ValueError("Command timestamps require timezones")
        canonical = command.model_dump(mode="json", exclude={"command_id"})
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()
        ).hexdigest()
        # Writer lock also protects against two mock clients using the same state.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute(
                "SELECT * FROM receipts WHERE key=? OR command_id=?",
                (command.idempotency_key, command.command_id),
            ).fetchone()
            if old is not None:
                if old["digest"] != digest or old["command_id"] != command.command_id:
                    raise ValueError("Command idempotency key has different content")
                result = AgentCommandResult.model_validate_json(old["result"])
            else:
                if (
                    self.db.execute("SELECT count(*) FROM receipts").fetchone()[0]
                    >= 1024
                ):
                    raise ValueError(
                        "Receipt capacity reached; no unsafe journal eviction"
                    )
                now = datetime.now(UTC)
                error = None
                arguments = command.payload.get("arguments", {})
                if command.expires_at <= now:
                    error = "Command expired; no mock action was executed"
                elif (
                    command.command_type == "application.capability.invoke"
                    and (command.expires_at - command.created_at).total_seconds() > 10
                ):
                    error = "Application execution requires a deadline of at most ten seconds"
                elif self._get("enabled", False) is not True:
                    error = "Provider is not enabled"
                elif (
                    command.command_type
                    not in {"capability.invoke", "application.capability.invoke"}
                    or command.payload.get("capability_id") != CAPABILITY
                    or command.payload.get("action") != "set_output"
                ):
                    error = "Unsupported command or capability action"
                elif (
                    not isinstance(arguments, dict)
                    or set(arguments) != {"channel", "value"}
                    or arguments["channel"] != CHANNEL
                    or type(arguments["value"]) is not bool
                ):
                    error = "Invalid mock output arguments"
                if (
                    error is None
                    and command.command_type == "application.capability.invoke"
                ):
                    # Persist uncertainty BEFORE requesting the single-use permit.
                    # A crash leaves this receipt, never permission to try again.
                    pending = AgentCommandResult(
                        command_id=command.command_id,
                        device_id=self.device_id,
                        status="failed",
                        completed_at=now,
                        output={"execution_state": "unknown", "mock": True},
                        error="Previous execution intent is unresolved; automatic retry refused",
                    )
                    self.db.execute(
                        "INSERT INTO receipts VALUES (?,?,?,?)",
                        (
                            command.idempotency_key,
                            command.command_id,
                            digest,
                            pending.model_dump_json(),
                        ),
                    )
                    self.db.commit()
                    self.db.execute("BEGIN IMMEDIATE")
                    try:
                        started = time.monotonic()
                        permit = self._body(
                            self._request(
                                "POST",
                                self.prefix
                                + f"/commands/{command.command_id}/authorize-execution",
                                timeout=2,
                            )
                        )
                        if (
                            not isinstance(permit, dict)
                            or permit.get("authorized") is not True
                            or permit.get("command_id") != command.command_id
                            or time.monotonic() - started > 2
                        ):
                            raise ValueError(
                                "Execution permit acknowledgement mismatch"
                            )
                    except (requests.RequestException, ProtocolRejected, ValueError):
                        error = "Live execution authorization was unavailable or denied"
                    now = datetime.now(UTC)
                    if error is None and command.expires_at <= now:
                        error = "Command expired before mock action"
                if error is None:
                    self._set("output", arguments["value"])
                    self._set("executions", self.executions + 1)
                    event = DeviceEventV1(
                        event_id=f"evt_{uuid4().hex}",
                        device_id=self.device_id,
                        event_type="gpio.output.changed",
                        occurred_at=now,
                        payload={
                            "capability_id": CAPABILITY,
                            "channel": CHANNEL,
                            "value": self.output,
                            "reason": "set",
                            "mock": True,
                            "command_id": command.command_id,
                        },
                    ).model_dump(mode="json")
                    self._queue_state(now)
                    self._enqueue(event["event_id"], "/events", event)
                result = AgentCommandResult(
                    command_id=command.command_id,
                    device_id=self.device_id,
                    status="failed" if error else "succeeded",
                    completed_at=now,
                    error=error,
                    output={
                        "execution_state": "not_executed" if error else "executed",
                        "mock": True,
                        "outputs": {CHANNEL: self.output},
                    },
                )
                self.db.execute(
                    "INSERT INTO receipts VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET result=excluded.result",
                    (
                        command.idempotency_key,
                        command.command_id,
                        digest,
                        result.model_dump_json(),
                    ),
                )
            self._enqueue(
                f"result:{command.command_id}",
                f"/commands/{command.command_id}/result",
                result.model_dump(mode="json"),
            )
            self.db.commit()
            return result
        except BaseException:
            self.db.rollback()
            raise

    def poll(self):
        response = self._request("GET", self.prefix + "/commands/next")
        if response.status_code == 204:
            return None
        return self.execute(AgentCommand.model_validate(self._body(response)))

    def tick(self):
        status = self.enroll()
        if status != "approved":
            return status
        self.negotiate()
        self.publish_inventory()
        self.heartbeat()
        provider = self.register_capability()
        self.flush()
        self.reconcile()
        if provider.enabled:
            with self.db:
                self._queue_state(datetime.now(UTC))
        self.flush()
        self.poll()
        self.flush()
        return status
