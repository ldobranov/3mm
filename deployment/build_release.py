#!/usr/bin/env python3
"""Build deterministic, architecture-specific 3mm release archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Iterable

SUPPORTED_ARCHITECTURES = ("aarch64", "armv7l", "x86_64")
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

    required = {
        "VERSION",
        "install.sh",
        "backend/requirements.txt",
        "backend/services/update_staging.py",
        "deployment/apply_staged_update.py",
        "deployment/install-systemd.sh",
        "deployment/migrate_database.py",
        "deployment/update-dependency-allowlist.json",
        "deployment/systemd/3mm-agent.service",
        "deployment/systemd/3mm-core.service",
        "deployment/systemd/3mm-update-helper.service",
        "deployment/systemd/3mm-web.service",
        "frontend/compiler/package.json",
        "three_mm_runtime/update_helper.py",
    }
    missing = sorted(required - names)
    if missing:
        raise ReleaseBuildError(
            f"Source archive is missing required files: {', '.join(missing)}"
        )
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
            payload,
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
        "artifacts": artifacts,
        "dependencies": {"apt_packages": packages},
    }
    manifest_file = output_dir / "3mm-update-manifest.json"
    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


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
        )
    except ReleaseBuildError as exc:
        raise SystemExit(f"Release build failed: {exc}") from exc
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
