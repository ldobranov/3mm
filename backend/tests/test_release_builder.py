from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from backend.services.system_updates import UpdateManifest, read_current_release
from deployment.build_release import (
    ReleaseBuildError,
    build_release_assets,
    read_dependencies,
)

COMMIT = "a" * 40
EPOCH = 1_787_728_000
REQUIRED_SOURCE_FILES = {
    "VERSION": b"1.2.0\n",
    "backend/requirements.txt": b"fastapi==0.141.1\n",
    "deployment/install-systemd.sh": b"#!/usr/bin/env bash\n",
    "deployment/migrate_database.py": b"print('migrate')\n",
    "deployment/systemd/3mm-agent.service": b"[Unit]\n",
    "deployment/systemd/3mm-core.service": b"[Unit]\n",
    "deployment/systemd/3mm-web.service": b"[Unit]\n",
    "frontend/compiler/package.json": b'{"name":"compiler"}\n',
    "frontend/dist/stale.js": b"must not survive\n",
}


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

    assert packages == sorted(packages)
    assert {"curl", "npm", "python3", "python3-venv", "util-linux"} <= set(packages)


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
