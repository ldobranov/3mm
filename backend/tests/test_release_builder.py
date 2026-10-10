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
    "three_mm_runtime/application_transport.py": b"print('transport app')\n",
    "three_mm_public_web/__init__.py": b"# public web\n",
    "three_mm_public_web/__main__.py": b"print('public main')\n",
    "three_mm_public_web/server.py": b"print('public server')\n",
    "three_mm_application_sdk/__init__.py": b"# sdk\n",
    "frontend/dist/stale.js": b"must not survive\n",
}
TARGET_CONTRACT = json.loads(Path(CONTRACT_PATH).read_text(encoding="utf-8"))
REQUIRED_SOURCE_FILES[CONTRACT_PATH] = json.dumps(TARGET_CONTRACT).encode()
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


@pytest.mark.parametrize("required", [
    "three_mm_application_sdk/files.py",
    "three_mm_application_sdk/file_wire.py",
    "three_mm_application_sdk/scoped_files.py",
    "three_mm_runtime/application_file_executor.py",
    "backend/services/application_files.py",
    "three_mm_runtime/application_files_snapshot.py",
])
def test_builder_requires_the_sdk_private_file_adapter(tmp_path, required):
    files = dict(REQUIRED_SOURCE_FILES)
    del files[required]
    write_source_archive(tmp_path / "source.tar", files)
    with pytest.raises(ReleaseBuildError, match=required):
        build(tmp_path)


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
