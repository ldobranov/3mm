"""Persist a signed handoff and report root outcomes without replaying installs."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
import stat
import threading
import uuid
from typing import Callable

from pydantic import BaseModel, ConfigDict

from agent.node_update_client import NodeUpdateClient, NodeUpdateHelperError
from three_mm_protocol import AgentCommand
from three_mm_protocol.node_updates import NodeUpdateAuthorization, NodeUpdateOperation

TERMINAL_STATES = {"succeeded", "rolled_back", "failed"}


class NodeUpdateTracking(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    authorization: NodeUpdateAuthorization
    acknowledged: NodeUpdateOperation | None = None


class NodeUpdateExecution:
    def __init__(self, *, data_dir: Path, device_id: str, helper: NodeUpdateClient):
        self.path = Path(data_dir) / "node-update-tracking.json"
        self.device_id = device_id
        self.helper = helper
        self._lock = threading.RLock()

    def _load(self) -> NodeUpdateTracking | None:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16384:
            raise NodeUpdateHelperError("invalid_update_tracking")
        tracking = NodeUpdateTracking.model_validate_json(self.path.read_bytes())
        if tracking.authorization.request.device_id != self.device_id:
            raise NodeUpdateHelperError("node_update_device_mismatch")
        if tracking.acknowledged is not None:
            self._check_identity(tracking.acknowledged, tracking.authorization)
        return tracking

    def _save(self, tracking: NodeUpdateTracking) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.parent / (".node-update-tracking-" + uuid.uuid4().hex)
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(tracking.model_dump_json().encode("utf-8") + b"\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary, self.path)
            if os.name == "posix":
                descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _check_identity(operation: NodeUpdateOperation, authorization: NodeUpdateAuthorization):
        if any(getattr(operation, name) != getattr(authorization.request, name)
               for name in ("operation_id", "device_id", "release_id", "archive_sha256")):
            raise NodeUpdateHelperError("invalid_helper_operation")

    def apply(self, command: AgentCommand) -> NodeUpdateOperation:
        authorization = NodeUpdateAuthorization.model_validate(command.payload)
        request = authorization.request
        if (command.command_type != "agent.update.apply" or command.device_id != self.device_id
                or request.device_id != self.device_id):
            raise NodeUpdateHelperError("node_update_device_mismatch")
        if request.created_at != command.created_at or request.expires_at != command.expires_at:
            raise NodeUpdateHelperError("node_update_deadline_mismatch")
        with self._lock:
            tracking = self._load()
            if tracking is not None:
                if tracking.authorization.request.operation_id == request.operation_id:
                    if tracking.authorization != authorization:
                        raise NodeUpdateHelperError("node_update_replay_conflict")
                elif (tracking.acknowledged is None
                      or tracking.acknowledged.status not in TERMINAL_STATES):
                    raise NodeUpdateHelperError("node_update_unresolved")
                else:
                    tracking = None
            if tracking is None:
                if not request.created_at <= datetime.now(UTC) < request.expires_at:
                    raise NodeUpdateHelperError("expired_node_update_handoff")
                # Must survive the installer stopping/restarting this Agent, even
                # if the local helper's acceptance response is lost.
                self._save(NodeUpdateTracking(authorization=authorization))
            operation = self.helper.apply(authorization)
            self._check_identity(operation, authorization)
            return operation

    def report_pending(self, post: Callable[[str, dict], None]) -> None:
        """Poll only; a restart or failed HTTP report never authorizes execution."""
        with self._lock:
            tracking = self._load()
            if tracking is None:
                return
            operation = self.helper.status(tracking.authorization.request.operation_id)
            if operation is None or operation == tracking.acknowledged:
                return
            self._check_identity(operation, tracking.authorization)
            acknowledged = tracking.acknowledged
            if acknowledged is not None and (
                operation.updated_at < acknowledged.updated_at
                or acknowledged.status in TERMINAL_STATES
                or (acknowledged.status == "unknown" and operation.status in {"accepted", "running"})
                or (acknowledged.status == "running" and operation.status == "accepted")
            ):
                raise NodeUpdateHelperError("node_update_outcome_regression")

        # Do not put intermediate outcomes in the general outbox: a delayed
        # accepted/running report must not overwrite a terminal outcome. On
        # network failure this durable tracker polls the newest root record.
        post(f"node-updates/{operation.operation_id}/report", operation.model_dump(mode="json"))
        with self._lock:
            current = self._load()
            if current is not None and current.authorization == tracking.authorization:
                self._save(current.model_copy(update={"acknowledged": operation}))
