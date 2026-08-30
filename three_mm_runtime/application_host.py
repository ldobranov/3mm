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
from pathlib import Path

from three_mm_application_sdk import (
    ApplicationContext,
    ApplicationMigration,
    ApplicationPlatformClient,
    ApplicationStorage,
    OperationContext,
)
from three_mm_runtime.application_transport import (
    ApplicationTransportError,
    read_message,
    send_message,
    sign_message,
    verify_message,
)


def _load_service(
    metadata: dict[str, object],
    instance_root: Path,
    platform_secret: bytes | None = None,
):
    wheel_name = metadata.get("wheel")
    entrypoint = metadata.get("entrypoint")
    if not isinstance(wheel_name, str) or not isinstance(entrypoint, str):
        raise RuntimeError("Application service metadata is invalid")
    release_dir = instance_root / "releases" / str(metadata.get("sha256"))
    wheel = (release_dir / wheel_name).resolve()
    if release_dir.resolve() not in wheel.parents or not wheel.is_file():
        raise RuntimeError("Application service wheel is unavailable")
    module_name, factory_name = entrypoint.split(":", 1)
    sys.path.insert(0, str(wheel))
    storage_metadata = metadata.get("storage")
    if not isinstance(storage_metadata, dict):
        raise RuntimeError("Application storage metadata is invalid")
    migration_entrypoint = storage_metadata.get("migration_entrypoint")
    target_revision = storage_metadata.get("schema_revision")
    if not isinstance(migration_entrypoint, str) or not isinstance(target_revision, str):
        raise RuntimeError("Application storage metadata is invalid")
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
    context = ApplicationContext(
        module_id=str(metadata["module_id"]),
        version=str(metadata["version"]),
        data_dir=instance_root / "data",
        configuration=dict(metadata.get("configuration") or {}),
        storage=storage,
        platform=(
            ApplicationPlatformClient(
                Path(str(metadata["platform_socket"])),
                str(metadata["instance_id"]),
                platform_secret,
            )
            if platform_secret is not None
            and isinstance(metadata.get("platform_socket"), str)
            and isinstance(metadata.get("instance_id"), str)
            else None
        ),
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
    secret = (key_root / f"{instance}.key").read_bytes()
    if len(secret) != 32:
        raise RuntimeError("Application service key is invalid")
    service = _load_service(metadata, instance_root, secret)
    storage = ApplicationStorage(instance_root / "data")
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
                    if operation_id == "three_mm.platform.status":
                        if raw_context.get("audience") != "internal":
                            raise ApplicationTransportError(
                                "Platform status requires the internal audience"
                            )
                        response = {
                            "ok": True,
                            "result": storage.status(),
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
                    context = OperationContext(
                        audience=audience,
                        correlation_id=str(raw_context.get("correlation_id", "")),
                        user_id=raw_context.get("user_id")
                        if isinstance(raw_context.get("user_id"), int)
                        and not isinstance(raw_context.get("user_id"), bool)
                        else None,
                        idempotency_key=raw_context.get("idempotency_key")
                        if isinstance(raw_context.get("idempotency_key"), str)
                        else None,
                    )
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
