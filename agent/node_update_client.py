"""Small unprivileged Node-only helper client; never executes installer commands."""

import json
import re
import socket
from pathlib import Path

from three_mm_protocol.node_updates import (
    NodeUpdateAuthorization,
    NodeUpdateOperation,
    NodeUpdatePrepareRequest,
    NodeUpdatePreparedArtifact,
    NodeUpdateSupport,
)

SOCKET_PATH = Path("/run/3mm-node-update/helper.sock")
MAX_RESPONSE_BYTES = 65536


class NodeUpdateHelperError(RuntimeError):
    pass


class NodeUpdateClient:
    def __init__(self, socket_path: Path = SOCKET_PATH, timeout_seconds: float = 2.0):
        self.socket_path = socket_path
        self.timeout_seconds = timeout_seconds
    def prepare(
        self,
        request: NodeUpdatePrepareRequest,
    ) -> NodeUpdatePreparedArtifact:
        result = self._exchange(
            {
                "action": "prepare",
                "request": request.model_dump(mode="json"),
            }
        )

        try:
            prepared = NodeUpdatePreparedArtifact.model_validate(
                result["prepared"]
            )
        except (KeyError, ValueError) as exc:
            raise NodeUpdateHelperError(
                "invalid_helper_prepared_artifact"
            ) from exc

        for field in (
            "operation_id",
            "device_id",
            "release_id",
            "archive_sha256",
            "archive_size_bytes",
        ):
            if getattr(prepared, field) != getattr(request, field):
                raise NodeUpdateHelperError(
                    "invalid_helper_prepared_artifact"
                )

        return prepared
    
    def apply(self, authorization: NodeUpdateAuthorization) -> NodeUpdateOperation:
        request = authorization.request
        operation = self._request({"action": "apply", "request": authorization.model_dump(mode="json")})
        if operation is None or any(
            getattr(operation, field) != getattr(request, field)
            for field in ("operation_id", "device_id", "release_id", "archive_sha256")
        ):
            raise NodeUpdateHelperError("invalid_helper_operation")
        return operation

    def status(self, operation_id: str | None = None) -> NodeUpdateOperation | None:
        if operation_id is not None and not re.fullmatch(r"nodeupd_[0-9a-f]{32}", operation_id):
            raise NodeUpdateHelperError("invalid_operation_id")
        payload = {"action": "status"}
        if operation_id is not None:
            payload["operation_id"] = operation_id
        operation = self._request(payload)
        if operation is not None and operation_id is not None and operation.operation_id != operation_id:
            raise NodeUpdateHelperError("invalid_helper_operation")
        return operation

    def support(self) -> NodeUpdateSupport:
        try:
            return NodeUpdateSupport.model_validate(self._exchange({"action": "support"})["support"])
        except (ValueError, KeyError) as exc:
            raise NodeUpdateHelperError("invalid_helper_support") from exc

    def _request(
        self,
        payload: dict,
    ) -> NodeUpdateOperation | None:
        result = self._exchange(payload)

        try:
            operation = result["operation"]
        except KeyError as exc:
            raise NodeUpdateHelperError(
                "node_update_helper_unavailable_or_rejected"
            ) from exc

        return (
            NodeUpdateOperation.model_validate(operation)
            if operation is not None
            else None
        )
        
    def _exchange(self, payload: dict) -> dict:
        try:
            with socket.socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM,
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(str(self.socket_path))
                connection.sendall(
                    json.dumps(
                        payload,
                        separators=(",", ":"),
                    ).encode()
                    + b"\n"
                )

                response = bytearray()

                while len(response) <= MAX_RESPONSE_BYTES:
                    chunk = connection.recv(
                        min(
                            4096,
                            MAX_RESPONSE_BYTES + 1 - len(response),
                        )
                    )

                    if not chunk:
                        break

                    response.extend(chunk)

                    if b"\n" in chunk:
                        break

            if len(response) > MAX_RESPONSE_BYTES:
                raise ValueError("response_too_large")

            result = json.loads(response.split(b"\n", 1)[0])

            if (
                not isinstance(result, dict)
                or result.get("ok") is not True
            ):
                if (
                    isinstance(result, dict)
                    and re.fullmatch(
                        r"[a-z0-9_]{1,80}",
                        str(result.get("error", "")),
                    )
                ):
                    raise NodeUpdateHelperError(result["error"])

                raise ValueError("helper_rejected_request")

            return result

        except (OSError, ValueError, KeyError, AttributeError) as exc:
            raise NodeUpdateHelperError(
                "node_update_helper_unavailable_or_rejected"
            ) from exc
