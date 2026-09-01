"""Transactional installation and rollback for supervised application services."""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.services.application_configuration import (
    ApplicationConfigurationError,
    resolve_application_configuration,
)
from three_mm_runtime.application_transport import (
    ApplicationServiceClient,
    ApplicationTransportError,
)


class ApplicationActivationError(RuntimeError):
    pass


class ApplicationSupervisor(Protocol):
    def is_enabled(self, instance_id: str) -> bool: ...

    def restart(self, instance_id: str) -> None: ...

    def stop(self, instance_id: str) -> None: ...


class SystemdApplicationSupervisor:
    def is_enabled(self, instance_id: str) -> bool:
        unit = f"3mm-application-extension@{instance_id}.service"
        try:
            result = subprocess.run(
                ["/usr/bin/systemctl", "is-enabled", "--quiet", unit],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ApplicationActivationError(
                "Application service state could not be read"
            ) from exc
        return result.returncode == 0

    def _run(self, arguments: list[str], instance_id: str) -> None:
        unit = f"3mm-application-extension@{instance_id}.service"
        try:
            subprocess.run(
                ["/usr/bin/systemctl", *arguments, unit],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ApplicationActivationError(
                "Application service lifecycle command failed"
            ) from exc

    def restart(self, instance_id: str) -> None:
        self._run(["enable"], instance_id)
        self._run(["restart"], instance_id)

    def stop(self, instance_id: str) -> None:
        self._run(["disable", "--now"], instance_id)


@dataclass(frozen=True, slots=True)
class ActivatedApplication:
    module_id: str
    version: str
    sha256: str
    instance_id: str
    socket_path: Path


def application_instance_id(module_id: str) -> str:
    return hashlib.sha256(module_id.encode("utf-8")).hexdigest()[:24]


def _validate_instance_id(instance_id: str) -> None:
    if len(instance_id) != 24 or any(
        character not in "0123456789abcdef" for character in instance_id
    ):
        raise ApplicationActivationError("Application instance identity is invalid")


def uninstall_application_instance(
    instance_id: str,
    *,
    root: Path = Path("/var/lib/3mm/application-extensions"),
    key_root: Path = Path("/etc/3mm/application-extensions"),
    supervisor: ApplicationSupervisor | None = None,
) -> None:
    """Remove one application runtime while preserving its mutable data."""
    _validate_instance_id(instance_id)

    selected_supervisor = supervisor or SystemdApplicationSupervisor()
    selected_supervisor.stop(instance_id)

    instance_root = root / instance_id
    (instance_root / "active.json").unlink(missing_ok=True)
    shutil.rmtree(instance_root / "releases", ignore_errors=True)
    shutil.rmtree(instance_root / "run", ignore_errors=True)
    for snapshot in instance_root.glob(".database-*.rollback"):
        snapshot.unlink(missing_ok=True)
    (key_root / f"{instance_id}.key").unlink(missing_ok=True)


def erase_application_instance_data(
    instance_id: str,
    *,
    root: Path = Path("/var/lib/3mm/application-extensions"),
    supervisor: ApplicationSupervisor | None = None,
) -> None:
    """Permanently erase preserved data for an already uninstalled application."""
    _validate_instance_id(instance_id)
    selected_supervisor = supervisor or SystemdApplicationSupervisor()
    instance_root = root / instance_id
    if selected_supervisor.is_enabled(instance_id) or (instance_root / "active.json").exists():
        raise ApplicationActivationError(
            "Application data cannot be erased while the service is installed"
        )
    shutil.rmtree(instance_root / "data", ignore_errors=True)
    try:
        instance_root.rmdir()
    except OSError:
        pass


def _write_atomic(path: Path, payload: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_bytes(payload)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _set_owner(path: Path, uid: int | None, gid: int | None) -> None:
    if uid is not None and gid is not None:
        os.chown(path, uid, gid)


def _prepare_directory(
    path: Path,
    *,
    uid: int | None,
    gid: int | None,
) -> None:
    """Create or repair a service directory independently of the process umask."""
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    os.chmod(path, 0o750)
    _set_owner(path, uid, gid)


def _snapshot_database(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    os.chmod(destination, 0o600)
    return True


def _restore_database(
    database: Path,
    snapshot: Path,
    existed: bool,
    service_uid: int | None,
    service_gid: int | None,
) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{database}{suffix}").unlink(missing_ok=True)
    if existed:
        source_connection = sqlite3.connect(snapshot)
        destination_connection = sqlite3.connect(database)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
        snapshot.unlink(missing_ok=True)
        os.chmod(database, 0o600)
        _set_owner(database, service_uid, service_gid)
    else:
        database.unlink(missing_ok=True)


def _wait_for_health(
    metadata: dict[str, object],
    secret: bytes,
    socket_path: Path,
    *,
    client_factory: Callable[..., ApplicationServiceClient],
    sleep: Callable[[float], None],
) -> None:
    last_error: Exception | None = None
    attempts = max(1, int(metadata["startup_timeout_seconds"]) * 5)
    for _attempt in range(attempts):
        try:
            result = client_factory(socket_path, secret, 2).invoke(
                str(metadata["health_operation_id"]),
                {},
                {
                    "audience": "internal",
                    "correlation_id": f"activation:{metadata['sha256']}",
                },
            )
            if result.get("status") not in {"ok", "ready"}:
                raise ApplicationTransportError(
                    "Application health operation did not report readiness"
                )
            return
        except (ApplicationTransportError, OSError) as exc:
            last_error = exc
            sleep(0.2)
    raise ApplicationActivationError(
        "Application extension did not become healthy"
    ) from last_error


def activate_application_package(
    package_path: Path,
    expected_sha256: str,
    *,
    configuration: dict[str, object] | None = None,
    root: Path = Path("/var/lib/3mm/application-extensions"),
    key_root: Path = Path("/etc/3mm/application-extensions"),
    supervisor: ApplicationSupervisor | None = None,
    service_uid: int | None = None,
    service_gid: int | None = None,
    client_factory: Callable[..., ApplicationServiceClient] = ApplicationServiceClient,
    sleep: Callable[[float], None] = time.sleep,
) -> ActivatedApplication:
    try:
        blob = package_path.read_bytes()
    except OSError as exc:
        raise ApplicationActivationError("Application package is unavailable") from exc
    if hashlib.sha256(blob).hexdigest() != expected_sha256:
        raise ApplicationActivationError("Application package checksum is invalid")
    try:
        validated = validate_module_package(blob)
    except ModulePackageError as exc:
        raise ApplicationActivationError(str(exc)) from exc
    definition = validated.application_extension
    if definition is None:
        raise ApplicationActivationError("Package is not an application extension")
    try:
        resolved_configuration = resolve_application_configuration(
            validated.manifest.configuration_schema,
            validated.manifest.configuration_defaults,
            definition,
            overrides=configuration,
        )
    except ApplicationConfigurationError as exc:
        raise ApplicationActivationError(str(exc)) from exc

    instance_id = application_instance_id(definition.module_id)
    instance_root = root / instance_id
    releases_root = instance_root / "releases"
    release_root = releases_root / validated.sha256
    data_root = instance_root / "data"
    run_root = instance_root / "run"
    socket_path = run_root / "service.sock"
    key_path = key_root / f"{instance_id}.key"
    _prepare_directory(instance_root, uid=0 if service_uid is not None else None, gid=service_gid)
    _prepare_directory(releases_root, uid=0 if service_uid is not None else None, gid=service_gid)
    _prepare_directory(release_root, uid=0 if service_uid is not None else None, gid=service_gid)
    _prepare_directory(data_root, uid=service_uid, gid=service_gid)
    _prepare_directory(run_root, uid=service_uid, gid=service_gid)
    _prepare_directory(key_root, uid=0 if service_uid is not None else None, gid=service_gid)

    wheel_path = release_root / "service.whl"
    if not wheel_path.exists():
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            wheel_payload = archive.read(definition.service.artifact)
        if hashlib.sha256(wheel_payload).hexdigest() != (
            definition.service.artifact_sha256
        ):
            raise ApplicationActivationError("Application wheel checksum is invalid")
        _write_atomic(wheel_path, wheel_payload, 0o440)

    if key_path.exists():
        secret = key_path.read_bytes()
        if len(secret) != 32:
            raise ApplicationActivationError("Application service key is invalid")
    else:
        secret = secrets.token_bytes(32)
        _write_atomic(key_path, secret, 0o640)

    # The service owns only its mutable instance/data directory. Reviewed code,
    # active metadata and the transport key remain root-owned and read-only.
    _set_owner(wheel_path, 0 if service_uid is not None else None, service_gid)
    _set_owner(key_path, 0 if service_uid is not None else None, service_gid)

    metadata = {
        "instance_id": instance_id,
        "module_id": definition.module_id,
        "version": definition.version,
        "sha256": validated.sha256,
        "wheel": "service.whl",
        "entrypoint": definition.service.entrypoint,
        "health_operation_id": definition.service.health_operation_id,
        "startup_timeout_seconds": definition.service.startup_timeout_seconds,
        "shutdown_timeout_seconds": definition.service.shutdown_timeout_seconds,
        "configuration": resolved_configuration,
        "platform_socket": str(root / "platform" / "platform.sock"),
        "storage": {
            "schema_revision": definition.storage.schema_revision,
            "migration_entrypoint": definition.storage.migration_entrypoint,
        },
        "operations": [
            {
                "operation_id": operation.operation_id,
                "audiences": list(operation.audiences),
                "idempotency": operation.idempotency,
            }
            for operation in definition.operations
        ],
    }
    active_path = instance_root / "active.json"
    previous = active_path.read_bytes() if active_path.exists() else None
    selected_supervisor = supervisor or SystemdApplicationSupervisor()
    previous_was_enabled = (
        selected_supervisor.is_enabled(instance_id) if previous is not None else False
    )
    database = data_root / "state.sqlite3"
    database_snapshot = instance_root / f".database-{validated.sha256}.rollback"
    database_snapshot.unlink(missing_ok=True)
    try:
        if previous_was_enabled:
            selected_supervisor.stop(instance_id)
        database_existed = _snapshot_database(database, database_snapshot)
    except Exception as exc:
        if previous_was_enabled:
            try:
                selected_supervisor.restart(instance_id)
            except Exception:
                pass
        database_snapshot.unlink(missing_ok=True)
        raise ApplicationActivationError(
            "Application data could not be staged for activation"
        ) from exc
    _write_atomic(
        active_path,
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        0o640,
    )
    _set_owner(active_path, 0 if service_uid is not None else None, service_gid)
    try:
        selected_supervisor.restart(instance_id)
        _wait_for_health(
            metadata,
            secret,
            socket_path,
            client_factory=client_factory,
            sleep=sleep,
        )
    except Exception as exc:
        try:
            selected_supervisor.stop(instance_id)
            _restore_database(
                database,
                database_snapshot,
                database_existed,
                service_uid,
                service_gid,
            )
            if previous is None:
                active_path.unlink(missing_ok=True)
            else:
                _write_atomic(active_path, previous, 0o640)
                _set_owner(
                    active_path,
                    0 if service_uid is not None else None,
                    service_gid,
                )
                if previous_was_enabled:
                    selected_supervisor.restart(instance_id)
                else:
                    selected_supervisor.stop(instance_id)
        except Exception:
            pass
        raise ApplicationActivationError(
            "Application activation failed; the previous version was restored"
        ) from exc
    finally:
        database_snapshot.unlink(missing_ok=True)
    return ActivatedApplication(
        module_id=definition.module_id,
        version=definition.version,
        sha256=validated.sha256,
        instance_id=instance_id,
        socket_path=socket_path,
    )
