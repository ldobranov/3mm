#!/usr/bin/env python3
"""Build deterministic, architecture-specific 3mm release archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # Both module imports and the workflow's direct script invocation.
    from .deployment_contract import (
        CONTRACT_PATH,
        DeploymentContractError,
        validate_deployment_contract, validate_platform_runtime_contract,
    )
except ImportError:
    from deployment_contract import (
        CONTRACT_PATH,
        DeploymentContractError,
        validate_deployment_contract, validate_platform_runtime_contract,
    )

from deployment.armv6_ui_tools import FILES as ARMV6_FILES, TOOLS_PATH, artifact_inputs

SUPPORTED_ARCHITECTURES = ("aarch64", "armv7l", "x86_64", "armv6l")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9+.:~-]*$")
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


class ReleaseBuildError(RuntimeError):
    """Raised when release inputs cannot produce a trusted artifact."""


@dataclass(frozen=True)
class PayloadFile:
    name: str
    data: bytes
    mode: int


def _safe_path(name: str) -> str:
    normalized = name.rstrip("/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or name.startswith("/")
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ReleaseBuildError(f"Unsafe archive path: {name}")
    return path.as_posix()


def _read_member(source: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    if member.size > MAX_MEMBER_BYTES:
        raise ReleaseBuildError(f"Archive member is too large: {member.name}")
    extracted = source.extractfile(member)
    if extracted is None:
        raise ReleaseBuildError(f"Archive member cannot be read: {member.name}")
    data = extracted.read(MAX_MEMBER_BYTES + 1)
    if len(data) != member.size or len(data) > MAX_MEMBER_BYTES:
        raise ReleaseBuildError(f"Archive member size is invalid: {member.name}")
    return data


def read_source_payload(source_archive: Path) -> list[PayloadFile]:
    if not source_archive.is_file():
        raise ReleaseBuildError(f"Source archive does not exist: {source_archive}")

    payload: list[PayloadFile] = []
    names: set[str] = set()
    total_size = 0
    try:
        with tarfile.open(source_archive, mode="r:") as source:
            for member in source.getmembers():
                name = _safe_path(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ReleaseBuildError(
                        f"Unsupported source archive entry: {member.name}"
                    )
                if name == ".3mm-release.json" or name.startswith("frontend/dist/"):
                    continue
                if name in names:
                    raise ReleaseBuildError(f"Duplicate source archive path: {name}")
                data = _read_member(source, member)
                total_size += len(data)
                if total_size > MAX_TOTAL_BYTES:
                    raise ReleaseBuildError("Source archive payload is too large")
                names.add(name)
                payload.append(
                    PayloadFile(
                        name=name,
                        data=data,
                        mode=0o755 if member.mode & 0o111 else 0o644,
                    )
                )
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseBuildError("Source archive is invalid") from exc

    # Product sources and optional libraries can stay in the repository without
    # becoming executable Core release contents. Markers are allowed only in an
    # individual module/library, never at a required runtime directory or root.
    source_only = set()
    for item in payload:
        if PurePosixPath(item.name).name != ".3mm-source-only":
            continue
        parts = PurePosixPath(item.name).parts
        if len(parts) != 3 or parts[0] not in {"modules", "libraries"} or item.data:
            raise ReleaseBuildError("Source-only marker must be empty and belong to a module/library")
        source_only.add("/".join(parts[:2]) + "/")
    payload = [item for item in payload if not any(item.name.startswith(prefix) for prefix in source_only)]
    names = {item.name for item in payload}

    required = {
        CONTRACT_PATH,
        "deployment/deployment_contract.py",
        "VERSION",
        "install.sh",
        "backend/requirements.txt",
        "backend/applications/commands/__init__.py",
        "backend/applications/commands/broker.py",
        "backend/applications/commands/discovery.py",
        "backend/applications/commands/passage.py",
        "backend/applications/commands/rebinding.py",
        "backend/applications/connectors/__init__.py",
        "backend/applications/connectors/broker.py",
        "backend/applications/connectors/secrets.py",
        "backend/applications/connectors/transport.py",
        "backend/applications/events/__init__.py",
        "backend/applications/events/api.py",
        "backend/applications/events/broker.py",
        "backend/applications/events/publication.py",
        "backend/applications/operations_api.py",
        "backend/applications/resources/__init__.py",
        "backend/applications/resources/providers.py",
        "backend/applications/runtime/__init__.py",
        "backend/applications/runtime/gateway.py",
        "backend/applications/runtime/health.py",
        "backend/applications/runtime/identity.py",
        "backend/applications/runtime/invocations.py",
        "backend/applications/runtime/peers.py",
        "backend/applications/runtime/platform.py",
        "backend/applications/runtime/responses.py",
        "backend/applications/runtime/status.py",
        "backend/applications/runtime/status_probe.py",
        "backend/applications/sessions/__init__.py",
        "backend/applications/sessions/api.py",
        "backend/applications/sessions/authority.py",
        "backend/applications/sessions/browser.py",
        "backend/applications/sessions/local.py",
        "backend/applications/sessions/remote.py",
        "backend/applications/sessions/runtimes.py",
        "backend/applications/tasks/__init__.py",
        "backend/applications/tasks/api.py",
        "backend/applications/tasks/broker.py",
        "backend/applications/tasks/schedules.py",
        "backend/sessions/__init__.py",
        "backend/sessions/acceptance.py",
        "backend/sessions/agent.py",
        "backend/sessions/api.py",
        "backend/sessions/broker.py",
        "backend/sessions/discovery.py",
        "backend/sessions/gateway.py",
        "backend/sessions/transport.py",
        "backend/applications/relational/__init__.py",
        "backend/applications/relational/activation.py",
        "backend/applications/relational/activation_recovery.py",
        "backend/applications/relational/admin_worker.py",
        "backend/applications/relational/authority.py",
        "backend/applications/relational/boot.py",
        "backend/applications/relational/candidate.py",
        "backend/applications/relational/lifecycle.py",
        "backend/applications/relational/namespace_recovery.py",
        "backend/applications/relational/preparation_recovery.py",
        "backend/applications/relational/reactivation.py",
        "backend/applications/relational/recovery.py",
        "backend/applications/relational/recovery_confirmation.py",
        "backend/applications/relational/registration.py",
        "backend/applications/relational/startup.py",
        "backend/applications/relational/upgrade.py",
        "backend/applications/relational/upgrade_admin.py",
        "backend/applications/relational/upgrade_cli.py",
        "backend/applications/relational/upgrade_confirmation.py",
        "backend/applications/relational/upgrade_rollback.py",
        "backend/devices/pairing/__init__.py",
        "backend/devices/pairing/api.py",
        "backend/devices/pairing/enrollment.py",
        "backend/devices/pairing/service.py",
        "backend/devices/platform/__init__.py",
        "backend/devices/platform/api.py",
        "backend/devices/platform/service.py",
        "backend/devices/updates/__init__.py",
        "backend/devices/updates/api.py",
        "backend/devices/updates/approval.py",
        "backend/devices/updates/catalog.py",
        "backend/devices/updates/delivery.py",
        "backend/devices/updates/delivery_api.py",
        "backend/devices/updates/execution.py",
        "backend/settings/__init__.py",
        "backend/settings/api.py",
        "backend/settings/crud.py",
        "backend/system/audit/__init__.py",
        "backend/system/audit/api.py",
        "backend/system/audit/retention.py",
        "backend/accounts/bootstrap.py",
        "backend/applications/authority/__init__.py",
        "backend/applications/authority/access.py",
        "backend/applications/authority/admin.py",
        "backend/applications/authority/composition.py",
        "backend/applications/authority/context.py",
        "backend/applications/authority/inspection.py",
        "backend/applications/authority/keys.py",
        "backend/applications/authority/management.py",
        "backend/applications/authority/metadata.py",
        "backend/applications/authority/policy.py",
        "backend/applications/authority/policy_reviews.py",
        "backend/applications/authority/review.py",
        "backend/applications/authority/sources.py",
        "backend/applications/authority/subjects.py",
        "backend/applications/authority/tasks.py",
        "backend/devices/modules/template_data/character-display.mock.json",
        "backend/devices/modules/template_data/character-display.pcf8574-2row.json",
        "backend/devices/modules/template_data/character-display.pcf8574-4row.json",
        "backend/devices/modules/template_data/gpio-input.gpiod.json",
        "backend/devices/modules/template_data/gpio-input.mock.json",
        "backend/devices/modules/templates.py",
        "backend/devices/telemetry/__init__.py",
        "backend/devices/telemetry/events_api.py",
        "backend/devices/telemetry/ingest_api.py",
        "backend/devices/telemetry/state_api.py",
        "backend/installation/__init__.py",
        "backend/installation/api.py",
        "backend/installation/identity.py",
        "backend/installation/peer_listing.py",
        "backend/installation/peer_read_sources.py",
        "backend/installation/peers.py",
        "backend/installation/projection.py",
        "backend/installation/session_tls.py",
        "backend/installation/status_binding.py",
        "backend/localization/service.py",
        "backend/storage/__init__.py",
        "backend/storage/engine.py",
        "backend/storage/public_assets.py",
        "backend/storage/sessions.py",
        "backend/system/components.py",
        "backend/artifacts/__init__.py",
        "backend/artifacts/api.py",
        "backend/artifacts/packages.py",
        "backend/artifacts/inspection.py",
        "backend/artifacts/code_scope.py",
        "backend/artifacts/compiled_ui.py",
        "backend/artifacts/provenance.py",
        "backend/appearance/__init__.py",
        "backend/appearance/api.py",
        "backend/appearance/packages.py",
        "backend/appearance/customization.py",
        "backend/appearance/assets.py",
        "backend/accounts/__init__.py",
        "backend/accounts/passwords.py",
        "backend/accounts/tokens.py",
        "backend/accounts/dependencies.py",
        "backend/accounts/users_api.py",
        "backend/accounts/access/__init__.py",
        "backend/accounts/access/api.py",
        "backend/accounts/access/sources.py",
        "backend/accounts/access/groups_api.py",
        "backend/accounts/access/roles_api.py",
        "backend/accounts/access/permissions_api.py",
        "backend/accounts/sessions/__init__.py",
        "backend/accounts/sessions/api.py",
        "backend/accounts/sessions/refresh.py",
        "backend/accounts/sessions/policy.py",
        "backend/alembic/versions/4f29a071b819_application_result_tasks.py",
        "backend/alembic/versions/5a30b182c920_application_task_schedules.py",
        "backend/alembic/versions/6b41c293da31_retire_builder_automations.py",
        "backend/alembic/versions/7c52d3a4eb42_retire_dashboards.py",
        "backend/alembic/versions/8d63e4b5fc53_retire_declarative_crud.py",
        "packages/protocol/ui_metadata.py",
        "backend/alembic/versions/9e74f5c60d64_retire_legacy_content.py",
        "backend/alembic/versions/af85a6d71e75_user_subject_ids.py",
        "backend/alembic/versions/b096b7e82f86_kiosk_incarnations.py",
        "backend/db/language_extension.py",
        "backend/db/menu.py",
        "backend/db/module_reference.py",
        "backend/system/updates/__init__.py",
        "backend/system/updates/api.py",
        "backend/system/updates/releases.py",
        "backend/system/updates/policy.py",
        "backend/system/updates/staging.py",
        "backend/system/updates/platform_runtime.py",
        "backend/system/updates/components_api.py",
        "backend/system/updates/components.py",
        "backend/applications/checkpoints.py",
        "backend/applications/delegations/__init__.py",
        "backend/applications/delegations/api.py",
        "backend/applications/delegations/service.py",
        "backend/applications/files/__init__.py",
        "backend/applications/files/api.py",
        "backend/applications/files/authority.py",
        "backend/applications/files/transfers.py",
        "backend/applications/kiosks/__init__.py",
        "backend/applications/kiosks/api.py",
        "backend/applications/kiosks/service.py",
        "backend/applications/public_web/__init__.py",
        "backend/applications/public_web/guests.py",
        "backend/applications/public_web/webhook_admission.py",
        "backend/applications/queries/__init__.py",
        "backend/applications/queries/configuration.py",
        "backend/applications/queries/transport.py",
        "backend/applications/public_web/routes.py",
        "backend/applications/public_web/transport.py",
        "backend/devices/__init__.py",
        "backend/devices/operations.py",
        "backend/devices/authority.py",
        "backend/devices/auth.py",
        "backend/devices/http.py",
        "backend/devices/body_limit.py",
        "backend/devices/commands/__init__.py",
        "backend/devices/commands/api.py",
        "backend/devices/commands/queue.py",
        "backend/devices/commands/notifier.py",
        "backend/devices/capabilities/__init__.py",
        "backend/devices/capabilities/api.py",
        "backend/devices/capabilities/state_api.py",
        "backend/devices/capabilities/registry.py",
        "backend/devices/hardware_interfaces.py",
        "backend/devices/features/__init__.py",
        "backend/devices/features/api.py",
        "backend/devices/features/service.py",
        "backend/devices/modules/__init__.py",
        "backend/devices/modules/lifecycle.py",
        "backend/devices/modules/authority.py",
        "backend/devices/registry/__init__.py",
        "backend/devices/registry/api.py",
        "backend/devices/registry/read.py",
        "backend/devices/registry/online.py",
        "backend/localization/__init__.py",
        "backend/localization/api.py",
        "backend/localization/packages.py",
        "backend/system/__init__.py",
        "backend/system/backups/__init__.py",
        "backend/system/backups/api.py",
        "backend/system/backups/service.py",
        "backend/system/control.py",
        "backend/system/diagnostics/__init__.py",
        "backend/system/diagnostics/api.py",
        "backend/system/diagnostics/failures.py",
        "backend/system/diagnostics/operations.py",
        "backend/system/diagnostics/workspace.py",
        "backend/system/diagnostics/bundle.py",
        "backend/system/diagnostics/alerts.py",
        "backend/system/network_recovery/__init__.py",
        "backend/system/network_recovery/api.py",
        "backend/system/network_recovery/service.py",
        "components/__init__.py",
        "components/admin_web/__init__.py",
        "components/admin_web/__main__.py",
        "components/admin_web/server.py",
        "components/system_runtime/__init__.py",
        "components/system_runtime/activate.py",
        "components/system_runtime/install_profile.py",
        "components/system_runtime/services.py",
        "components/system_runtime/host_session_policy.py",
        "components/system_runtime/host_session_worker.py",
        "config_templates/product.json",
        "components/setup/__init__.py",
        "components/setup/__main__.py",
        "components/setup/captive_portal.py",
        "components/setup/cli.py",
        "components/setup/config.py",
        "components/setup/main.py",
        "components/setup/product.py",
        "components/setup/provision.py",
        "components/setup/schemas.py",
        "components/setup/requirements.txt",
        "components/setup/static/setup.html",
        "deployment/apply_staged_update.py",
        "deployment/bootstrap-local-agent.py",
        "deployment/component_transition.py",
        "deployment/factory_reset.py",
        "deployment/local_agent_pairing.py",
        "deployment/restore_application_extensions.py",
        "deployment/authority_recovery.py",
        "deployment/install-systemd.sh",
        "deployment/migrate_database.py",
        "deployment/prepare_host_sessions.py",
        "deployment/update-dependency-allowlist.json",
        "deployment/systemd/3mm-agent.service",
        "deployment/systemd/3mm-setup-local.service",
        "deployment/systemd/3mm-application-extension@.service",
        "deployment/systemd/3mm-core.service",
        "deployment/systemd/3mm-host-session-worker.socket",
        "deployment/systemd/3mm-host-session-worker@.service",
        "deployment/systemd/3mm-update-helper.service",
        "deployment/systemd/3mm-web.service",
        "deployment/systemd/3mm-public-web.socket",
        "deployment/systemd/3mm-public-web.service",
        "frontend/compiler/package.json",
        "components/system_runtime/update_helper.py",
        'components/system_runtime/platform_runtime_updates.py',
        "components/system_runtime/application_activation.py",
        "components/system_runtime/application_host.py",
        "components/system_runtime/application_host_identity.py",
        "deployment/application_host_component.py",
        "deployment/application-host-contract.json",
        "deployment/application-host-requirements.txt",
        "components/system_runtime/application_transport.py",
        "components/public_web/__init__.py",
        "components/public_web/__main__.py",
        "components/public_web/server.py",
        "components/public_web/webhook_pilot.py",
        "packages/application_sdk/__init__.py",
        "packages/application_sdk/discovery.py",
        "packages/protocol/application_requirements.py",
        "backend/applications/__init__.py",
        "backend/applications/management/__init__.py",
        "backend/applications/management/configuration.py",
        "backend/applications/management/requirements.py",
        "backend/applications/management/staging.py",
        "backend/applications/management/provenance.py",
        "backend/applications/management/api.py",
        "backend/applications/management/access_api.py",
        "backend/applications/management/connector_api.py",
        "backend/applications/management/ui_admin_api.py",
        "backend/applications/management/lifecycle.py",
        "backend/applications/management/consent.py",
        "backend/applications/management/lifecycle_consent.py",
        "backend/applications/management/connector_settings.py",
        "backend/applications/resources/discovery.py",
        "packages/protocol/application_resources.py",
        'deployment/platform-runtime-contract.json',
        'deployment/platform_runtime_component.py',
        'deployment/systemd/3mm-platform-runtime.service',
        'packages/__init__.py',
        'packages/platform_wire/__init__.py',
        'packages/platform_wire/event_delivery.py',
        'packages/platform_wire/task_time.py',
        'packages/protocol/__init__.py',
        'packages/protocol/theme_design_defaults.json',
        'packages/provisioning/__init__.py',
        'packages/provisioning/network_recovery.py',
        'components/platform_runtime/__init__.py',
        'components/platform_runtime/__main__.py',
        'components/platform_runtime/server.py',
        'components/platform_runtime/public_web.py',
        'components/platform_runtime/events.py',
        'components/platform_runtime/responses.py',
        'components/platform_runtime/connector_worker.py',
        'components/platform_runtime/connector_execute.py',
        'components/platform_runtime/tasks.py',
        'deployment/systemd/3mm-connector-worker.service',
    }
    missing = sorted(required - names)
    if missing:
        raise ReleaseBuildError(
            f"Source archive is missing required files: {', '.join(missing)}"
        )
    try:
        validate_platform_runtime_contract(next(item.data for item in payload if item.name=="deployment/platform-runtime-contract.json"))
    except DeploymentContractError as error:
        raise ReleaseBuildError(str(error)) from error
    from deployment.application_host_component import validate_host_contract
    try:
        validate_host_contract(next(item.data for item in payload if item.name=="deployment/application-host-contract.json"))
    except (ValueError,TypeError,AttributeError) as error:
        raise ReleaseBuildError("Core/application-host contracts are unsupported") from error
    return sorted(payload, key=lambda item: item.name)


def read_frontend_payload(frontend_dist: Path) -> list[PayloadFile]:
    if not frontend_dist.is_dir():
        raise ReleaseBuildError(f"Frontend dist does not exist: {frontend_dist}")
    index_file = frontend_dist / "index.html"
    asset_files = sorted((frontend_dist / "assets").glob("*.js"))
    if not index_file.is_file() or not asset_files:
        raise ReleaseBuildError(
            "Frontend dist requires index.html and at least one assets/*.js file"
        )

    entries = sorted(frontend_dist.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ReleaseBuildError("Frontend dist must not contain symbolic links")

    payload: list[PayloadFile] = []
    total_size = 0
    for file_path in (path for path in entries if path.is_file()):
        relative = file_path.relative_to(frontend_dist).as_posix()
        name = _safe_path(f"frontend/dist/{relative}")
        size = file_path.stat().st_size
        if size > MAX_MEMBER_BYTES:
            raise ReleaseBuildError(f"Frontend file is too large: {relative}")
        data = file_path.read_bytes()
        total_size += len(data)
        if total_size > MAX_TOTAL_BYTES:
            raise ReleaseBuildError("Frontend payload is too large")
        payload.append(PayloadFile(name=name, data=data, mode=0o644))
    return payload


def read_dependencies(dependencies_file: Path) -> list[str]:
    try:
        payload = json.loads(dependencies_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError("Release dependencies file is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "apt_packages",
    }:
        raise ReleaseBuildError("Release dependencies file has unsupported fields")
    packages = payload.get("apt_packages")
    if payload.get("schema_version") != 1 or not isinstance(packages, list):
        raise ReleaseBuildError("Release dependencies file is invalid")
    if (
        len(packages) > 100
        or any(not isinstance(item, str) for item in packages)
        or len(packages) != len(set(packages))
        or packages != sorted(packages)
        or any(not PACKAGE_PATTERN.fullmatch(item) for item in packages)
    ):
        raise ReleaseBuildError(
            "APT dependencies must be unique, sorted, valid package names"
        )
    return packages


def _write_file(archive: tarfile.TarFile, payload: PayloadFile, epoch: int) -> None:
    info = tarfile.TarInfo(payload.name)
    info.size = len(payload.data)
    info.mode = payload.mode
    info.mtime = epoch
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    with tempfile.SpooledTemporaryFile(max_size=MAX_MEMBER_BYTES) as source:
        source.write(payload.data)
        source.seek(0)
        archive.addfile(info, source)


def write_release_archive(
    output_file: Path,
    payload: Iterable[PayloadFile],
    metadata: dict[str, object],
    *,
    epoch: int,
) -> tuple[str, int]:
    metadata_bytes = (
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    files = list(payload) + [
        PayloadFile(name=".3mm-release.json", data=metadata_bytes, mode=0o644)
    ]
    names = [item.name for item in files]
    if len(names) != len(set(names)):
        raise ReleaseBuildError("Release payload contains duplicate paths")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_suffix(output_file.suffix + ".tmp")
    try:
        with temporary.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_output, mtime=epoch
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
                ) as archive:
                    for item in sorted(files, key=lambda entry: entry.name):
                        _write_file(archive, item, epoch)
        os.replace(temporary, output_file)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ReleaseBuildError(
            f"Could not write release archive: {output_file}"
        ) from exc

    digest = hashlib.sha256(output_file.read_bytes()).hexdigest()
    return digest, output_file.stat().st_size


def build_release_assets(
    *,
    source_archive: Path,
    frontend_dist: Path,
    dependencies_file: Path,
    output_dir: Path,
    repository: str,
    version: str,
    tag: str,
    commit: str,
    branch: str,
    channel: str,
    architectures: Iterable[str],
    source_date_epoch: int,
    armv6_ui_tools: Path | None = None,
) -> dict[str, object]:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ReleaseBuildError("Repository must use the owner/name format")
    if not SEMVER_PATTERN.fullmatch(version) or tag != f"v{version}":
        raise ReleaseBuildError("Tag must be v followed by the manifest version")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ReleaseBuildError("Commit must be 40 lowercase hexadecimal characters")
    if not BRANCH_PATTERN.fullmatch(branch) or ".." in branch:
        raise ReleaseBuildError("Branch name is invalid")
    if channel not in {"stable", "beta", "test"}:
        raise ReleaseBuildError("Release channel is invalid")
    if source_date_epoch <= 0:
        raise ReleaseBuildError("SOURCE_DATE_EPOCH must be positive")

    selected_architectures = list(architectures)
    if (
        not selected_architectures
        or len(selected_architectures) != len(set(selected_architectures))
        or any(item not in SUPPORTED_ARCHITECTURES for item in selected_architectures)
    ):
        raise ReleaseBuildError("Release architectures are invalid or duplicated")

    source_payload = read_source_payload(source_archive)
    if any(item.name.startswith(TOOLS_PATH + "/") for item in source_payload):
        raise ReleaseBuildError("ARMv6 compiler artifacts must be supplied separately")
    if ("armv6l" in selected_architectures) != (armv6_ui_tools is not None):
        raise ReleaseBuildError("ARMv6 releases require separate ARMv6 compiler artifacts")
    armv6_payload = []
    if armv6_ui_tools is not None:
        try:
            armv6_payload = [
                PayloadFile(f"{TOOLS_PATH}/{name}", data, 0o755 if name == "esbuild" else 0o644)
                for name, data in zip(ARMV6_FILES, artifact_inputs(armv6_ui_tools), strict=True)
            ]
        except (OSError, ValueError) as exc:
            raise ReleaseBuildError(str(exc)) from exc
    version_file = next(item for item in source_payload if item.name == "VERSION")
    try:
        source_version = version_file.data.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ReleaseBuildError("Source VERSION file must contain ASCII text") from exc
    if source_version != version:
        raise ReleaseBuildError(
            f"Source VERSION {source_version!r} does not match release {version!r}"
        )
    frontend_payload = read_frontend_payload(frontend_dist)
    payload = source_payload + frontend_payload
    contract_file = next(item for item in source_payload if item.name == CONTRACT_PATH)
    try:
        validate_deployment_contract(
            contract_file.data,
            {item.name for item in payload} | {".3mm-release.json"},
        )
    except DeploymentContractError as exc:
        raise ReleaseBuildError(str(exc)) from exc
    packages = read_dependencies(dependencies_file)
    created_at = datetime.fromtimestamp(source_date_epoch, tz=UTC).isoformat()

    artifacts: list[dict[str, object]] = []
    for architecture in selected_architectures:
        filename = f"3mm-{version}-{architecture}.tar.gz"
        metadata = {
            "architecture": architecture,
            "branch": branch,
            "commit": commit,
            "created_at": created_at,
            "includes_working_tree": False,
            "release_id": tag,
            "version": version,
        }
        sha256, size_bytes = write_release_archive(
            output_dir / filename,
            payload + (armv6_payload if architecture == "armv6l" else []),
            metadata,
            epoch=source_date_epoch,
        )
        artifacts.append(
            {
                "architecture": architecture,
                "filename": filename,
                "download_url": (
                    f"https://github.com/{repository}/releases/download/{tag}/{filename}"
                ),
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
        )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "version": version,
        "release_id": tag,
        "commit": commit,
        "channel": channel,
        "artifacts": [],
        "dependencies": {"apt_packages": packages},
    }
    # Installed Core releases validate every entry in the original manifest.
    # Keep the ARMv6 Hub catalog separate so adding it does not break their OTA.
    manifests = []
    for filename, armv6 in (("3mm-update-manifest.json", False), ("3mm-armv6-update-manifest.json", True)):
        matching = [item for item in artifacts if (item["architecture"] == "armv6l") == armv6]
        if not matching:
            continue
        result = {**manifest, "artifacts": matching}
        (output_dir / filename).write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        manifests.append(result)
    return manifests[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path, required=True)
    parser.add_argument("--frontend-dist", type=Path, required=True)
    parser.add_argument("--dependencies-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument(
        "--channel", choices=("stable", "beta", "test"), default="stable"
    )
    parser.add_argument(
        "--architecture",
        action="append",
        dest="architectures",
        choices=SUPPORTED_ARCHITECTURES,
        required=True,
    )
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--armv6-ui-tools", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_release_assets(
            source_archive=args.source_archive,
            frontend_dist=args.frontend_dist,
            dependencies_file=args.dependencies_file,
            output_dir=args.output_dir,
            repository=args.repository,
            version=args.version,
            tag=args.tag,
            commit=args.commit,
            branch=args.branch,
            channel=args.channel,
            architectures=args.architectures,
            source_date_epoch=args.source_date_epoch,
            armv6_ui_tools=args.armv6_ui_tools,
        )
    except ReleaseBuildError as exc:
        raise SystemExit(f"Release build failed: {exc}") from exc
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
