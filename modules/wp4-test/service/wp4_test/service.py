"""No background work, direct files, device commands, network or auto-grants."""
from three_mm_application_sdk import ApplicationPlatformError
from three_mm_application_sdk.files import ApplicationFileStorageError
from three_mm_application_sdk.scoped_files import (
    ApplicationScopedFileStorage, ApplicationFileExecutionUnconfirmed,
)


class Service:
    def __init__(self, application):
        self.application = application

    def handle(self, operation_id, payload, context):
        if operation_id == "health" and context.audience == "internal":
            return {"status": "ready"}
        if context.audience != "administrator" or context.user_id is None:
            raise ValueError("A Core-authenticated administrator is required")
        if operation_id == "echo":
            return {"message": payload["message"]}
        # Even a misconfigured/old host must not select a direct-file fallback.
        files = self.application.file_storage
        if not isinstance(files, ApplicationScopedFileStorage):
            raise ValueError("This fixture requires the scoped private-file adapter")
        if operation_id == "file_get":
            try:
                item = files.get("probe")
                return {"status": "found" if item else "missing",
                    "text": item.content.decode("utf-8") if item else "",
                    "sha256": item.sha256 if item else None}
            except ApplicationFileStorageError:
                return {"status": "blocked", "text": "", "sha256": None}
        if operation_id == "file_put":
            if context.idempotency_key != payload["request_id"]:
                raise ValueError("Use the same file request ID and command idempotency key")
            try:
                item = files.put("probe", payload["text"].encode("utf-8"),
                    expected_sha256=payload["expected_sha256"], request_id=payload["request_id"])
                return {"status": "stored", "request_id": payload["request_id"], "sha256": item.sha256}
            except ApplicationFileExecutionUnconfirmed:
                # A denied/lost transport response cannot prove no write occurred.
                # Never retry automatically or invent a replacement request ID.
                return {"status": "unconfirmed", "request_id": payload["request_id"], "sha256": None}
            except ApplicationFileStorageError:
                return {"status": "blocked", "request_id": payload["request_id"], "sha256": None}
        if operation_id == "file_receipt":
            try:
                return {"status": "available", "receipt": files.operation_status(payload["request_id"])}
            except (ApplicationFileStorageError, ApplicationPlatformError):
                return {"status": "blocked", "receipt": None}
        raise ValueError("Unknown test operation")


def create_service(application):
    return Service(application)
