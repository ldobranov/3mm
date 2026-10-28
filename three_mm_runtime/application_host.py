"""Run one reviewed application extension wheel outside the Core process."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import socket
import sys
import time
from collections import deque
from contextlib import ExitStack, nullcontext
from pathlib import Path

from three_mm_protocol.application_requirements import ApplicationPlatformRequirementV1, ApplicationRequirementsRequestV1
from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationFileLimits,
    ApplicationFileStorage,
    ApplicationFileStorageError,
    ApplicationMigration,
    ApplicationPlatformClient,
    ApplicationScopedFileStorage,
    ApplicationStorage,
    OperationContext,
)
from three_mm_protocol.application_extension import ApplicationPrivateFilesV1, ApplicationPrivateFilesV2
from three_mm_application_sdk.scoped_media import ApplicationScopedMediaStorage
from three_mm_application_sdk.file_wire import MAX_SCOPED_FILE_BYTES
from three_mm_runtime.application_file_executor import ApplicationFileExecutor
from three_mm_runtime.application_relational_runtime import PreparedRelationalRuntime
from three_mm_runtime.application_transport import (
    ApplicationTransportError,
    read_message,
    send_message,
    sign_message,
    verify_message,
)


class _AwaitingFileAuthority(ApplicationFileStorage):
    """Declared files never fall back to ungranted native SDK access.

    This is a cooperative reviewed-native denial, not OS isolation. All public
    file operations enter _locked before filesystem access. Requests outside the
    supported scoped transport never acquire a native-helper fallback. The
    trusted backup/rollback adapter remains independent.
    """

    def _locked(self, *, write: bool):
        raise ApplicationFileStorageError(
            "Declared private files require supported applied storage authority"
        )


def _private_file_adapter(storage_metadata, data_dir, platform=None):
    request = storage_metadata.get("private_files")
    if request is None:
        if storage_metadata.get("relational") is not None:
            # Opting into scoped DB authority never grants the undeclared legacy
            # file helper. A separate exact private-files declaration is needed.
            return _AwaitingFileAuthority(data_dir)
        return None  # Existing undeclared SDK 1.0–1.3 behavior is unchanged.
    try:
        declaration = (ApplicationPrivateFilesV2 if request.get('file_contract_version') == 2 else ApplicationPrivateFilesV1).model_validate(request)
    except ValueError:
        raise RuntimeError("Application private file metadata is invalid") from None
    if declaration.file_contract_version == 2:
        return ApplicationScopedMediaStorage(data_dir, platform, declaration)
    adapter = ApplicationScopedFileStorage if declaration.max_file_bytes <= MAX_SCOPED_FILE_BYTES else _AwaitingFileAuthority
    return adapter(
        data_dir,
        mode=declaration.mode,
        limits=ApplicationFileLimits(
            declaration.max_file_bytes,
            declaration.max_total_bytes,
            declaration.max_files,
        ),
        **({"platform": platform} if adapter is ApplicationScopedFileStorage else {}),
    )


def _require_supported_storage(metadata, relational_runtime=None, instance_root=None):
    storage = metadata.get("storage")
    if not isinstance(storage, dict):
        raise RuntimeError("Application storage metadata is invalid")
    if storage.get("relational") is not None:
        if type(relational_runtime) is not PreparedRelationalRuntime:
            raise RuntimeError(
                "Application relational storage runtime is not implemented "
                "without a prepared lifecycle"
            )
        relational_runtime.require_metadata(metadata, instance_root)
    return storage


def _load_service(
    metadata: dict[str, object],
    instance_root: Path,
    platform_secret: bytes | None = None,
    *,
    relational_runtime=None,
):
    storage_metadata = _require_supported_storage(
        metadata, relational_runtime, instance_root
    )
    if relational_runtime is not None and os.geteuid() == 0:
        raise RuntimeError("Relational application code must run as a non-root service")
    wheel_name = metadata.get("wheel")
    entrypoint = metadata.get("entrypoint")
    if not isinstance(wheel_name, str) or not isinstance(entrypoint, str):
        raise RuntimeError("Application service metadata is invalid")
    release_dir = instance_root / "releases" / str(metadata.get("sha256"))
    wheel = (release_dir / wheel_name).resolve()
    if release_dir.resolve() not in wheel.parents or not wheel.is_file():
        raise RuntimeError("Application service wheel is unavailable")
    module_name, factory_name = entrypoint.split(":", 1)
    migration_entrypoint = storage_metadata.get("migration_entrypoint")
    target_revision = storage_metadata.get("schema_revision")
    if not isinstance(migration_entrypoint, str) or not isinstance(target_revision, str):
        raise RuntimeError("Application storage metadata is invalid")
    requirements = metadata.get('platform_requirements', [])
    if not isinstance(requirements, list) or len(requirements) > 16:
        raise RuntimeError('Application platform requirements metadata is invalid')
    requirements = tuple(ApplicationPlatformRequirementV1.model_validate_json(json.dumps(item)) for item in requirements)
    if requirements:
        ApplicationRequirementsRequestV1(requirements=requirements)
    # Validate before importing migrations, opening SQLite or calling package code.
    # A declaration is not a grant and must not select the legacy file adapter.
    platform = (
        ApplicationPlatformClient(Path(metadata["platform_socket"]), metadata["instance_id"], platform_secret)
        if platform_secret is not None and isinstance(metadata.get("platform_socket"), str)
        and isinstance(metadata.get("instance_id"), str) else None
    )
    if relational_runtime is not None:
        # Root-managed boot requires CURRENT Core trust BEFORE changing the
        # import path or importing any wheel module. No SQL/grant fallback.
        relational_runtime.require_boot_startup(platform)
    sys.path.insert(0, str(wheel))
    file_storage = _private_file_adapter(storage_metadata, instance_root / "data", platform)
    if relational_runtime is None:
        migration_module, migration_factory_name = migration_entrypoint.split(":", 1)
        migration_factory = getattr(
            importlib.import_module(migration_module), migration_factory_name
        )
        migrations = migration_factory()
        if not isinstance(migrations, (list, tuple)) or not all(
            isinstance(item, ApplicationMigration) for item in migrations
        ):
            raise RuntimeError("Application migration entrypoint is invalid")
        storage = ApplicationStorage(instance_root / "data")
        storage.migrate(migrations, target_revision)
        factory = getattr(importlib.import_module(module_name), factory_name)
    else:
        # Normal restart never imports/runs migration code. Both the wheel and
        # prepared schema were checked before any package service import.
        from three_mm_runtime.application_relational_migrations import _migration_factory

        storage = relational_runtime.storage(platform)
        factory = _migration_factory(wheel, entrypoint)
    context = ApplicationContext(
        module_id=str(metadata["module_id"]),
        version=str(metadata["version"]),
        data_dir=instance_root / "data",
        configuration=dict(metadata.get("configuration") or {}),
        storage=storage,
        file_storage=file_storage,
        platform=platform,
        platform_requirements=requirements,
    )
    service = factory(context)
    if not callable(getattr(service, "handle", None)):
        raise RuntimeError("Application service does not implement the SDK")
    return service


def serve(instance: str, root: Path, key_root: Path, group_id: int | None = None) -> None:
    instance_root = (root / instance).resolve()
    if root.resolve() not in instance_root.parents:
        raise RuntimeError("Application instance path is invalid")
    metadata = json.loads((instance_root / "active.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("instance_id") != instance:
        raise RuntimeError("Application service metadata is invalid")
    relational = metadata.get("storage", {}).get("relational") is not None
    if not relational:
        _require_supported_storage(metadata)
    secret = (key_root / f"{instance}.key").read_bytes()
    if len(secret) != 32:
        raise RuntimeError("Application service key is invalid")
    with ExitStack() as executors:
        runtime = None
        if relational:
            try:
                runtime = executors.enter_context(
                    PreparedRelationalRuntime(instance_root, metadata, secret, group_id)
                )
            except (ValueError, KeyError, OSError) as error:
                raise RuntimeError(
                    "Application relational storage runtime is not implemented "
                    "without a verified prepared lifecycle"
                ) from error
        _require_supported_storage(metadata, runtime, instance_root)
        request = metadata.get("storage", {}).get("private_files")
        if request is not None:
            declaration = (ApplicationPrivateFilesV2 if request.get('file_contract_version') == 2 else ApplicationPrivateFilesV1).model_validate(request)
            if declaration.file_contract_version == 2 or declaration.max_file_bytes <= MAX_SCOPED_FILE_BYTES:
                # Factory/handler SDK calls wait on Core; never call back into
                # their occupied serial service.sock. Own one bounded worker.
                executors.enter_context(ApplicationFileExecutor(instance_root, metadata, secret, group_id))
        if runtime is None:
            service = _load_service(metadata, instance_root, secret)
            _serve_requests(metadata, instance_root, secret, service, group_id)
        else:
            service = _load_service(
                metadata, instance_root, secret, relational_runtime=runtime
            )
            _serve_requests(
                metadata, instance_root, secret, service, group_id,
                relational_runtime=runtime,
            )


def _serve_requests(
    metadata, instance_root, secret, service, group_id, *, relational_runtime=None
):
    _require_supported_storage(metadata, relational_runtime, instance_root)
    storage = (
        ApplicationStorage(instance_root / "data")
        if relational_runtime is None else None
    )
    socket_path = instance_root / "run" / "service.sock"
    socket_path.unlink(missing_ok=True)
    recent: deque[tuple[str, int]] = deque(maxlen=4096)
    seen: set[str] = set()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        if group_id is not None:
            os.chown(socket_path, -1, group_id)
        os.chmod(socket_path, 0o660)
        server.listen(16)
        while True:
            connection, _ = server.accept()
            with connection:
                request_id = "invalid"
                try:
                    request = verify_message(read_message(connection), secret)
                    request_id = str(request["request_id"])
                    if request_id in seen:
                        raise ApplicationTransportError(
                            "Application service request was already processed"
                        )
                    recent.append((request_id, int(time.time())))
                    seen.add(request_id)
                    while recent and recent[0][1] < int(time.time()) - 60:
                        expired, _ = recent.popleft()
                        seen.discard(expired)
                    operation_id = request.get("operation_id")
                    payload = request.get("payload")
                    raw_context = request.get("context")
                    if (
                        not isinstance(operation_id, str)
                        or not isinstance(payload, dict)
                        or not isinstance(raw_context, dict)
                    ):
                        raise ApplicationTransportError(
                            "Application service request is invalid"
                        )
                    if operation_id in {"three_mm.host.info", "three_mm.task.info", "three_mm.delegation.info"}:
                        if raw_context != {"audience": "internal"} or payload:
                            raise ApplicationTransportError("Host metadata requires an internal empty request")
                        import hashlib
                        from three_mm_runtime.application_host_identity import build_identity, HOST_CONTRACT
                        response = {"ok": True, "result": {
                            "host_contract": HOST_CONTRACT, "build_id": build_identity(),
                            **({**({"task_execution_contract": 1} if operation_id == "three_mm.task.info"
                                    else {"operation_delegation_contract": 1}),
                                "artifact_sha256": metadata["sha256"], "module_id": metadata["module_id"],
                                "configuration_sha256": hashlib.sha256(json.dumps(metadata.get("configuration", {}),
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()}
                                if operation_id != "three_mm.host.info" else {}),
                            "pid": os.getpid(), "uid": os.geteuid(),
                            "instance_id": metadata["instance_id"],
                            "metadata_sha256": hashlib.sha256(json.dumps(metadata,
                                sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                        }}
                        send_message(connection, sign_message({"version": 1,
                            "request_id": request_id, "timestamp": int(time.time()), **response}, secret))
                        continue
                    if operation_id == "three_mm.platform.status":
                        if raw_context.get("audience") != "internal":
                            raise ApplicationTransportError(
                                "Platform status requires the internal audience"
                            )
                        response = {
                            "ok": True,
                            "result": (
                                storage.status() if relational_runtime is None
                                else relational_runtime.readiness()
                            ),
                        }
                        send_message(
                            connection,
                            sign_message(
                                {
                                    "version": 1,
                                    "request_id": request_id,
                                    "timestamp": int(time.time()),
                                    **response,
                                },
                                secret,
                            ),
                        )
                        continue
                    operations = metadata.get("operations")
                    declared = next(
                        (
                            item
                            for item in operations
                            if isinstance(item, dict)
                            and item.get("operation_id") == operation_id
                        ),
                        None,
                    ) if isinstance(operations, list) else None
                    audience = raw_context.get("audience")
                    idempotency_key = raw_context.get("idempotency_key")
                    if (
                        not isinstance(declared, dict)
                        or not isinstance(audience, str)
                        or audience not in declared.get("audiences", [])
                    ):
                        raise ApplicationTransportError(
                            "Application operation is not declared for this audience"
                        )
                    if (
                        declared.get("idempotency") == "required"
                        and not isinstance(idempotency_key, str)
                    ):
                        raise ApplicationTransportError(
                            "Application operation requires an idempotency key"
                        )
                    if (
                        declared.get("idempotency") == "forbidden"
                        and idempotency_key is not None
                    ):
                        raise ApplicationTransportError(
                            "Application operation forbids an idempotency key"
                        )
                    from three_mm_protocol.application_delegation import OperationExecutorV1
                    executor = OperationExecutorV1(module_id=metadata["module_id"],
                        instance_id=metadata["instance_id"], artifact_sha256=metadata["sha256"])
                    if raw_context.get("executor", executor.model_dump()) != executor.model_dump():
                        raise ApplicationTransportError("Operation executor does not match this host")
                    context = OperationContext.from_platform({**raw_context, "executor": executor.model_dump()})
                    if context.delegation is not None:
                        from datetime import UTC, datetime
                        from three_mm_protocol.application_delegation import bounded_object
                        import hashlib
                        digest = hashlib.sha256(json.dumps(bounded_object(payload), sort_keys=True,
                            separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                        if (context.delegation.operation_id != operation_id
                                or context.delegation.payload_sha256 != digest
                                or datetime.now(UTC) >= context.delegation.expires_at):
                            raise ApplicationTransportError("Delegation is expired or belongs to different input")
                    if declared.get("kind") == "task":
                        execution = context.task_execution
                        task = next((item for item in metadata.get("tasks", [])
                            if isinstance(item, dict) and execution is not None
                            and item.get("task_id") == execution.task_id), None)
                        if (task is None or task.get("handler_operation_id") != operation_id
                                or context.idempotency_key != execution.task_run_id):
                            raise ApplicationTransportError("Task context does not match the declared handler")
                        from datetime import UTC, datetime
                        started = time.clock_gettime(time.CLOCK_BOOTTIME)
                        permit = ApplicationPlatformClient(Path(metadata["platform_socket"]), metadata["instance_id"],
                            secret, timeout_seconds=2).start_task(execution)
                        expires = datetime.fromisoformat(permit["lease_until"].replace("Z", "+00:00"))
                        if time.clock_gettime(time.CLOCK_BOOTTIME) - started > min(2, permit["lease_remaining_seconds"]) or datetime.now(UTC) >= expires:
                            raise ApplicationTransportError("Task execution permit is no longer current")
                    elif context.task_execution is not None:
                        raise ApplicationTransportError("Task context is reserved for task handlers")
                    ticket = request.get("relational_invocation")
                    if relational_runtime is None:
                        if ticket is not None:
                            raise ApplicationTransportError("Unexpected relational invocation")
                        boundary = nullcontext()
                    elif operation_id == metadata.get("health_operation_id"):
                        if ticket is not None:
                            raise ApplicationTransportError(
                                "Health cannot acquire relational SQL authority"
                            )
                        boundary = nullcontext()
                    else:
                        boundary = relational_runtime.session.invocation(
                            ticket, operation_id=operation_id
                        )
                    from three_mm_application_sdk.transaction_guard import host_operation
                    with boundary, host_operation():
                        result = service.handle(operation_id, payload, context)
                    if not isinstance(result, dict):
                        raise ApplicationTransportError(
                            "Application operation returned an invalid result"
                        )
                    response = {"ok": True, "result": result}
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)[:500]}
                send_message(
                    connection,
                    sign_message(
                        {
                            "version": 1,
                            "request_id": request_id,
                            "timestamp": int(time.time()),
                            **response,
                        },
                        secret,
                    ),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument(
        "--root", type=Path, default=Path("/var/lib/3mm/application-extensions")
    )
    parser.add_argument(
        "--key-root", type=Path, default=Path("/etc/3mm/application-extensions")
    )
    parser.add_argument("--group")
    arguments = parser.parse_args()
    group_id = None
    if arguments.group:
        import grp

        group_id = grp.getgrnam(arguments.group).gr_gid
    serve(arguments.instance, arguments.root, arguments.key_root, group_id)


if __name__ == "__main__":
    main()
