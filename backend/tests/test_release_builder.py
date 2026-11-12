from __future__ import annotations

import io
import json
import os
import shlex
import socket
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from backend.system.updates.releases import UpdateManifest, read_current_release
from backend.system.updates.staging import read_dependency_allowlist
from deployment.build_release import (
    ReleaseBuildError,
    build_release_assets,
    read_dependencies,
    read_source_payload,
)
from deployment.deployment_contract import (
    CONTRACT_PATH,
    DeploymentContractError,
    validate_deployment_contract,
)

COMMIT = "a" * 40
EPOCH = 1_787_728_000
ADMIN_WEB_FILES = (
    "components/__init__.py",
    "components/admin_web/__init__.py",
    "components/admin_web/__main__.py",
    "components/admin_web/server.py",
    "components/setup/__init__.py",
    "components/setup/captive_portal.py",
)
SETUP_FILES = tuple("components/setup/" + name + ".py" for name in
    ("__init__", "__main__", "captive_portal", "cli", "config", "main", "product", "provision", "schemas")) + (
    "components/setup/requirements.txt", "components/setup/static/setup.html")
PUBLIC_WEB_FILES = (
    "components/public_web/__init__.py",
    "components/public_web/__main__.py",
    "components/public_web/server.py",
    "components/public_web/webhook_pilot.py",
)
NETWORK_RECOVERY_FILES = (
    "backend/system/__init__.py",
    "backend/system/network_recovery/__init__.py",
    "backend/system/network_recovery/api.py",
    "backend/system/network_recovery/service.py",
)
DEVICE_HARDWARE_FILES = (
    "backend/devices/__init__.py",
    "backend/devices/hardware_interfaces.py",
)
DEVICE_REGISTRY_FILES = tuple("backend/devices/registry/" + name + ".py"
                              for name in ("__init__", "api", "read", "online"))
DEVICE_FEATURE_FILES = tuple("backend/devices/features/" + name + ".py"
                             for name in ("__init__", "api", "service"))
DEVICE_MODULE_FILES = tuple("backend/devices/modules/" + name + ".py"
                            for name in ("__init__", "lifecycle", "authority"))
DEVICE_OPERATIONS_FILES = tuple("backend/devices/" + name + ".py" for name in
    ("operations", "authority", "auth", "http", "body_limit")) + tuple(
    "backend/devices/commands/" + name + ".py" for name in ("__init__", "api", "queue", "notifier")) + tuple(
    "backend/devices/capabilities/" + name + ".py" for name in ("__init__", "api", "state_api", "registry"))
LOCALIZATION_FILES = tuple("backend/localization/" + name + ".py"
                           for name in ("__init__", "api", "packages"))
APPLICATION_MANAGEMENT_FILES = ("backend/applications/__init__.py",) + tuple(
    "backend/applications/management/" + name + ".py" for name in
    ("__init__", "configuration", "requirements", "staging", "provenance",
     "api", "access_api", "connector_api", "ui_admin_api", "lifecycle", "consent",
     "lifecycle_consent", "connector_settings"))
ARTIFACT_FILES = tuple("backend/artifacts/" + name + ".py" for name in
    ("__init__", "api", "packages", "inspection", "code_scope", "compiled_ui", "provenance"))
APPEARANCE_FILES = tuple("backend/appearance/" + name + ".py" for name in
    ("__init__", "api", "packages", "customization", "assets"))
ACCOUNT_SESSION_FILES = ("backend/accounts/__init__.py",) + tuple(
    "backend/accounts/sessions/" + name + ".py" for name in ("__init__", "api", "refresh", "policy"))
ACCOUNT_ACCESS_FILES = tuple("backend/accounts/" + name + ".py" for name in
    ("passwords", "tokens", "dependencies", "users_api")) + tuple(
    "backend/accounts/access/" + name + ".py" for name in
    ("__init__", "api", "sources", "groups_api", "roles_api", "permissions_api"))
APPLICATION_AUTHORITY_FILES = tuple("backend/applications/authority/" + name + ".py" for name in
    ("__init__", "access", "context", "policy", "subjects", "keys", "review", "sources",
     "management", "inspection", "admin", "metadata", "policy_reviews", "tasks", "composition"))
APPLICATION_RUNTIME_FILES = tuple("backend/applications/runtime/" + name + ".py" for name in
    ("__init__", "gateway", "platform", "invocations", "responses", "health", "identity", "status", "peers", "status_probe"))
APPLICATION_RESOURCE_FILES = tuple("backend/applications/resources/" + name + ".py" for name in
    ("__init__", "discovery", "providers")) + tuple(
    "backend/applications/commands/" + name + ".py" for name in ("__init__", "broker", "discovery", "rebinding", "passage")) + tuple(
    "backend/applications/connectors/" + name + ".py" for name in ("__init__", "broker", "transport", "secrets")) + tuple(
    "backend/applications/events/" + name + ".py" for name in ("__init__", "broker", "publication", "api")) + tuple(
    "backend/applications/tasks/" + name + ".py" for name in ("__init__", "broker", "schedules", "api")) + (
    "backend/applications/operations_api.py",)
INTERACTIVE_SESSION_FILES = tuple("backend/sessions/" + name + ".py" for name in
    ("__init__", "broker", "transport", "gateway", "agent", "discovery", "acceptance", "api")) + tuple(
    "backend/applications/sessions/" + name + ".py" for name in
    ("__init__", "browser", "local", "remote", "authority", "runtimes", "api"))
APPLICATION_CONTENT_FILES = tuple("backend/applications/files/" + name + ".py" for name in
    ("__init__", "authority", "transfers", "api")) + tuple(
    "backend/applications/public_web/" + name + ".py" for name in
    ("__init__", "routes", "transport", "guests", "webhook_admission")) + tuple(
    "backend/applications/delegations/" + name + ".py" for name in ("__init__", "service", "api")) + tuple(
    "backend/applications/kiosks/" + name + ".py" for name in ("__init__", "service", "api")) + tuple(
    "backend/applications/queries/" + name + ".py" for name in ("__init__", "configuration", "transport")) + (
    "backend/applications/checkpoints.py",)
INSTALLATION_FILES = tuple("backend/installation/" + name + ".py" for name in
    ("__init__", "identity", "session_tls", "status_binding", "projection", "peer_read_sources",
     "peer_listing", "peers", "api"))
DEVICE_TELEMETRY_FILES = tuple("backend/devices/telemetry/" + name + ".py" for name in
    ("__init__", "ingest_api", "events_api", "state_api"))
DEVICE_ADMINISTRATION_FILES = tuple("backend/devices/pairing/" + name + ".py" for name in
    ("__init__", "api", "service", "enrollment")) + tuple(
    "backend/devices/platform/" + name + ".py" for name in ("__init__", "api", "service")) + tuple(
    "backend/devices/updates/" + name + ".py" for name in
    ("__init__", "api", "delivery_api", "catalog", "approval", "delivery", "execution"))
SETTINGS_AUDIT_FILES = tuple("backend/settings/" + name + ".py" for name in
    ("__init__", "api", "crud")) + tuple(
    "backend/system/audit/" + name + ".py" for name in ("__init__", "api", "retention"))
PROVIDER_TEMPLATE_FILES = ("backend/devices/modules/templates.py",) + tuple(
    "backend/devices/modules/template_data/" + name + ".json" for name in
    ("character-display.mock", "character-display.pcf8574-2row", "character-display.pcf8574-4row",
     "gpio-input.gpiod", "gpio-input.mock"))
STORAGE_FILES = tuple("backend/storage/" + name + ".py" for name in
    ("__init__", "engine", "sessions", "public_assets")) + (
    "backend/system/components.py", "backend/accounts/bootstrap.py", "backend/localization/service.py")
DIAGNOSTIC_FILES = tuple("backend/system/diagnostics/" + name + ".py"
                         for name in ("__init__", "api", "failures", "operations", "workspace", "bundle", "alerts"))
PRODUCT_FILES = (
    "config_templates/product.json",
    "components/setup/product.py",
)
RUNTIME_ACTIVATION_FILES = tuple(
    "components/system_runtime/" + name + ".py"
    for name in ("activate", "services", "install_profile")
)
PLATFORM_WIRE_FILES = (
    "packages/__init__.py",
    "packages/platform_wire/__init__.py",
    "packages/platform_wire/event_delivery.py",
    "packages/platform_wire/task_time.py",
)
PROVISIONING_FILES = ("packages/provisioning/__init__.py", "packages/provisioning/network_recovery.py")
SYSTEM_UPDATE_FILES = tuple("backend/system/updates/" + name + ".py" for name in (
    "__init__", "api", "releases", "policy", "staging", "platform_runtime", "components_api", "components"))
BACKUP_FILES = tuple("backend/system/backups/" + name + ".py"
                     for name in ("__init__", "api", "service"))
REQUIRED_SOURCE_FILES = {
    "config_templates/product.json": Path("config_templates/product.json").read_bytes(),
    "VERSION": b"1.2.0\n",
    "install.sh": b"#!/usr/bin/env bash\n",
    "backend/requirements.txt": b"fastapi==0.141.1\n",
    "backend/system/updates/staging.py": b"print('stage')\n",
    "backend/applications/public_web/routes.py": b"print('public registry')\n",
    "backend/applications/public_web/transport.py": b"print('public gateway')\n",
    "deployment/install-systemd.sh": b"#!/usr/bin/env bash\n",
    "deployment/apply_staged_update.py": b"print('apply')\n",
    "deployment/bootstrap-local-agent.py": b"print('bootstrap agent')\n",
    "deployment/factory_reset.py": b"print('reset')\n",
    "deployment/local_agent_pairing.py": b"print('pair agent')\n",
    "deployment/restore_application_extensions.py": b"print('restore apps')\n",
    "deployment/migrate_database.py": b"print('migrate')\n",
    "deployment/update-dependency-allowlist.json": b'{"schema_version":1,"apt_packages":[]}\n',
    "deployment/systemd/3mm-agent.service": b"[Unit]\n",
    "deployment/systemd/3mm-setup-local.service": b"[Unit]\n",
    "deployment/systemd/3mm-application-extension@.service": b"[Unit]\n",
    "deployment/systemd/3mm-core.service": b"[Unit]\n",
    "deployment/systemd/3mm-update-helper.service": b"[Unit]\n",
    "deployment/systemd/3mm-web.service": b"[Unit]\n",
    "deployment/systemd/3mm-public-web.socket": b"[Socket]\n",
    "deployment/systemd/3mm-public-web.service": b"[Service]\n",
    "frontend/compiler/package.json": b'{"name":"compiler"}\n',
    "components/system_runtime/update_helper.py": b"print('helper')\n",
    "components/system_runtime/application_activation.py": b"print('activate app')\n",
    "components/system_runtime/application_host.py": b"print('host app')\n",
    "components/system_runtime/application_host_identity.py": b"# host metadata\n",
    "deployment/application_host_component.py": b"# host component\n",
    "deployment/component_transition.py": b"# coordinated component transition\n",
    "deployment/application-host-contract.json": Path("deployment/application-host-contract.json").read_bytes(),
    "deployment/application-host-requirements.txt": Path("deployment/application-host-requirements.txt").read_bytes(),
    "components/system_runtime/application_transport.py": b"print('transport app')\n",
    "components/public_web/__init__.py": b"# public web\n",
    "components/public_web/__main__.py": b"print('public main')\n",
    "components/public_web/server.py": b"print('public server')\n",
    "components/public_web/webhook_pilot.py": b"# public webhook transport\n",
    "packages/application_sdk/__init__.py": b"# sdk\n",
    'deployment/platform-runtime-contract.json': Path("deployment/platform-runtime-contract.json").read_bytes(),
    'deployment/platform_runtime_component.py': b"# component fixture\n",
    'deployment/systemd/3mm-platform-runtime.service': b"# component fixture\n",
    'packages/platform_wire/__init__.py': b"# component fixture\n",
    'packages/__init__.py': b"# shared packages\n",
    'packages/platform_wire/event_delivery.py': b"# component fixture\n",
    'packages/platform_wire/task_time.py': b"# component fixture\n",
    'components/platform_runtime/__init__.py': b"# component fixture\n",
    'components/platform_runtime/__main__.py': b"# component fixture\n",
    'components/platform_runtime/server.py': b"# component fixture\n",
    'components/platform_runtime/public_web.py': b"# component fixture\n",
    'components/platform_runtime/events.py': b"# component fixture\n",
    'components/platform_runtime/responses.py': b"# component fixture\n",
    'components/platform_runtime/connector_worker.py': b"# component fixture\n",
    'components/platform_runtime/connector_execute.py': b"# component fixture\n",
    'components/platform_runtime/tasks.py': b"# component fixture\n",
    'deployment/systemd/3mm-connector-worker.service': b"# component fixture\n",
    "frontend/dist/stale.js": b"must not survive\n",
}
TARGET_CONTRACT = json.loads(Path(CONTRACT_PATH).read_text(encoding="utf-8"))
RELATIONAL_RELEASE_FILES = (
    "backend/applications/authority/admin.py",
    "backend/applications/runtime/platform.py",
    "backend/applications/relational/authority.py",
    "backend/applications/relational/activation.py",
    "backend/applications/relational/activation_recovery.py",
    "backend/applications/relational/admin_worker.py",
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
    "packages/application_sdk/relational_preparation_recovery_wire.py",
    "packages/application_sdk/relational_receipts.py",
    "packages/application_sdk/relational_upgrade_receipts.py",
    "packages/application_sdk/relational_upgrade_wire.py",
    "packages/application_sdk/relational_wire.py",
    "components/system_runtime/application_database_snapshot.py",
    "components/system_runtime/application_relational_activation.py",
    "components/system_runtime/application_relational_activation_recovery.py",
    "components/system_runtime/application_relational_boot.py",
    "components/system_runtime/application_relational_boot_policy.py",
    "components/system_runtime/application_relational_control.py",
    "components/system_runtime/application_relational_installation.py",
    "components/system_runtime/application_relational_migrations.py",
    "components/system_runtime/application_relational_namespace.py",
    "components/system_runtime/application_relational_namespace_recovery.py",
    "components/system_runtime/application_relational_preparation.py",
    "components/system_runtime/application_relational_preparation_recovery.py",
    "components/system_runtime/application_relational_preparation_recovery_control.py",
    "components/system_runtime/application_relational_reactivation.py",
    "components/system_runtime/application_relational_recovery.py",
    "components/system_runtime/application_relational_recovery_confirmation.py",
    "components/system_runtime/application_relational_runtime.py",
    "components/system_runtime/application_relational_session.py",
    "components/system_runtime/application_relational_startup.py",
    "components/system_runtime/application_relational_upgrade.py",
    "components/system_runtime/application_relational_upgrade_confirmation.py",
    "components/system_runtime/application_relational_upgrade_control.py",
    "components/system_runtime/application_relational_upgrade_restore.py",
    "components/system_runtime/application_relational_upgrade_rollback.py",
    "components/system_runtime/update_helper_client.py",
)
REQUIRED_SOURCE_FILES[CONTRACT_PATH] = json.dumps(TARGET_CONTRACT).encode()
for migration in ("4f29a071b819_application_result_tasks", "5a30b182c920_application_task_schedules",
        "6b41c293da31_retire_builder_automations", "7c52d3a4eb42_retire_dashboards", "8d63e4b5fc53_retire_declarative_crud", "9e74f5c60d64_retire_legacy_content", "af85a6d71e75_user_subject_ids", "b096b7e82f86_kiosk_incarnations"):
    REQUIRED_SOURCE_FILES[f"backend/alembic/versions/{migration}.py"] = b"# migration fixture\n"
REQUIRED_SOURCE_FILES["packages/protocol/ui_metadata.py"] = b"# shared UI metadata fixture\n"
REQUIRED_SOURCE_FILES["backend/db/language_extension.py"] = b"# language projection fixture\n"
REQUIRED_SOURCE_FILES["backend/db/menu.py"] = b"# navigation fixture\n"
REQUIRED_SOURCE_FILES["backend/db/module_reference.py"] = b"# retained references fixture\n"
for required in TARGET_CONTRACT["required_files"]:
    if required not in {".3mm-release.json", "frontend/dist/index.html"}:
        REQUIRED_SOURCE_FILES.setdefault(required, b"placeholder\n")


def write_source_archive(
    path: Path,
    files: dict[str, bytes] | None = None,
) -> None:
    with tarfile.open(path, mode="w") as archive:
        for name, data in (files or REQUIRED_SOURCE_FILES).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            archive.addfile(info, io.BytesIO(data))


def write_frontend_dist(path: Path) -> None:
    (path / "assets").mkdir(parents=True)
    (path / "index.html").write_text('<div id="app"></div>\n', encoding="utf-8")
    (path / "assets" / "main.js").write_text("console.log('3mm')\n", encoding="utf-8")
    (path / "runtime-config.json").write_text(
        '{"backend_port":8887}\n', encoding="utf-8"
    )


def write_dependencies(path: Path, packages: list[object] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "apt_packages": (
                    packages if packages is not None else ["curl", "python3-venv"]
                ),
            }
        ),
        encoding="utf-8",
    )


def build(tmp_path: Path, output_name: str = "output", *,
          architectures=("aarch64", "x86_64"), armv6_ui_tools=None) -> dict[str, object]:
    source_archive = tmp_path / "source.tar"
    frontend_dist = tmp_path / "dist"
    dependencies_file = tmp_path / "dependencies.json"
    if not source_archive.exists():
        write_source_archive(source_archive)
    if not frontend_dist.exists():
        write_frontend_dist(frontend_dist)
    if not dependencies_file.exists():
        write_dependencies(dependencies_file)
    return build_release_assets(
        source_archive=source_archive,
        frontend_dist=frontend_dist,
        dependencies_file=dependencies_file,
        output_dir=tmp_path / output_name,
        repository="ldobranov/3mm",
        version="1.2.0",
        tag="v1.2.0",
        commit=COMMIT,
        branch="main",
        channel="stable",
        architectures=architectures,
        source_date_epoch=EPOCH,
        armv6_ui_tools=armv6_ui_tools,
    )


def test_builder_creates_strict_architecture_specific_manifest(tmp_path: Path) -> None:
    manifest = build(tmp_path)

    validated = UpdateManifest.model_validate(manifest)
    assert validated.version == "1.2.0"
    assert [artifact.architecture for artifact in validated.artifacts] == [
        "aarch64",
        "x86_64",
    ]
    assert validated.dependencies.apt_packages == ["curl", "python3-venv"]
    assert (
        json.loads(
            (tmp_path / "output" / "3mm-update-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        == manifest
    )


def test_full_armv6_release_requires_and_only_it_contains_its_toolchain(tmp_path, monkeypatch):
    from deployment import armv6_ui_tools as tools
    import hashlib

    with pytest.raises(ReleaseBuildError, match="require separate ARMv6"):
        build(tmp_path, architectures=("armv6l",))
    source = tmp_path / "ui-tools"
    source.mkdir()
    (source / "esbuild").write_bytes(b"x86")
    (source / "rollup.tgz").write_bytes(b"fixture")
    (source / "esbuild-notices.txt").write_bytes(b"fixture notice")
    with pytest.raises(ReleaseBuildError, match="not a Linux ARM binary"):
        build(tmp_path, architectures=("armv6l",), armv6_ui_tools=source)
    (source / "esbuild").write_bytes(b"\x7fELF\x01\x01" + b"\0" * 12 + b"\x28\x00")
    with pytest.raises(ReleaseBuildError, match="pinned digest"):
        build(tmp_path, architectures=("armv6l",), armv6_ui_tools=source)
    monkeypatch.setattr(tools, "ROLLUP_SHA256", hashlib.sha256(b"fixture").hexdigest())
    manifest = build(tmp_path, architectures=("armv6l", "aarch64"), armv6_ui_tools=source)
    arm_manifest = json.loads((tmp_path / "output/3mm-armv6-update-manifest.json").read_text())
    assert [item.architecture for item in UpdateManifest.model_validate(manifest).artifacts] == ["aarch64"]
    assert [item.architecture for item in UpdateManifest.model_validate(arm_manifest).artifacts] == ["armv6l"]
    for artifact in manifest["artifacts"] + arm_manifest["artifacts"]:
        with tarfile.open(tmp_path / "output" / artifact["filename"]) as archive:
            paths = {name for name in archive.getnames() if name.startswith(tools.TOOLS_PATH + "/")}
            assert paths == ({f"{tools.TOOLS_PATH}/{name}" for name in tools.FILES}
                if artifact["architecture"] == "armv6l" else set())


def test_release_archives_are_reproducible_and_installer_compatible(
    tmp_path: Path,
) -> None:
    first_manifest = build(tmp_path, "first")
    second_manifest = build(tmp_path, "second")

    assert first_manifest == second_manifest
    for artifact in first_manifest["artifacts"]:
        filename = artifact["filename"]
        first_archive = tmp_path / "first" / filename
        second_archive = tmp_path / "second" / filename
        assert first_archive.read_bytes() == second_archive.read_bytes()

        with tarfile.open(first_archive, mode="r:gz") as archive:
            names = set(archive.getnames())
            assert "frontend/dist/index.html" in names
            assert "frontend/dist/assets/main.js" in names
            assert "frontend/dist/stale.js" not in names
            assert "deployment/install-systemd.sh" in names
            assert "deployment/factory_reset.py" in names
            assert "deployment/frontend_access.py" in names
            assert "deployment/systemd/3mm-public-web.socket" in names
            assert "components/public_web/server.py" in names
            assert "packages/application_sdk/files.py" in names
            assert "packages/application_sdk/file_wire.py" in names
            assert "packages/application_sdk/scoped_files.py" in names
            assert "components/system_runtime/application_file_executor.py" in names
            assert "backend/applications/files/authority.py" in names
            assert "components/system_runtime/application_files_snapshot.py" in names
            assert set(RELATIONAL_RELEASE_FILES) <= names
            assert "install.sh" in names
            assert json.load(archive.extractfile(CONTRACT_PATH)) == TARGET_CONTRACT
            assert all(member.mtime == EPOCH for member in archive.getmembers())
            metadata = json.load(archive.extractfile(".3mm-release.json"))
            assert metadata["architecture"] == artifact["architecture"]
            assert metadata["commit"] == COMMIT
            assert metadata["release_id"] == "v1.2.0"

            metadata_path = tmp_path / f"{artifact['architecture']}.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            current = read_current_release(metadata_path)
            assert current.release_id == "v1.2.0"
            assert current.version == "1.2.0"


def test_builder_rejects_unsafe_source_paths(tmp_path: Path) -> None:
    source_archive = tmp_path / "source.tar"
    files = dict(REQUIRED_SOURCE_FILES)
    files["../outside"] = b"unsafe"
    write_source_archive(source_archive, files)
    write_frontend_dist(tmp_path / "dist")
    write_dependencies(tmp_path / "dependencies.json")

    with pytest.raises(ReleaseBuildError, match="Unsafe archive path"):
        build(tmp_path)


@pytest.mark.parametrize("required", ADMIN_WEB_FILES + SETUP_FILES + PUBLIC_WEB_FILES + NETWORK_RECOVERY_FILES + DEVICE_HARDWARE_FILES + DEVICE_REGISTRY_FILES + DEVICE_FEATURE_FILES + DEVICE_MODULE_FILES + DEVICE_OPERATIONS_FILES + DEVICE_ADMINISTRATION_FILES + SETTINGS_AUDIT_FILES + DEVICE_TELEMETRY_FILES + PROVIDER_TEMPLATE_FILES + LOCALIZATION_FILES + APPLICATION_MANAGEMENT_FILES + APPLICATION_RUNTIME_FILES + APPLICATION_RESOURCE_FILES + INTERACTIVE_SESSION_FILES + APPLICATION_CONTENT_FILES + APPLICATION_AUTHORITY_FILES + INSTALLATION_FILES + STORAGE_FILES + ARTIFACT_FILES + APPEARANCE_FILES + ACCOUNT_SESSION_FILES + ACCOUNT_ACCESS_FILES + DIAGNOSTIC_FILES + PLATFORM_WIRE_FILES + PROVISIONING_FILES + SYSTEM_UPDATE_FILES + BACKUP_FILES + PRODUCT_FILES + RUNTIME_ACTIVATION_FILES + ("backend/applications/relational/__init__.py", "backend/system/control.py", "packages/application_sdk/__init__.py", "packages/application_sdk/discovery.py", "components/system_runtime/__init__.py", "deployment/component_transition.py") + tuple(
    'components/platform_runtime/' + name + '.py' for name in
    ('__init__', '__main__', 'server', 'public_web', 'events', 'responses', 'connector_worker', 'connector_execute', 'tasks')))
def test_missing_relocated_runtime_is_rejected_before_activation(tmp_path, required):
    assert required in TARGET_CONTRACT["required_files"]
    with pytest.raises(DeploymentContractError, match=required):
        validate_deployment_contract(
            REQUIRED_SOURCE_FILES[CONTRACT_PATH],
            set(TARGET_CONTRACT["required_files"]) - {required},
        )
    files = dict(REQUIRED_SOURCE_FILES)
    del files[required]
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match=required):
        build(tmp_path)


def test_core_domains_import_from_extracted_release(tmp_path):
    root = Path(__file__).resolve().parents[2]
    files = dict(REQUIRED_SOURCE_FILES)
    files['packages/__init__.py'] = (root/'packages/__init__.py').read_bytes()
    files['components/__init__.py'] = (root/'components/__init__.py').read_bytes()
    files['packages/protocol/theme_design_defaults.json'] = (
        root/'packages/protocol/theme_design_defaults.json').read_bytes()
    # Use real Core/shared Python sources, not the release fixture placeholders.
    # The child must resolve the domain and its common dependencies solely from
    # the produced archive plus the already installed dependency environment.
    for package in ("backend", "agent", "deployment", "packages/protocol", "packages/provisioning",
                    "packages/application_sdk",
                    "components/system_runtime", "packages/platform_wire", "components/public_web", "components/platform_runtime",
                    "components/setup"):
        for directory, subdirectories, names in os.walk(root / package):
            subdirectories[:] = [name for name in subdirectories if not name.startswith(".")
                                 and name not in {"tests", "__pycache__", "data", "uploads",
                                                  "venv", "venv3", "env", "node_modules"}
                                 and not (Path(directory) / name).is_symlink()]
            for name in names:
                path = Path(directory) / name
                if name.endswith(".py") and not path.is_symlink():
                    files[path.relative_to(root).as_posix()] = path.read_bytes()
    for name in SETUP_FILES:
        files[name] = (root/name).read_bytes()
    for name in PROVIDER_TEMPLATE_FILES:
        files[name] = (root/name).read_bytes()
    write_source_archive(tmp_path / "source.tar", files)
    manifest = build(tmp_path, architectures=("x86_64",))
    extracted = tmp_path / "release"
    with tarfile.open(tmp_path / "output" / manifest["artifacts"][0]["filename"], "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    result = subprocess.run(
        [sys.executable, "-E", "-c", '''
from importlib.util import find_spec
from pathlib import Path
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.database  # Register the real ORM model set before the projection query.
from backend.devices import hardware_interfaces
from backend.devices.registry import api as registry_api, read as registry_read, online as registry_online
from backend.devices.features import api as features_api, service as features_service
from backend.devices.modules import lifecycle as module_lifecycle, authority as module_authority
from backend.devices import operations as device_operations, authority as device_authority
from backend.devices import auth as device_auth, http as device_http, body_limit
from backend.devices.commands import api as command_api, queue as command_queue, notifier
from backend.devices.capabilities import api as capability_api, state_api, registry as capability_registry
from backend.devices.telemetry import ingest_api, events_api, state_api as telemetry_state
from backend.devices.modules import templates
from backend.devices.pairing import api as pairing_api, service as pairing_service, enrollment
from backend.devices.platform import api as device_platform_api, service as device_platform_service
from backend.devices.updates import api as node_api, delivery_api, catalog, approval, delivery, execution
from backend.localization import api as localization_api, packages as localization_packages
from backend.applications.management import configuration, requirements, staging as application_staging, provenance
from backend.applications.management import api as management_api, access_api, connector_api, ui_admin_api
from backend.applications.management import lifecycle, consent, lifecycle_consent, connector_settings
from backend.artifacts import api as artifact_api, packages as artifact_packages, inspection as artifact_inspection
from backend.artifacts import code_scope, compiled_ui as artifact_ui, provenance as artifact_provenance
from backend.appearance import api as appearance_api, packages as appearance_packages, customization, assets as appearance_assets
from backend.accounts.sessions import api as session_api, refresh as session_refresh, policy as session_policy
from backend.accounts import passwords, tokens, dependencies, users_api
from backend.accounts.access import api as access_catalog, sources, groups_api, roles_api, permissions_api
from backend.applications.authority import access as application_access, context as authority_context
from backend.applications.authority import policy as authority_policy, subjects, keys, review, sources as authority_sources
from backend.applications.authority import management as authority_management, inspection, admin, metadata
from backend.applications.authority import policy_reviews, tasks as authority_tasks, composition
from backend.installation import identity, session_tls, status_binding, projection, peer_read_sources, peer_listing, peers
from backend.installation import api as installation_api
from backend.storage import engine as storage_engine, sessions as storage_sessions, public_assets
from backend.system import components as core_components
from backend.accounts import bootstrap
from backend.localization import service as localization_service
from backend.settings import api as settings_api, crud
from backend.system.audit import api as audit_api, retention
from backend.applications.relational import authority as relational_authority, lifecycle as relational_lifecycle
from backend.applications.relational import registration, candidate, activation, activation_recovery, reactivation
from backend.applications.relational import boot, startup, admin_worker, upgrade, upgrade_confirmation, upgrade_rollback
from backend.applications.relational import upgrade_admin, upgrade_cli, recovery, recovery_confirmation, namespace_recovery, preparation_recovery
from backend.system import control
from backend.system.network_recovery import api, service
from backend.system.diagnostics import api as diagnostic_api
from backend.system.diagnostics import failures, operations, workspace, bundle, alerts
from backend.system.updates import api as updates_api
from backend.system.updates import releases, policy, staging, platform_runtime, components_api, components
from backend.system.backups import api as backups_api, service as backups_service
from packages.application_sdk import ApplicationPlatformError
from packages.protocol.extension_schemas import extension_schema_catalog
from packages.protocol.theme_extension_v2 import DESIGN_DEFAULTS
from components.public_web import server, webhook_pilot
from packages.provisioning import persistence
from components.platform_runtime import server as platform_server
from components.platform_runtime import connector_worker, connector_execute, events, responses, tasks
from components.setup import main as setup_main, product as setup_product
from components.system_runtime import DeviceRuntimePlanner, RuntimeService
from components.system_runtime import application_transport, update_helper_client, install_bootstrap

root = Path.cwd().resolve()
assert all(Path(module.__file__).resolve().is_relative_to(root)
           for module in (control, api, service, hardware_interfaces, server, webhook_pilot, persistence,
                          diagnostic_api, failures, operations, workspace, bundle, alerts, setup_main, setup_product,
                          updates_api, releases, policy, staging, platform_runtime, components_api, components,
                          backups_api, backups_service, registry_api, registry_read, registry_online,
                          features_api, features_service, module_lifecycle, module_authority,
                          localization_api, localization_packages, configuration, requirements, application_staging, provenance,
                          application_transport, update_helper_client, install_bootstrap))
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in
           (artifact_api, artifact_packages, artifact_inspection, code_scope, artifact_ui, artifact_provenance,
            appearance_api, appearance_packages, customization, appearance_assets, session_api, session_refresh, session_policy))
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in
           (device_operations, device_authority, device_auth, device_http, body_limit,
            command_api, command_queue, notifier, capability_api, state_api, capability_registry,
            management_api, access_api, connector_api, ui_admin_api, lifecycle, consent, lifecycle_consent,
            connector_settings, passwords, tokens, dependencies, users_api, access_catalog, sources,
            groups_api, roles_api, permissions_api))
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in
           (ingest_api, events_api, telemetry_state, templates, application_access, authority_context,
            authority_policy, subjects, keys, review, authority_sources, authority_management, inspection,
            admin, metadata, policy_reviews, authority_tasks, composition, identity, session_tls, status_binding,
            projection, peer_read_sources, peer_listing, peers, installation_api, storage_engine,
            storage_sessions, public_assets, core_components, bootstrap, localization_service))
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in
           (pairing_api, pairing_service, enrollment, device_platform_api, device_platform_service,
            node_api, delivery_api, catalog, approval, delivery, execution, settings_api, crud, audit_api, retention,
            relational_authority, relational_lifecycle, registration, candidate, activation, activation_recovery,
            reactivation, boot, startup, admin_worker, upgrade, upgrade_confirmation, upgrade_rollback,
            upgrade_admin, upgrade_cli, recovery, recovery_confirmation, namespace_recovery, preparation_recovery))
# Consumers must retain the actual shared dependency/module objects, not shims
# that would split overrides, token decoding or the command-notification state.
assert session_api.require_user is dependencies.require_user
assert command_api.require_admin is dependencies.require_admin
assert users_api.decode_token is tokens.decode_token
assert command_api.device_command_notifier is notifier.device_command_notifier
assert dependencies.get_db is storage_sessions.get_db
assert storage_sessions.engine is storage_engine.engine
assert backend.database.engine is not storage_engine.engine
assert authority_management.CoreReviewKeyStore is keys.CoreReviewKeyStore
assert installation_api.peers is peers
assert device_platform_api.device_command_notifier is notifier.device_command_notifier
assert settings_api.create_crud_routes is crud.create_crud_routes
assert settings_api.i18n_manager is localization_service.i18n_manager
assert audit_api.audit_retention is retention
assert ApplicationPlatformError.__module__ == "packages.application_sdk"
for name in ('backend.routes', 'backend.services', 'backend.utils'):
    assert find_spec(name) is None, name
assert find_spec("three_mm_protocol") is None
assert find_spec("three_mm_application_sdk") is None
assert find_spec("three_mm_runtime") is None
assert find_spec("three_mm_platform_runtime") is None
assert find_spec("three_mm_public_web") is None
assert find_spec("three_mm_provisioning") is None
assert find_spec("setup_service") is None
assert setup_main.SETUP_PAGE == root / 'components/setup/static/setup.html'
assert setup_product.PRODUCT_PATH == root / 'config_templates/product.json'
assert setup_product.load_product_metadata() == json.loads(setup_product.PRODUCT_PATH.read_text())
assert localization_packages.BundledLanguagePackages(None,None).root == root / 'modules'
assert DeviceRuntimePlanner.__module__ == 'components.system_runtime.services'
assert RuntimeService.__module__ == 'components.system_runtime.services'
assert artifact_ui._compiler_script() == root / 'frontend/compiler/compile-ui-extension.mjs'
assert templates.BUNDLED_TEMPLATES == root/'backend/devices/modules/template_data'
template_sources = templates.sources()
assert {source.descriptor.template_id for source in template_sources.values()} == {
    'character-display.mock', 'character-display.pcf8574-2row', 'character-display.pcf8574-4row',
    'gpio-input.gpiod', 'gpio-input.mock'}
template_id = next(key for key,source in template_sources.items()
                   if source.descriptor.template_id == 'character-display.pcf8574-2row')
blob = templates.prepare_provider(template_id, {'columns':16})
assert blob == templates.prepare_provider(template_id, {'columns':16})
prepared_profile = artifact_packages.validate_module_package(blob)
assert prepared_profile.manifest.configuration_defaults['columns'] == 16
assert prepared_profile.manifest.configuration_defaults['rows'] == 2
assert server.PublicWebRequestHandler.server_version == "3mm-Public-Web/1"
assert DESIGN_DEFAULTS == json.loads(
    (root / "packages/protocol/theme_design_defaults.json").read_text())
contracts = extension_schema_catalog()["contracts"]
assert "theme-extension.v2" in contracts
assert contracts["theme-extension.v2"]["schema"]["$id"] == "urn:3mm:schema:theme-extension.v2"
app = FastAPI()
app.include_router(api.router)
app.include_router(control.router)
app.include_router(hardware_interfaces.router)
schema = app.openapi()
prefix = "/api/v1/network-recovery"
assert {path: set(operations) for path, operations in schema["paths"].items()} == {
    prefix + "/status": {"get"}, prefix + "/policy": {"put"},
    prefix + "/setup": {"post"}, prefix + "/access-point": {"post"},
    prefix + "/access-point/stop": {"post"},
    "/api/v1/system-control/restart": {"post"},
    "/api/v1/system-control/factory-reset": {"post"},
    "/api/v1/devices/{device_id}/hardware-interfaces": {"get"},
    "/api/v1/devices/{device_id}/hardware-interfaces/i2c/enable": {"post"},
    "/api/v1/devices/{device_id}/hardware-interfaces/restart": {"post"},
}
assert "NetworkRecoveryStatus" in schema["components"]["schemas"]
assert "SystemActionQueued" in schema["components"]["schemas"]
assert "EnableI2cRequest" in schema["components"]["schemas"]
assert "RestartRequest" in schema["components"]["schemas"]
updates_app = FastAPI()
updates_app.include_router(updates_api.router)
prefix_updates = "/api/v1/system-updates"
expected_updates = {
    "/status": {"get"}, "/check": {"post"}, "/policy": {"get", "put"},
    "/operation": {"get"}, "/stage": {"post"}, "/apply": {"post"},
    "/runtime": {"get"}, "/runtime/prepare": {"post"},
    "/runtime/apply": {"post"}, "/runtime/recover": {"post"},
    "/components/targets": {"get"}, "/components/nodes": {"get"},
    "/components/{component}/{target_id}": {"get"},
    "/components/{component}/{target_id}/prepare": {"post"},
    "/components/{component}/{target_id}/apply": {"post"},
    "/components/{component}/{target_id}/rollback": {"post"},
    "/components/{component}/{target_id}/recover": {"post"},
}
assert {path: set(methods) for path, methods in updates_app.openapi()["paths"].items()} == {
    prefix_updates + path: methods for path, methods in expected_updates.items()}
def unexpected_helper(*args, **kwargs):
    raise AssertionError("An unauthenticated request must not reach the helper")
control.UpdateHelperClient = unexpected_helper
hardware_interfaces.UpdateHelperClient = unexpected_helper
updates_api.UpdateHelperClient = unexpected_helper
components_api.UpdateHelperClient = unexpected_helper
with TestClient(updates_app) as update_client:
    for path, methods in expected_updates.items():
        target = prefix_updates + path.replace("{component}", "agent").replace("{target_id}", "local")
        for method in methods:
            assert update_client.request(method, target, **({} if method == "get" else {"json": {}})).status_code == 401
with TestClient(app) as client:
    assert client.get(prefix + "/status").status_code == 401
    for action in ("restart", "factory-reset"):
        assert client.post("/api/v1/system-control/" + action,
                           json={"confirmation": "RESTART"}).status_code == 401
    hardware_path = "/api/v1/devices/dev_" + "a" * 32 + "/hardware-interfaces"
    assert client.get(hardware_path).status_code == 401
    for suffix in ("/i2c/enable", "/restart"):
        assert client.post(hardware_path + suffix, json={}).status_code == 401
# Diagnostics have a separate router: every administrative boundary must remain
# guarded even in an extracted release that cannot import old source locations.
diagnostic_app = FastAPI()
diagnostic_app.include_router(diagnostic_api.router)
with TestClient(diagnostic_app) as client:
    for path, methods in diagnostic_app.openapi()["paths"].items():
        for method in methods:
            assert client.request(method, path, json={} if method != "get" else None).status_code == 401
backup_app = FastAPI()
backup_app.include_router(backups_api.router)
expected_backups = {
    "/api/v1/backups": {"get", "post"}, "/api/v1/backups/preview": {"get"},
    "/api/v1/backups/operation": {"get"}, "/api/v1/backups/restore": {"post"},
    "/api/v1/backups/{backup_id}/export": {"post"},
    "/api/v1/backups/exports/{export_id}": {"get"},
    "/api/v1/backups/restore-file": {"post"},
}
assert {path: set(methods) for path, methods in backup_app.openapi()["paths"].items()} == expected_backups
backups_api.UpdateHelperClient = unexpected_helper
backups_api.get_settings = unexpected_helper
with TestClient(backup_app) as client:
    for path, methods in expected_backups.items():
        target = path.replace("{backup_id}", "bkp_20261111T120000Z_aaaaaaaa").replace("{export_id}", "a" * 32)
        for method in methods:
            assert client.request(method, target, json={} if method != "get" else None).status_code == 401
registry_app = FastAPI()
registry_app.include_router(registry_api.router)
assert set(registry_app.openapi()["paths"]) == {"/api/v1/devices", "/api/v1/devices/{device_id}"}
registry_api.read_devices = unexpected_helper
registry_api.read_device = unexpected_helper
with TestClient(registry_app) as client:
    for path in ("/api/v1/devices", "/api/v1/devices/dev_" + "a" * 32):
        assert client.get(path).status_code == 401
features_app = FastAPI()
features_app.include_router(features_api.router)
assert {path:set(methods) for path,methods in features_app.openapi()["paths"].items()} == {
    "/api/v1/devices/{device_id}/protocol":{"get"},
    "/api/v1/devices/{device_id}/runtime-features":{"get","put"},
}
features_api.DeviceOperations = unexpected_helper
features_api.runtime_features_snapshot = unexpected_helper
with TestClient(features_app) as client:
    prefix = "/api/v1/devices/dev_" + "a" * 32
    assert client.get(prefix + "/protocol").status_code == 401
    assert client.get(prefix + "/runtime-features").status_code == 401
    assert client.put(prefix + "/runtime-features", json={}).status_code == 401
device_app = FastAPI()
for module in (command_api, capability_api, state_api):
    device_app.include_router(module.router)
device_prefix = '/api/v1/devices/{device_id}'
expected_device_operations = {
    '/commands': {'get', 'post'}, '/commands/next': {'get'},
    '/commands/{command_id}/result': {'post'},
    '/commands/{command_id}/authorize-execution': {'post'},
    '/capabilities': {'get'}, '/capability-providers': {'get'},
    '/capability-providers/{provider_type}/{provider_id}': {'get', 'put'},
    '/capability-providers/{provider_type}/{provider_id}/enabled': {'post'},
    '/capability-providers/{provider_type}/{provider_id}/configuration': {'post'},
    '/capability-availability': {'post'}, '/capabilities/invoke': {'post'},
    '/capabilities/{capability_id}/state': {'get', 'post'},
}
assert {path:set(methods) for path,methods in device_app.openapi()['paths'].items()} == {
    device_prefix+path:methods for path,methods in expected_device_operations.items()}
with TestClient(device_app) as client:
    for path,methods in expected_device_operations.items():
        target = (device_prefix+path).replace('{device_id}','dev_'+'a'*32).replace('{command_id}','cmd_'+'b'*32)
        target = target.replace('{provider_type}','agent_module').replace('{provider_id}','org.example.provider')
        target = target.replace('{capability_id}','example.output')
        for method in methods:
            assert client.request(method,target,json={} if method!='get' else None).status_code == 401
telemetry_app = FastAPI()
for module in (ingest_api,events_api,telemetry_state):
    telemetry_app.include_router(module.router)
expected_telemetry = {'/heartbeat':{'post'},'/inventory':{'post'},'/events':{'get','post'},
    '/desired-state':{'get','put'},'/reported-state':{'post'},'/state':{'get'}}
assert {path:set(methods) for path,methods in telemetry_app.openapi()['paths'].items()} == {
    device_prefix+path:methods for path,methods in expected_telemetry.items()}
with TestClient(telemetry_app) as client:
    for path,methods in expected_telemetry.items():
        for method in methods:
            target = (device_prefix+path).replace('{device_id}','dev_'+'a'*32)
            assert client.request(method,target,json={} if method!='get' else None).status_code == 401
installation_app = FastAPI()
installation_app.include_router(installation_api.router)
with TestClient(installation_app) as client:
    prefix = '/api/v1/installation-peers'
    assert client.get(prefix+'/origin').status_code == 401
    assert client.put(prefix+'/origin',json={'origin':'https://example.invalid'}).status_code == 401
    assert client.get(prefix+'/applications/org.example.app').status_code == 401
pairing_app = FastAPI()
pairing_app.include_router(pairing_api.router)
expected_pairing = {'/pairing/enroll':{'post'},'/pairing/requests':{'get'},
    '/pairing/requests/{request_id}/reject':{'post'},'/pairing-codes':{'post'},'/pairing/claim':{'post'},
    '/pairing/requests/{request_id}/approve':{'post'},'/pairing/complete':{'post'},
    '/devices/{device_id}/credentials/{credential_id}/revoke':{'post'},
    '/devices/{device_id}/credentials/replace':{'post'}}
assert {path:set(methods) for path,methods in pairing_app.openapi()['paths'].items()} == {
    '/api/v1'+path:methods for path,methods in expected_pairing.items()}
with TestClient(pairing_app) as client:
    for path,methods in expected_pairing.items():
        target = ('/api/v1'+path).replace('{request_id}','1').replace('{device_id}','dev_'+'a'*32).replace('{credential_id}','credential')
        for method in methods:
            expected = 422 if path in {'/pairing/enroll','/pairing/claim','/pairing/complete'} else 401
            assert client.request(method,target,json={} if method!='get' else None).status_code == expected
platform_app = FastAPI()
platform_app.include_router(device_platform_api.router)
expected_platform = {'/pairing/authority-proof':{'post'},'/devices/{device_id}/authority-exchange':{'post'},
    '/devices/{device_id}/lifecycle':{'put'},'/devices/{device_id}/platform':{'get'},
    '/devices/{device_id}/authority/release':{'post'},'/devices/{device_id}/authority/prepare-enrollment':{'post'}}
assert {path:set(methods) for path,methods in platform_app.openapi()['paths'].items()} == {
    '/api/v1'+path:methods for path,methods in expected_platform.items()}
with TestClient(platform_app) as client:
    for path,methods in expected_platform.items():
        target = ('/api/v1'+path).replace('{device_id}','dev_'+'a'*32)
        for method in methods:
            expected = 422 if path=='/pairing/authority-proof' else 401
            assert client.request(method,target,json={} if method!='get' else None).status_code == expected
node_app = FastAPI()
node_app.include_router(node_api.router)
node_app.include_router(delivery_api.router)
expected_node = {'/{device_id}/node-updates/check':{'get'},'/{device_id}/node-updates/prepare':{'post'},
    '/{device_id}/node-updates/{operation_id}':{'get'},'/node-updates/approval-key':{'get'},
    '/{device_id}/node-updates/{operation_id}/apply':{'post'},'/{device_id}/node-updates/{operation_id}/report':{'post'},
    '/{device_id}/node-updates/{operation_id}/archive':{'get'}}
assert {path:set(methods) for path,methods in node_app.openapi()['paths'].items()} == {
    '/api/v1/devices'+path:methods for path,methods in expected_node.items()}
# The public key identity endpoint is intentionally public. Do not create or
# access an installed approval key while proving the other routes deny access.
node_api.public_approval_key = unexpected_helper
with TestClient(node_app) as client:
    for path,methods in expected_node.items():
        if path=='/node-updates/approval-key': continue
        target = ('/api/v1/devices'+path).replace('{device_id}','dev_'+'a'*32).replace('{operation_id}','operation')
        for method in methods:
            assert client.request(method,target,json={} if method!='get' else None).status_code == 401
settings_app = FastAPI()
settings_app.include_router(settings_api.router)
settings_app.include_router(audit_api.router,prefix='/api')
with TestClient(settings_app) as client:
    assert client.get('/role/read').status_code == 401
    assert client.post('/settings/create',json={}).status_code == 401
    assert client.get('/api/audit-logs').status_code == 401
    assert client.get('/api/audit-logs/retention-plan').status_code == 401
    assert client.post('/api/audit-logs/retention',json={}).status_code == 401
account_app = FastAPI()
account_app.include_router(users_api.router,prefix='/api/user')
for module in (groups_api,roles_api,permissions_api):
    account_app.include_router(module.router,prefix='/api')
with TestClient(account_app) as client:
    assert client.get('/api/user/read',headers={'Authorization':'Bearer invalid'}).status_code == 401
    for path in ('/api/groups','/api/roles','/api/permissions/my','/api/access'):
        assert client.get(path).status_code == 401
    assert client.put('/api/access/bindings',json={}).status_code == 401
management_app = FastAPI()
management_app.include_router(management_api.router)
management_app.include_router(access_api.router)
with TestClient(management_app) as client:
    prefix = '/api/v1/application-extensions'
    assert client.get(prefix).status_code == 401
    assert client.get(prefix+'/org.example.app/authority').status_code == 401
    assert client.post(prefix+'/org.example.app/authority/consent/preview',json={}).status_code == 401
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.db.language_extension import LanguageExtensionInstallation
engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
LanguageExtensionInstallation.__table__.create(engine)
def localization_db():
    with Session(engine) as db:
        yield db
localization_app = FastAPI()
localization_app.include_router(localization_api.router, prefix="/api")
localization_app.dependency_overrides[localization_api.get_db] = localization_db
with TestClient(localization_app) as client:
    response = client.get("/api/translations/en")
    assert response.status_code == 200
    assert response.json() == {"language_code":"en","frontend":{},"backend":{},"extensions":{}}
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/v1/modules/languages/catalog").status_code == 401
    assert client.post("/api/v1/modules/languages/packages/" + "a" * 64 + "/enable").status_code == 401
    assert client.delete("/api/v1/modules/languages/packages/" + "a" * 64).status_code == 401
from backend.db.module import ModulePackage, ThemeExtensionInstallation
from backend.db.settings import Settings
ModulePackage.__table__.create(engine)
ThemeExtensionInstallation.__table__.create(engine)
Settings.__table__.create(engine)
artifact_app = FastAPI()
artifact_app.include_router(artifact_api.router)
artifact_app.dependency_overrides[artifact_api.get_db] = localization_db
artifact_api.validate_module_package = unexpected_helper
artifact_api.compile_ui_package = unexpected_helper
with TestClient(artifact_app) as client:
    assert client.post('/api/v1/modules/packages/inspect',content=b'',headers={'Content-Type':'application/zip'}).status_code == 401
    assert client.get('/api/v1/modules/packages').status_code == 401
    assert client.get('/api/v1/modules/agent-catalog').status_code == 401
    response = client.get('/api/v1/modules/compiled-ui/catalog')
    assert response.status_code == 200 and response.json() == {'items':[]}
    assert client.get('/api/v1/modules/compiled-ui/assets/org.example.missing/1.0.0/'+'a'*64+'/assets/missing.mjs').status_code == 404
    assert client.get('/api/v1/modules/themes/appearance').status_code == 200
    assert client.get('/api/v1/modules/themes/catalog').status_code == 401
    assert client.post('/api/v1/modules/themes/selection',json={'sha256':None}).status_code == 401
    assert client.post('/api/v1/modules/themes/packages/'+'a'*64+'/enable').status_code == 401
    assert client.delete('/api/v1/modules/themes/packages/'+'a'*64).status_code == 401
sessions_app = FastAPI()
sessions_app.include_router(session_api.router,prefix='/api')
sessions_app.include_router(session_refresh.router,prefix='/api')
expected_sessions = {'/api/sessions/my':{'get'},'/api/sessions/logout-all':{'post'},
    '/api/sessions/{session_id}':{'delete'},'/api/sessions/track-activity':{'post'},
    '/api/user/refresh':{'post'},'/api/admin/session-settings':{'get','put'}}
assert {path:set(methods) for path,methods in sessions_app.openapi()['paths'].items()} == expected_sessions
session_api.create_audit_log = unexpected_helper
session_refresh.save_session_duration_hours = unexpected_helper
with TestClient(sessions_app) as client:
    for path,methods in expected_sessions.items():
        for method in methods:
            assert client.request(method,path.replace('{session_id}','1'),json={'duration_hours':24}).status_code == 401
engine.dispose()
print("Extracted Core domains: passed")
'''],
        cwd=extracted,
        env={key: value for key, value in {**os.environ, "DATABASE_URL": "sqlite://"}.items()
             if key not in {"PYTHONPATH", "PYTHONHOME", "COMPILED_UI_COMPILER_SCRIPT"}},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    # A separate child keeps the second, independently composed source family
    # bounded without increasing the existing cold-import subprocess budget.
    runtime_result = subprocess.run(
        [sys.executable, "-E", "-c", '''
from importlib.util import find_spec
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.database
from backend.applications.runtime import gateway as runtime_gateway, platform as runtime_platform
from backend.applications.runtime import invocations, responses, health, identity, status, peers, status_probe
from backend.applications.resources import discovery as resource_discovery, providers
from backend.applications.commands import broker as command_broker, discovery as command_discovery, rebinding, passage
from backend.applications.connectors import broker as connector_broker, transport as connector_transport, secrets
from backend.applications import operations_api
from backend.applications.events import broker as event_broker, publication, api as event_api
from backend.applications.tasks import broker as task_broker, schedules, api as task_api
from backend.sessions import broker as session_broker, transport as session_transport
from backend.sessions import gateway as session_gateway, agent as session_agent, discovery as session_discovery
from backend.sessions import acceptance, api as generic_session_api
from backend.applications.sessions import browser, local, remote, authority, runtimes, api as application_session_api

root = Path.cwd().resolve()
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in (
    runtime_gateway, runtime_platform, invocations, responses, health, identity, status, peers, status_probe,
    resource_discovery, providers, command_broker, command_discovery, rebinding, passage,
    connector_broker, connector_transport, secrets, operations_api, event_broker, publication, event_api,
    task_broker, schedules, task_api, session_broker, session_transport, session_gateway, session_agent,
    session_discovery, acceptance, generic_session_api, browser, local, remote, authority, runtimes, application_session_api))
assert invocations.ApplicationGatewayError is runtime_gateway.ApplicationGatewayError
assert health.ResponseWaiter is responses.ResponseWaiter
assert status_probe.ResponseWaiter is responses.ResponseWaiter
assert schedules.tasks is task_broker
assert operations_api.ApplicationConnectorError is connector_broker.ApplicationConnectorError
assert operations_api.ApplicationGatewayError is runtime_gateway.ApplicationGatewayError
assert event_api.application_event_status is event_broker.application_event_status
assert task_api._snapshot is task_broker._snapshot
assert generic_session_api.get_session_gateway is session_gateway.get_session_gateway
assert generic_session_api.get_device_tickets is session_agent.get_device_tickets
assert browser.ReviewedSessionRuntime is runtimes.ReviewedSessionRuntime
for name in ('backend.routes', 'backend.services', 'backend.utils'):
    assert find_spec(name) is None, name

operations_app = FastAPI()
operations_app.include_router(operations_api.router)
operations_app.include_router(event_api.router)
operations_app.include_router(task_api.router, prefix='/api/v1/application-extensions')
expected_operations = {
    '/api/v1/application-extensions/{module_id}/jobs/{job_id}/resolve': {'post'},
    '/api/v1/application-extensions/{module_id}/secrets': {'get', 'post'},
    '/api/v1/application-extensions/{module_id}/secrets/{secret_ref}': {'put', 'delete'},
    '/api/v1/application-extensions/{module_id}/connectors/{connector_id}': {'put'},
    '/api/v1/application-extensions/{module_id}/operational-status': {'get'},
    '/api/v1/application-events/status': {'get'},
    '/api/v1/application-events/drain': {'post'},
    '/api/v1/application-extensions/{module_id}/tasks/{task_run_id}/resolve': {'post'}}
assert {path:set(methods) for path,methods in operations_app.openapi()['paths'].items()} == expected_operations
with TestClient(operations_app) as client:
    for path, methods in expected_operations.items():
        for method in methods:
            url = path.replace('{module_id}', 'org.example.missing').replace('{job_id}', 'job')
            url = url.replace('{secret_ref}', 'secret_' + 'a'*32).replace('{connector_id}', 'resource')
            url = url.replace('{task_run_id}', 'task_' + 'a'*32)
            assert client.request(method, url, json={}).status_code == 401, (method, path)

# Inspect the explicit session composition without constructing a prototype
# gateway/provider or invoking its ticket, transport or hardware entrypoints.
assert {route.path for route in generic_session_api.router.routes} == {
    '/api/v1/interactive-sessions/ticket', '/api/v1/interactive-sessions/discovery',
    '/api/v1/interactive-sessions/ws', '/api/v1/devices/{device_id}/session-ticket',
    '/api/v1/devices/{device_id}/session-ws'}
assert {route.path for route in application_session_api.application_session_router(object()).routes} == {
    '/api/v1/application-extensions/{module_id}/session-recovery',
    '/api/v1/application-extensions/{module_id}/session-recovery/{session_id}/confirm-cleanup',
    '/api/v1/application-extensions/{module_id}/session-host/{entrypoint_id}',
    '/api/v1/application-extensions/{module_id}/session-host/{entrypoint_id}/ticket',
    '/api/v1/application-extensions/{module_id}/session-host/{entrypoint_id}/ws'}
import backend.main as core_main
assert Path(core_main.__file__).resolve().is_relative_to(root)
assert Path(core_main.app_settings.backend.uploads_dir).resolve() == root/'uploads'
client = TestClient(core_main.app)  # No lifespan: no database, workers or listeners.
for method, path in (
    ('post', '/api/v1/interactive-sessions/ticket'),
    ('get', '/api/v1/interactive-sessions/discovery'),
    ('post', '/api/v1/devices/dev_' + 'a'*32 + '/session-ticket'),
    ('get', '/api/v1/application-extensions/org.example.session-client/session-host/operations'),
    ('post', '/api/v1/application-extensions/org.example.session-client/session-host/operations/ticket')):
    assert client.request(method, path).status_code == 404, (method, path)
assert session_gateway._GATEWAY is None
assert session_agent._DEVICE_TICKETS is None
print("Extracted application runtime, resources and sessions: passed")
'''],
        cwd=extracted,
        env={key: value for key, value in {
            **os.environ, "DATABASE_URL": "sqlite://", "UPLOADS_DIR": str(extracted / "uploads")}.items()
             if key not in {"PYTHONPATH", "PYTHONHOME", "COMPILED_UI_COMPILER_SCRIPT",
                            "THREE_MM_LOCAL_SESSIONS", "THREE_MM_SESSION_LINKS"}},
        capture_output=True, text=True, timeout=30,
    )
    assert runtime_result.returncode == 0, (runtime_result.stdout, runtime_result.stderr)
    content_result = subprocess.run(
        [sys.executable, "-E", "-c", '''
from importlib.util import find_spec
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import backend.database
from backend.applications.files import authority as file_authority, transfers, api as file_api
from backend.applications.public_web import routes as public_routes, transport, guests, webhook_admission
from backend.applications.delegations import service as delegations, api as delegation_api
from backend.applications.kiosks import service as kiosks, api as kiosk_api
from backend.applications import checkpoints
from backend.applications.queries import configuration, transport as query_transport

root = Path.cwd().resolve()
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in (
    file_authority, transfers, file_api, public_routes, transport, guests, webhook_admission,
    delegations, delegation_api, kiosks, kiosk_api, checkpoints, configuration, query_transport))
for name in ('backend.routes', 'backend.services', 'backend.utils'):
    assert find_spec(name) is None, name
assert file_api.transfer_slot is transfers.transfer_slot
assert transfers.ApplicationFileAuthorityError is file_authority.ApplicationFileAuthorityError
assert file_api.ApplicationFileAuthorityError is file_authority.ApplicationFileAuthorityError
assert transport.public_form_guests is guests
assert webhook_admission.require_reviewed_webhook_route is public_routes.require_reviewed_webhook_route
assert delegation_api.service is delegations
assert kiosk_api.service is kiosks
assert kiosks.login_actor is delegations.login_actor
assert query_transport.QueryDispatch.__module__ == 'backend.applications.queries.transport'
assert query_transport.QueryRuntimeProbe.__module__ == 'backend.applications.queries.transport'

app = FastAPI()
prefix = '/api/v1/application-extensions'
for router in (file_api.router, delegation_api.router, kiosk_api.router):
    app.include_router(router, prefix=prefix)
expected = {
    '/{module_id}/files/control': {'post'},
    '/{module_id}/files/uploads/{upload_id}/chunks': {'post'},
    '/{module_id}/files/{file_id}/content': {'get'},
    '/{module_id}/files/{file_id}/chunks': {'get'},
    '/{module_id}/files/requests/{request_id}': {'get'},
    '/{module_id}/files/links/{link_id}/open': {'get'},
    '/{module_id}/files/links/{link_id}/content': {'post'},
    '/{module_id}/ui-host/{entrypoint_id}/access': {'get'},
    '/{module_id}/ui-host/{entrypoint_id}/delegations': {'post'},
    '/{module_id}/delegations/{delegation_id}': {'get'},
    '/{module_id}/delegations/{delegation_id}/cancel': {'post'},
    '/{module_id}/kiosk/enrollments': {'post'},
    '/{module_id}/kiosk/enrollments/claim': {'post'},
    '/{module_id}/kiosk/sessions': {'post'},
    '/{module_id}/kiosk/terminals': {'get'},
    '/{module_id}/kiosk/terminals/{terminal_id}': {'delete'}}
assert {path:set(methods) for path,methods in app.openapi()['paths'].items()} == {
    prefix+path:methods for path,methods in expected.items()}
base = prefix + '/org.example.missing'
binding = {'entrypoint_id':'main', 'artifact_sha256':'a'*64, 'built_ui_sha256':'b'*64}
with TestClient(app) as client:
    # Browser reads reject an anonymous actor before installation/key/runtime work.
    assert client.get(base+'/files/'+'c'*32+'/content', params=binding).status_code == 403
    assert client.get(base+'/files/requests/'+'c'*32, params=binding).status_code == 403
    # Delegation receipt readers and kiosk administration retain their login gate.
    assert client.get(base+'/delegations/'+'c'*32).status_code == 401
    assert client.post(base+'/delegations/'+'c'*32+'/cancel').status_code == 401
    assert client.get(base+'/kiosk/terminals').status_code == 401
    assert client.post(base+'/kiosk/enrollments', json={'request_id':'c'*32, 'label':'test'}).status_code == 401
    # These remain public proof/token endpoints, not blanket administrator APIs.
    link = client.get(base+'/files/links/'+'c'*32+'/open')
    assert link.status_code == 200 and 'File download' in link.text
    assert link.headers['Cache-Control'] == 'no-store'
    assert client.post(base+'/files/links/'+'c'*32+'/content', content=b'').status_code == 403
    assert client.post(base+'/kiosk/enrollments/claim', json={}).status_code == 422
    assert client.post(base+'/kiosk/sessions', json={}).status_code == 422
print("Extracted application files, public Web, delegations, kiosks and queries: passed")
'''],
        cwd=extracted,
        env={key: value for key, value in {**os.environ, "DATABASE_URL": "sqlite://"}.items()
             if key not in {"PYTHONPATH", "PYTHONHOME", "COMPILED_UI_COMPILER_SCRIPT"}},
        capture_output=True, text=True, timeout=30,
    )
    assert content_result.returncode == 0, (content_result.stdout, content_result.stderr)
    # Exercise the relocated package entrypoint from the built artifact, not
    # checkout imports. Its dependency environment is already installed.
    help_result = subprocess.run(
        [sys.executable, "-E", "-m", "components.public_web", "--help"],
        cwd=extracted,
        env={key: value for key, value in os.environ.items()
             if key not in {"PYTHONPATH", "PYTHONHOME"}},
        capture_output=True, text=True, timeout=15,
    )
    assert help_result.returncode == 0, (help_result.stdout, help_result.stderr)
    assert "--runtime-socket" in help_result.stdout
    authority_help = subprocess.run(
        [sys.executable, "-E", "-m", "backend.applications.authority.admin", "--help"],
        cwd=extracted,
        env={key:value for key,value in {**os.environ,"DATABASE_URL":"sqlite://"}.items()
             if key not in {"PYTHONPATH","PYTHONHOME"}},
        capture_output=True, text=True, timeout=15,
    )
    assert authority_help.returncode == 0, (authority_help.stdout,authority_help.stderr)
    assert "provision-key" in authority_help.stdout
    worker_help = subprocess.run(
        [sys.executable, "-E", "-m", "backend.applications.relational.admin_worker", "--help"],
        cwd=extracted,
        env={key:value for key,value in {**os.environ,"DATABASE_URL":"sqlite://"}.items()
             if key not in {"PYTHONPATH","PYTHONHOME"}},
        capture_output=True, text=True, timeout=15,
    )
    assert worker_help.returncode == 0, (worker_help.stdout,worker_help.stderr)
    assert "--core-uid" in worker_help.stdout


def test_admin_web_starts_from_extracted_release_without_checkout_imports(tmp_path):
    root = Path(__file__).resolve().parents[2]
    files = dict(REQUIRED_SOURCE_FILES)
    for name in (*ADMIN_WEB_FILES, "deployment/systemd/3mm-web.service"):
        files[name] = (root / name).read_bytes()
    write_source_archive(tmp_path / "source.tar", files)
    manifest = build(tmp_path, architectures=("x86_64",))
    extracted = tmp_path / "release"
    archive_path = tmp_path / "output" / manifest["artifacts"][0]["filename"]
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(extracted, filter="data")
    assert not (extracted / "three_mm_web").exists()
    unit = (extracted / "deployment/systemd/3mm-web.service").read_text()
    command = shlex.split(next(line.removeprefix("ExecStart=")
                              for line in unit.splitlines() if line.startswith("ExecStart=")))
    module = command[command.index("-m") + 1]
    # A real module launch with no site-packages or checkout PYTHONPATH. Keep
    # test listeners on loopback and an ephemeral port, never the installed UI.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME", "UPLOADS_DIR"}}
    with (tmp_path / "web.log").open("w+b") as log:
        process = subprocess.Popen(
            [sys.executable, "-E", "-S", "-m", module, "--host", "127.0.0.1",
             "--port", str(port), "--directory", str(extracted / "frontend/dist")],
            cwd=extracted, env=environment, stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/user/login", timeout=.5) as response:
                        assert response.status == 200
                        assert response.read() == (extracted / "frontend/dist/index.html").read_bytes()
                    break
                except URLError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        pytest.fail("Extracted admin web did not start: " + log.read().decode(errors="replace"))
                    time.sleep(.05)
            with urlopen(f"http://127.0.0.1:{port}/assets/main.js", timeout=2) as response:
                assert response.read() == (extracted / "frontend/dist/assets/main.js").read_bytes()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_builder_rejects_incomplete_target_owned_contract(tmp_path):
    files = dict(REQUIRED_SOURCE_FILES)
    contract = dict(TARGET_CONTRACT)
    contract["required_files"] = sorted(
        contract["required_files"] + ["deployment/systemd/future.service"]
    )
    files[CONTRACT_PATH] = json.dumps(contract).encode()
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match="future.service"):
        build(tmp_path)


@pytest.mark.parametrize(
    "required",
    [
        "packages/application_sdk/files.py",
        "packages/application_sdk/file_wire.py",
        "packages/application_sdk/scoped_files.py",
        "components/system_runtime/application_file_executor.py",
        "backend/applications/files/authority.py",
        "components/system_runtime/application_files_snapshot.py",
    ],
)
def test_builder_requires_the_sdk_private_file_adapter(tmp_path, required):
    files = dict(REQUIRED_SOURCE_FILES)
    del files[required]
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match=required):
        build(tmp_path)


@pytest.mark.parametrize("required", RELATIONAL_RELEASE_FILES)
def test_builder_requires_relational_lifecycle_and_boot_files(tmp_path, required):
    assert required in TARGET_CONTRACT["required_files"]
    files = dict(REQUIRED_SOURCE_FILES)
    del files[required]
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match=required):
        build(tmp_path)


def test_source_only_products_and_optional_libraries_are_excluded_from_release(tmp_path):
    files = dict(REQUIRED_SOURCE_FILES)
    files.update({
        "modules/example/.3mm-source-only": b"",
        "modules/example/source/service.py": b"raise AssertionError('product')",
        "libraries/optional/.3mm-source-only": b"",
        "libraries/optional/client.py": b"raise AssertionError('optional')",
        "modules/current/manifest.json": b"{}",
    })
    write_source_archive(tmp_path / "source.tar", files)
    names = {item.name for item in read_source_payload(tmp_path / "source.tar")}
    assert not any(name.startswith(("modules/example/", "libraries/optional/")) for name in names)
    assert "modules/current/manifest.json" in names
    assert {name for name in REQUIRED_SOURCE_FILES if not name.startswith("frontend/dist/")} <= names
    assert "frontend/dist/stale.js" not in names


@pytest.mark.parametrize("migration", ["4f29a071b819_application_result_tasks",
    "5a30b182c920_application_task_schedules", "6b41c293da31_retire_builder_automations", "7c52d3a4eb42_retire_dashboards", "8d63e4b5fc53_retire_declarative_crud", "9e74f5c60d64_retire_legacy_content", "af85a6d71e75_user_subject_ids", "b096b7e82f86_kiosk_incarnations"])
def test_release_requires_current_schema_chain(tmp_path, migration):
    files = dict(REQUIRED_SOURCE_FILES)
    files.pop(f"backend/alembic/versions/{migration}.py")
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match="missing required files"):
        read_source_payload(tmp_path / "source.tar")


@pytest.mark.parametrize("marker,content", [("backend/.3mm-source-only", b""),
    ("modules/x/.3mm-source-only", b"unexpected")])
def test_source_only_marker_cannot_remove_core_or_carry_code(tmp_path, marker, content):
    write_source_archive(tmp_path / "source.tar", {**REQUIRED_SOURCE_FILES, marker: content})
    with pytest.raises(ReleaseBuildError, match="Source-only marker"):
        read_source_payload(tmp_path / "source.tar")


def test_builder_rejects_version_mismatch(tmp_path: Path) -> None:
    files = dict(REQUIRED_SOURCE_FILES)
    files["VERSION"] = b"9.9.9\n"
    write_source_archive(tmp_path / "source.tar", files)
    write_frontend_dist(tmp_path / "dist")
    write_dependencies(tmp_path / "dependencies.json")

    with pytest.raises(ReleaseBuildError, match="does not match release"):
        build(tmp_path)


@pytest.mark.parametrize(
    "packages",
    [
        ["python3-venv", "curl"],
        ["curl", "curl"],
        ["curl", "bad package"],
        ["curl", 7],
    ],
)
def test_builder_rejects_unreviewable_dependency_lists(
    tmp_path: Path, packages: list[object]
) -> None:
    write_source_archive(tmp_path / "source.tar")
    write_frontend_dist(tmp_path / "dist")
    write_dependencies(tmp_path / "dependencies.json", packages)

    with pytest.raises(ReleaseBuildError, match="APT dependencies"):
        build(tmp_path)


def test_builder_requires_a_complete_frontend_dist(tmp_path: Path) -> None:
    write_source_archive(tmp_path / "source.tar")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<div></div>", encoding="utf-8")
    write_dependencies(tmp_path / "dependencies.json")

    with pytest.raises(ReleaseBuildError, match=r"assets/\*\.js"):
        build(tmp_path)


def test_tracked_release_dependencies_are_strict_and_reviewable() -> None:
    packages = read_dependencies(Path("deployment/release-dependencies.json"))
    allowlist = read_dependency_allowlist(
        Path("deployment/update-dependency-allowlist.json")
    )

    assert packages == sorted(packages)
    assert {"curl", "npm", "python3", "python3-venv", "util-linux"} <= set(packages)
    assert set(packages) <= allowlist


def test_release_workflow_publishes_only_complete_tagged_builds() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'tags:\n      - "v*.*.*"' in workflow
    assert "contents: write" in workflow
    assert "uses: actions/checkout@v7" in workflow
    assert "uses: actions/setup-python@v7" in workflow
    assert "uses: actions/setup-node@v6" in workflow
    assert 'git merge-base --is-ancestor "$COMMIT" origin/main' in workflow
    assert 'git cat-file -t "refs/tags/$TAG"' in workflow
    assert 'git rev-list -n 1 "$TAG"' in workflow
    assert 'Path("VERSION").read_text' in workflow
    assert "git archive --format=tar" in workflow
    assert "diff --recursive --brief" in workflow
    assert "--draft --verify-tag" in workflow
    assert workflow.index('gh release create "$TAG"') < workflow.index(
        'gh release edit "$TAG" --draft=false'
    )
    assert "workflow_dispatch" not in workflow


@pytest.mark.parametrize('required',[
    'backend/alembic/versions/1bf67d2435e6_event_runtime_claims.py',
    'backend/alembic/versions/2c078e3546f7_connector_dispatch.py',
    'backend/applications/connectors/broker.py',
    'backend/applications/connectors/transport.py',
    'backend/applications/runtime/responses.py',
    'backend/applications/runtime/status_probe.py',
    'backend/applications/runtime/health.py',
    'components/platform_runtime/events.py',
])
def test_builder_refuses_event_worker_without_matching_claim_migration(tmp_path,required):
    files=dict(REQUIRED_SOURCE_FILES);files.pop(required)
    write_source_archive(tmp_path/'source.tar',files)
    with pytest.raises(ReleaseBuildError,match=required):build(tmp_path)


@pytest.mark.parametrize('required', [
    'packages/application_sdk/discovery.py',
    'packages/protocol/application_requirements.py',
    'backend/applications/management/requirements.py',
    'backend/applications/resources/discovery.py',
    'backend/applications/resources/providers.py',
    'packages/protocol/application_resources.py',
])
def test_builder_refuses_an_incomplete_requirement_discovery_sdk(tmp_path, required):
    files = dict(REQUIRED_SOURCE_FILES); files.pop(required)
    write_source_archive(tmp_path / 'source.tar', files)
    with pytest.raises(ReleaseBuildError, match=required): build(tmp_path)
