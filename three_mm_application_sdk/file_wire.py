"""Bounded SDK/host file messages. No paths, grants or implicit retries."""

import base64
import hashlib
import json
import re

from three_mm_application_sdk.files import (
    ApplicationFileStorage,
    ApplicationFileStorageError,
)


MAX_SCOPED_FILE_BYTES = 1024 * 1024
MAX_FILE_MESSAGE_BYTES = 2 * 1024 * 1024
FILE_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")


def parse_file_request(value):
    if (
        type(value) is not dict
        or type(value.get("file_request_version")) is not int
        or value["file_request_version"] != 1
    ):
        raise ValueError("Private file request is invalid")
    request_id, action = value.get("request_id"), value.get("operation")
    if type(action) is not str:
        raise ValueError("Private file operation is invalid")
    if type(request_id) is not str or not FILE_REQUEST_ID.fullmatch(request_id):
        raise ValueError("Private file request identity is invalid")
    required = {"file_request_version", "request_id", "operation"}
    if action in {"get", "put", "delete"}:
        required.add("file_id")
        ApplicationFileStorage._identity(value.get("file_id"))
    elif action != "list":
        raise ValueError("Private file operation is invalid")
    if action in {"put", "delete"}:
        required.add("expected_sha256")
        ApplicationFileStorage._expected(value.get("expected_sha256"))
        if action == "delete" and value.get("expected_sha256") is None:
            raise ValueError("Private file deletion requires an expected digest")
    content = None
    if action == "put":
        required.add("content_base64")
        encoded = value.get("content_base64")
        if type(encoded) is not str or len(encoded) > 4 * (
            (MAX_SCOPED_FILE_BYTES + 2) // 3
        ):
            raise ValueError("Private file content exceeds the scoped transport limit")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ValueError("Private file content is invalid") from None
        if (
            len(content) > MAX_SCOPED_FILE_BYTES
            or base64.b64encode(content).decode("ascii") != encoded
        ):
            raise ValueError("Private file content is invalid or exceeds its limit")
    if set(value) != required:
        raise ValueError("Private file request fields are invalid")
    return dict(value), content


def file_request_identity(request):
    # Content is hashed, not retained in the Core journal/audit.
    value, content = parse_file_request(request)
    if content is not None:
        value.pop("content_base64")
        value.update(
            content_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
        )
    return hashlib.sha256(
        b"3mm:private-file-request:v1\x00"
        + json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def execute_file_request(storage, request):
    value, content = parse_file_request(request)
    operation = value["operation"]
    if operation == "list":
        return {"entries": [[name, size] for name, size in storage.list_entries()]}
    file_id = value["file_id"]
    if operation == "delete":
        storage.delete(file_id, expected_sha256=value["expected_sha256"])
        return {"deleted": True}
    item = (
        storage.get(file_id)
        if operation == "get"
        else storage.put(file_id, content, expected_sha256=value["expected_sha256"])
    )
    if item is None:
        return {"file": None}
    if len(item.content) > MAX_SCOPED_FILE_BYTES:
        raise ApplicationFileStorageError(
            "Private file exceeds the scoped transport limit"
        )
    result = {
        "file_id": item.file_id,
        "sha256": item.sha256,
        "size_bytes": len(item.content),
    }
    if operation == "get":
        result["content_base64"] = base64.b64encode(item.content).decode("ascii")
    return {"file": result}


def file_receipt(request, result=None, *, outcome="execution_unconfirmed"):
    value, _ = parse_file_request(request)
    receipt = {
        "request_id": value["request_id"],
        "operation": value["operation"],
        "outcome": outcome,
    }
    if "file_id" in value:
        receipt["file_id"] = value["file_id"]
    if result and type(result.get("file")) is dict:
        item = result["file"]
        receipt.update(sha256=item["sha256"], size_bytes=item["size_bytes"])
    return receipt


def validate_file_result(result, request, limits):
    """Do not promote a malformed/mismatched worker reply to completion."""
    value, content = parse_file_request(request)
    operation = value["operation"]
    if type(result) is not dict:
        raise ValueError("Private file result is invalid")
    if operation == "delete":
        if set(result) != {"deleted"} or result["deleted"] is not True:
            raise ValueError("Private file result is invalid")
        return
    if operation == "list":
        entries = result.get("entries")
        if (
            set(result) != {"entries"}
            or type(entries) is not list
            or len(entries) > limits.max_files
        ):
            raise ValueError("Private file result is invalid")
        names, total = [], 0
        for entry in entries:
            if type(entry) is not list or len(entry) != 2:
                raise ValueError("Private file result is invalid")
            name, size = entry
            ApplicationFileStorage._identity(name)
            if type(size) is not int or not 0 <= size <= limits.max_file_bytes:
                raise ValueError("Private file result is invalid")
            names.append(name)
            total += size
        if names != sorted(set(names)) or total > limits.max_total_bytes:
            raise ValueError("Private file result is invalid")
        return
    if set(result) != {"file"}:
        raise ValueError("Private file result is invalid")
    item = result["file"]
    if item is None and operation == "get":
        return
    fields = {"file_id", "sha256", "size_bytes"} | (
        {"content_base64"} if operation == "get" else set()
    )
    if (
        type(item) is not dict
        or set(item) != fields
        or item["file_id"] != value["file_id"]
        or type(item["size_bytes"]) is not int
        or not 0 <= item["size_bytes"] <= limits.max_file_bytes
    ):
        raise ValueError("Private file result is invalid")
    if operation == "get":
        encoded = item["content_base64"]
        if type(encoded) is not str or len(encoded) > 4 * (
            (limits.max_file_bytes + 2) // 3
        ):
            raise ValueError("Private file result is invalid")
        content = base64.b64decode(encoded, validate=True)
        if base64.b64encode(content).decode("ascii") != encoded:
            raise ValueError("Private file result is invalid")
    if (
        len(content) != item["size_bytes"]
        or hashlib.sha256(content).hexdigest() != item["sha256"]
    ):
        raise ValueError("Private file result is invalid")
