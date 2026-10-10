"""Host-selected file access through current Core authority, never direct I/O."""

import base64
from dataclasses import dataclass, field
import hashlib
import uuid

from three_mm_application_sdk.files import (
    ApplicationFile,
    ApplicationFileStorage,
    ApplicationFileStorageError,
)
from three_mm_application_sdk.file_wire import parse_file_request
from three_mm_application_sdk.transaction_guard import (
    require_outside_relational_transaction,
)


class ApplicationFileExecutionUnconfirmed(ApplicationFileStorageError):
    def __init__(self, request_id):
        self.request_id = request_id
        super().__init__(
            "Private file outcome is unconfirmed; inspect its receipt before retrying"
        )


@dataclass(frozen=True, slots=True)
class ApplicationScopedFileStorage(ApplicationFileStorage):
    platform: object | None = field(default=None, kw_only=True, repr=False)

    def _invoke(self, operation, *, request_id=None, **fields):
        # Refuse before transport/uncertain-outcome handling: this operation is
        # provably not started, not an ambiguous file mutation.
        require_outside_relational_transaction()
        value = {
            "file_request_version": 1,
            "request_id": uuid.uuid4().hex if request_id is None else request_id,
            "operation": operation,
            **fields,
        }
        value, _ = parse_file_request(value)
        if self.platform is None:
            raise ApplicationFileStorageError(
                "Declared private files require supported applied storage authority"
            )
        if operation in {"put", "delete"} and self.mode != "read_write":
            raise ApplicationFileStorageError("Private file storage is read-only")
        try:
            response = self.platform._call("files.execute", {"file_request": value})
        except RuntimeError:
            if operation in {"put", "delete"}:
                raise ApplicationFileExecutionUnconfirmed(value["request_id"]) from None
            raise ApplicationFileStorageError(
                "Private file authority or runtime is unavailable"
            ) from None
        receipt = response.get("receipt") if type(response) is dict else None
        if (
            type(receipt) is not dict
            or receipt.get("request_id") != value["request_id"]
            or receipt.get("operation") != operation
            or receipt.get("file_id") != value.get("file_id")
        ):
            if operation in {"put", "delete"}:
                raise ApplicationFileExecutionUnconfirmed(value["request_id"])
            raise ApplicationFileStorageError("Private file receipt is invalid")
        if receipt.get("outcome") != "completed":
            raise ApplicationFileExecutionUnconfirmed(value["request_id"])
        return response, value

    def get(self, file_id):
        response, _ = self._invoke("get", file_id=file_id)
        result = response.get("file_result")
        if type(result) is not dict or "file" not in result:
            raise ApplicationFileStorageError("Private file response is invalid")
        item = result["file"]
        if item is None:
            return None
        try:
            content = base64.b64decode(item["content_base64"], validate=True)
            if (
                item["file_id"] != file_id
                or len(content) > self.limits.max_file_bytes
                or item["size_bytes"] != len(content)
                or item["sha256"] != hashlib.sha256(content).hexdigest()
            ):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ApplicationFileStorageError(
                "Private file response is invalid"
            ) from None
        return ApplicationFile(file_id, content, item["sha256"])

    def list_entries(self):
        response, _ = self._invoke("list")
        entries = response.get("file_result", {}).get("entries")
        if type(entries) is not list or len(entries) > self.limits.max_files:
            raise ApplicationFileStorageError("Private file response is invalid")
        result = []
        for entry in entries:
            if type(entry) is not list or len(entry) != 2:
                raise ApplicationFileStorageError("Private file response is invalid")
            name, size = entry
            self._identity(name)
            if type(size) is not int or not 0 <= size <= self.limits.max_file_bytes:
                raise ApplicationFileStorageError("Private file response is invalid")
            result.append((name, size))
        if (
            result != sorted(result)
            or len({name for name, _ in result}) != len(result)
            or sum(size for _, size in result) > self.limits.max_total_bytes
        ):
            raise ApplicationFileStorageError("Private file response is invalid")
        return result

    def put(self, file_id, content, *, expected_sha256, request_id=None):
        if type(content) is not bytes or len(content) > self.limits.max_file_bytes:
            raise ApplicationFileStorageError(
                "Private file content is invalid or exceeds its limit"
            )
        response, value = self._invoke(
            "put",
            request_id=request_id,
            file_id=file_id,
            expected_sha256=expected_sha256,
            content_base64=base64.b64encode(content).decode("ascii"),
        )
        receipt = response["receipt"]
        digest = hashlib.sha256(content).hexdigest()
        if receipt.get("sha256") != digest or receipt.get("size_bytes") != len(content):
            raise ApplicationFileExecutionUnconfirmed(value["request_id"])
        return ApplicationFile(file_id, content, digest)

    def delete(self, file_id, *, expected_sha256, request_id=None):
        self._invoke(
            "delete",
            request_id=request_id,
            file_id=file_id,
            expected_sha256=expected_sha256,
        )

    def operation_status(self, request_id):
        require_outside_relational_transaction()
        # Historical metadata only; never read bytes or re-execute an operation.
        if self.platform is None:
            raise ApplicationFileStorageError("Private file authority is unavailable")
        return self.platform._call("files.status", {"file_request_id": request_id})

    def _locked(self, *, write):
        raise ApplicationFileStorageError(
            "Scoped files cannot fall back to direct SDK access"
        )
