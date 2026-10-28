from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from backend.services.system_updates import UpdateManifest, read_current_release
from backend.services.update_staging import read_dependency_allowlist
from deployment.build_release import (
    ReleaseBuildError,
    build_release_assets,
    read_dependencies,
    read_source_payload,
)
from deployment.deployment_contract import CONTRACT_PATH

COMMIT = "a" * 40
EPOCH = 1_787_728_000
REQUIRED_SOURCE_FILES = {
    "VERSION": b"1.2.0\n",
    "install.sh": b"#!/usr/bin/env bash\n",
    "backend/requirements.txt": b"fastapi==0.141.1\n",
    "backend/services/update_staging.py": b"print('stage')\n",
    "backend/services/application_public_web.py": b"print('public registry')\n",
    "backend/services/application_public_web_transport.py": b"print('public gateway')\n",
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
    "three_mm_runtime/update_helper.py": b"print('helper')\n",
    "three_mm_runtime/application_activation.py": b"print('activate app')\n",
    "three_mm_runtime/application_host.py": b"print('host app')\n",
    "three_mm_runtime/application_host_identity.py": b"# host metadata\n",
    "deployment/application_host_component.py": b"# host component\n",
    "deployment/application-host-contract.json": Path("deployment/application-host-contract.json").read_bytes(),
    "deployment/application-host-requirements.txt": Path("deployment/application-host-requirements.txt").read_bytes(),
    "three_mm_runtime/application_transport.py": b"print('transport app')\n",
    "three_mm_public_web/__init__.py": b"# public web\n",
    "three_mm_public_web/__main__.py": b"print('public main')\n",
    "three_mm_public_web/server.py": b"print('public server')\n",
    "three_mm_application_sdk/__init__.py": b"# sdk\n",
    'deployment/platform-runtime-contract.json': Path("deployment/platform-runtime-contract.json").read_bytes(),
    'deployment/platform_runtime_component.py': b"# component fixture\n",
    'deployment/systemd/3mm-platform-runtime.service': b"# component fixture\n",
    'three_mm_platform_wire/__init__.py': b"# component fixture\n",
    'three_mm_platform_runtime/__init__.py': b"# component fixture\n",
    'three_mm_platform_runtime/__main__.py': b"# component fixture\n",
    'three_mm_platform_runtime/server.py': b"# component fixture\n",
    'three_mm_platform_runtime/public_web.py': b"# component fixture\n",
    'three_mm_platform_runtime/events.py': b"# component fixture\n",
    'three_mm_platform_runtime/responses.py': b"# component fixture\n",
    'three_mm_platform_runtime/connector_worker.py': b"# component fixture\n",
    'deployment/systemd/3mm-connector-worker.service': b"# component fixture\n",
    "frontend/dist/stale.js": b"must not survive\n",
}
TARGET_CONTRACT = json.loads(Path(CONTRACT_PATH).read_text(encoding="utf-8"))
RELATIONAL_RELEASE_FILES = (
    "backend/services/application_authority_admin.py",
    "backend/services/application_platform.py",
    "backend/services/application_relational.py",
    "backend/services/application_relational_activation.py",
    "backend/services/application_relational_activation_recovery.py",
    "backend/services/application_relational_admin_worker.py",
    "backend/services/application_relational_boot.py",
    "backend/services/application_relational_candidate.py",
    "backend/services/application_relational_lifecycle.py",
    "backend/services/application_relational_namespace_recovery.py",
    "backend/services/application_relational_preparation_recovery.py",
    "backend/services/application_relational_reactivation.py",
    "backend/services/application_relational_recovery.py",
    "backend/services/application_relational_recovery_confirmation.py",
    "backend/services/application_relational_registration.py",
    "backend/services/application_relational_startup.py",
    "backend/services/application_relational_upgrade.py",
    "backend/services/application_relational_upgrade_admin.py",
    "backend/services/application_relational_upgrade_cli.py",
    "backend/services/application_relational_upgrade_confirmation.py",
    "backend/services/application_relational_upgrade_rollback.py",
    "three_mm_application_sdk/relational_preparation_recovery_wire.py",
    "three_mm_application_sdk/relational_receipts.py",
    "three_mm_application_sdk/relational_upgrade_receipts.py",
    "three_mm_application_sdk/relational_upgrade_wire.py",
    "three_mm_application_sdk/relational_wire.py",
    "three_mm_runtime/application_database_snapshot.py",
    "three_mm_runtime/application_relational_activation.py",
    "three_mm_runtime/application_relational_activation_recovery.py",
    "three_mm_runtime/application_relational_boot.py",
    "three_mm_runtime/application_relational_boot_policy.py",
    "three_mm_runtime/application_relational_control.py",
    "three_mm_runtime/application_relational_installation.py",
    "three_mm_runtime/application_relational_migrations.py",
    "three_mm_runtime/application_relational_namespace.py",
    "three_mm_runtime/application_relational_namespace_recovery.py",
    "three_mm_runtime/application_relational_preparation.py",
    "three_mm_runtime/application_relational_preparation_recovery.py",
    "three_mm_runtime/application_relational_preparation_recovery_control.py",
    "three_mm_runtime/application_relational_reactivation.py",
    "three_mm_runtime/application_relational_recovery.py",
    "three_mm_runtime/application_relational_recovery_confirmation.py",
    "three_mm_runtime/application_relational_runtime.py",
    "three_mm_runtime/application_relational_session.py",
    "three_mm_runtime/application_relational_startup.py",
    "three_mm_runtime/application_relational_upgrade.py",
    "three_mm_runtime/application_relational_upgrade_confirmation.py",
    "three_mm_runtime/application_relational_upgrade_control.py",
    "three_mm_runtime/application_relational_upgrade_restore.py",
    "three_mm_runtime/application_relational_upgrade_rollback.py",
    "three_mm_runtime/update_helper_client.py",
)
REQUIRED_SOURCE_FILES[CONTRACT_PATH] = json.dumps(TARGET_CONTRACT).encode()
for migration in ("4f29a071b819_application_result_tasks", "5a30b182c920_application_task_schedules",
        "6b41c293da31_retire_builder_automations", "7c52d3a4eb42_retire_dashboards", "8d63e4b5fc53_retire_declarative_crud", "9e74f5c60d64_retire_legacy_content", "af85a6d71e75_user_subject_ids", "b096b7e82f86_kiosk_incarnations"):
    REQUIRED_SOURCE_FILES[f"backend/alembic/versions/{migration}.py"] = b"# migration fixture\n"
REQUIRED_SOURCE_FILES["three_mm_protocol/ui_metadata.py"] = b"# shared UI metadata fixture\n"
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


def build(tmp_path: Path, output_name: str = "output") -> dict[str, object]:
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
        architectures=("aarch64", "x86_64"),
        source_date_epoch=EPOCH,
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
            assert "three_mm_public_web/server.py" in names
            assert "three_mm_application_sdk/files.py" in names
            assert "three_mm_application_sdk/file_wire.py" in names
            assert "three_mm_application_sdk/scoped_files.py" in names
            assert "three_mm_runtime/application_file_executor.py" in names
            assert "backend/services/application_files.py" in names
            assert "three_mm_runtime/application_files_snapshot.py" in names
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
        "three_mm_application_sdk/files.py",
        "three_mm_application_sdk/file_wire.py",
        "three_mm_application_sdk/scoped_files.py",
        "three_mm_runtime/application_file_executor.py",
        "backend/services/application_files.py",
        "three_mm_runtime/application_files_snapshot.py",
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
    'backend/services/application_connectors.py',
    'backend/services/application_connector_transport.py',
    'backend/services/application_response_relay.py',
    'backend/services/application_status_probe.py',
    'backend/services/application_health_probe.py',
    'three_mm_platform_runtime/events.py',
])
def test_builder_refuses_event_worker_without_matching_claim_migration(tmp_path,required):
    files=dict(REQUIRED_SOURCE_FILES);files.pop(required)
    write_source_archive(tmp_path/'source.tar',files)
    with pytest.raises(ReleaseBuildError,match=required):build(tmp_path)


@pytest.mark.parametrize('required', [
    'three_mm_application_sdk/discovery.py',
    'three_mm_protocol/application_requirements.py',
    'backend/services/application_requirements.py',
    'backend/services/application_resource_discovery.py',
    'backend/services/application_resource_providers.py',
    'three_mm_protocol/application_resources.py',
])
def test_builder_refuses_an_incomplete_requirement_discovery_sdk(tmp_path, required):
    files = dict(REQUIRED_SOURCE_FILES); files.pop(required)
    write_source_archive(tmp_path / 'source.tar', files)
    with pytest.raises(ReleaseBuildError, match=required): build(tmp_path)
