"""Admin API for persistent AI extension projects and their build history."""

import base64
import binascii
import hashlib
import difflib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.db.extension_project import ExtensionProject, ExtensionProjectBuild, ExtensionProjectFile
from backend.db.user import User
from backend.schemas.extension_project import (
    CreateExtensionProjectRequest,
    CreateProjectBuildRequest,
    ExtensionProjectResponse,
    ExtensionProjectSummaryResponse,
    ModifyExtensionProjectRequest,
    ModifyExtensionProjectResponse,
    MarkProjectBuildInstalledRequest,
    ProjectBuildResponse,
    ReplaceProjectFilesRequest,
    UpdateExtensionProjectRequest,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from backend.db.settings import Settings
from backend.schemas.ai_extension_builder import ExtensionSpec
from backend.utils.ai_extension_builder.generator import _ai_refine_files
from backend.utils.secure_settings import SecureSettingsError, decrypt_secret
from backend.config import get_settings


router = APIRouter(prefix="/api/v1/extension-projects", tags=["extension-projects"])
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-dev\.(\d+))?$")
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not result or not SLUG_PATTERN.fullmatch(result):
        raise HTTPException(422, "Project slug must contain lowercase letters, numbers, and single hyphens")
    return result


def _safe_files(files) -> list[tuple[str, str, str]]:
    result = []
    seen = set()
    for item in files:
        path = item.path.replace("\\", "/").lstrip("/")
        if not path or ".." in path.split("/") or path in seen:
            raise HTTPException(422, f"Invalid or duplicate project file path: {item.path}")
        seen.add(path)
        digest = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        result.append((path, item.content, digest))
    return result


def _project(db: Session, project_id: str) -> ExtensionProject:
    row = db.scalar(
        select(ExtensionProject)
        .options(selectinload(ExtensionProject.files))
        .where(ExtensionProject.project_id == project_id)
    )
    if row is None:
        raise HTTPException(404, "Extension project was not found")
    return row


def _assert_revision(project: ExtensionProject, expected: int) -> None:
    if project.revision != expected:
        raise HTTPException(409, f"Project changed since it was opened; current revision is {project.revision}")


def _next_version(current: str, kind: str) -> str:
    match = SEMVER_PATTERN.fullmatch(current)
    if not match:
        raise HTTPException(409, "Project current version is invalid")
    major, minor, patch = map(int, match.group(1, 2, 3))
    dev = int(match.group(4)) if match.group(4) else None
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "prerelease":
        return f"{major}.{minor}.{patch}-dev.{(dev or 0) + 1}" if dev else f"{major}.{minor}.{patch + 1}-dev.1"
    return f"{major}.{minor}.{patch + 1}"


def _artifact(payload: str | None) -> tuple[bytes | None, str | None]:
    if payload is None:
        return None, None
    try:
        content = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "Build artifact is not valid base64") from exc
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise HTTPException(422, "Build artifact must be a non-empty ZIP up to 10 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names:
                raise HTTPException(422, "Build artifact is missing manifest.json")
            manifest = json.loads(archive.read("manifest.json"))
            is_compiled = (
                manifest.get("manifest_version") == 2
                and (manifest.get("entrypoints") or {}).get("ui") == "compiled-ui.json"
            )
    except HTTPException:
        raise
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Build artifact is not a valid extension ZIP") from exc
    return content, "compiled" if is_compiled else "legacy"


def _build_response(build: ExtensionProjectBuild) -> ProjectBuildResponse:
    return ProjectBuildResponse.model_validate(build, from_attributes=True).model_copy(
        update={"has_artifact": bool(build.artifact_path)}
    )


@router.post("", response_model=ExtensionProjectResponse, status_code=201)
def create_project(
    payload: CreateExtensionProjectRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = ExtensionProject(
        project_id=f"extproj_{uuid.uuid4().hex}",
        owner_user_id=admin.id,
        name=payload.name.strip(),
        slug=_slug(payload.slug or payload.name),
        project_type=payload.project_type,
        spec=payload.spec,
        status="draft",
        current_version="0.0.0",
        revision=1,
    )
    for path, content, digest in _safe_files(payload.files):
        project.files.append(ExtensionProjectFile(path=path, content=content, sha256=digest))
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "An extension project with this slug already exists") from exc
    return _project(db, project.project_id)


@router.get("", response_model=list[ExtensionProjectSummaryResponse])
def list_projects(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    statement = select(ExtensionProject).order_by(ExtensionProject.updated_at.desc(), ExtensionProject.id.desc())
    if status:
        statement = statement.where(ExtensionProject.status == status)
    return list(db.scalars(statement.limit(limit)).all())


@router.get("/{project_id}", response_model=ExtensionProjectResponse)
def read_project(project_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _project(db, project_id)


@router.get("/{project_id}/next-version")
def read_next_version(
    project_id: str,
    change_kind: str = Query(default="patch", pattern="^(patch|minor|major|prerelease)$"),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    return {
        "current_version": project.current_version,
        "next_version": _next_version(project.current_version, change_kind),
        "change_kind": change_kind,
    }


@router.post("/{project_id}/modify", response_model=ModifyExtensionProjectResponse)
def propose_project_modification(
    project_id: str,
    payload: ModifyExtensionProjectRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    _assert_revision(project, payload.expected_revision)
    stored = project.spec or {}
    raw_spec = stored.get("extension_spec", stored)
    try:
        spec = ExtensionSpec.model_validate(raw_spec)
    except Exception as exc:
        raise HTTPException(409, "Project extension spec is invalid and must be repaired before AI modification") from exc

    current_files = {item.path: item.content for item in project.files}
    if not current_files:
        raise HTTPException(409, "Generate or add project source files before requesting a modification")
    protected = {"manifest.json", "compiled-ui.json"}
    editable_files = {path: content for path, content in current_files.items() if path not in protected}
    if not editable_files:
        raise HTTPException(409, "Project does not contain editable source files")

    def setting(key: str) -> str | None:
        row = db.scalar(select(Settings).where(
            Settings.key == key,
            Settings.language_code.is_(None),
            Settings.user_id.is_(None),
        ))
        return row.value if row else None

    configured_provider = (setting("ai_provider") or "").strip().lower() or None
    provider = payload.ai_provider if payload.ai_provider != "auto" else configured_provider
    try:
        groq_key = decrypt_secret(setting("ai_groq_api_key")) if setting("ai_groq_api_key") else None
        openrouter_key = decrypt_secret(setting("ai_openrouter_api_key")) if setting("ai_openrouter_api_key") else None
    except SecureSettingsError as exc:
        raise HTTPException(500, f"AI settings decryption is not configured: {exc}") from exc

    instructions = payload.change_request
    if "compiled-ui.json" in current_files:
        instructions += (
            "\n\nThis is an install-time compiled Vue package. Preserve existing component props/events, "
            "import only from 'vue' or relative project files, and do not assume access to Core source aliases."
        )
    updates, warnings = _ai_refine_files(
        spec, instructions, editable_files, payload.model, provider, groq_key, openrouter_key
    )
    changed = sorted(path for path, content in updates.items() if content != current_files.get(path))
    proposed = {**current_files, **{path: updates[path] for path in changed}}
    diffs = {
        path: "".join(difflib.unified_diff(
            current_files[path].splitlines(keepends=True),
            proposed[path].splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
        for path in changed
    }
    return ModifyExtensionProjectResponse(
        project_id=project.project_id,
        base_revision=project.revision,
        changed_files=changed,
        proposed_files=proposed,
        diffs=diffs,
        warnings=[warning.model_dump(mode="json") for warning in warnings],
    )


@router.patch("/{project_id}", response_model=ExtensionProjectResponse)
def update_project(
    project_id: str,
    payload: UpdateExtensionProjectRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    _assert_revision(project, payload.expected_revision)
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.spec is not None:
        project.spec = payload.spec
    if payload.status is not None:
        project.status = payload.status
    project.revision += 1
    db.commit()
    return _project(db, project_id)


@router.put("/{project_id}/files", response_model=ExtensionProjectResponse)
def replace_project_files(
    project_id: str,
    payload: ReplaceProjectFilesRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    _assert_revision(project, payload.expected_revision)
    project.files.clear()
    # Flush orphan deletes before inserting replacement rows with the same
    # (project_id, path) unique key. SQLite may otherwise insert first and
    # reject an ordinary edit as a duplicate project file.
    db.flush()
    for path, content, digest in _safe_files(payload.files):
        project.files.append(ExtensionProjectFile(path=path, content=content, sha256=digest))
    project.status = "draft"
    project.revision += 1
    db.commit()
    return _project(db, project_id)


@router.post("/{project_id}/builds", response_model=ProjectBuildResponse, status_code=201)
def create_build(
    project_id: str,
    payload: CreateProjectBuildRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    _assert_revision(project, payload.expected_revision)
    version = _next_version(project.current_version, payload.change_kind)
    if payload.status != "failed":
        exists = db.scalar(select(ExtensionProjectBuild.id).where(
            ExtensionProjectBuild.project_id == project.id,
            ExtensionProjectBuild.version == version,
            ExtensionProjectBuild.status != "failed",
        ))
        if exists is not None:
            raise HTTPException(409, "This project version already has a successful build")
    files_snapshot = {item.path: item.content for item in project.files}
    artifact, package_kind = _artifact(payload.artifact_base64)
    build_id = f"extbuild_{uuid.uuid4().hex}"
    artifact_path = None
    artifact_sha256 = hashlib.sha256(artifact).hexdigest() if artifact else None
    if artifact:
        artifact_dir = Path(get_settings().backend.uploads_dir) / "extension-project-builds" / project.project_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{build_id}.zip"
        artifact_path.write_bytes(artifact)
    build = ExtensionProjectBuild(
        build_id=build_id, project_id=project.id, version=version,
        status=payload.status, change_kind=payload.change_kind, change_request=payload.change_request,
        spec_snapshot=project.spec, files_snapshot=files_snapshot, report=payload.report,
        artifact_sha256=artifact_sha256, artifact_path=str(artifact_path) if artifact_path else None,
        package_kind=package_kind, created_by_user_id=admin.id,
    )
    db.add(build)
    project.status = payload.status
    if payload.status != "failed":
        project.current_version = version
    project.revision += 1
    db.commit()
    db.refresh(build)
    return _build_response(build)


@router.get("/{project_id}/builds", response_model=list[ProjectBuildResponse])
def list_builds(
    project_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    builds = list(db.scalars(select(ExtensionProjectBuild).where(
        ExtensionProjectBuild.project_id == project.id
    ).order_by(ExtensionProjectBuild.created_at.desc(), ExtensionProjectBuild.id.desc())).all())
    return [_build_response(build) for build in builds]


@router.get("/{project_id}/builds/{build_id}/artifact")
def download_build_artifact(
    project_id: str,
    build_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    build = db.scalar(select(ExtensionProjectBuild).where(
        ExtensionProjectBuild.project_id == project.id,
        ExtensionProjectBuild.build_id == build_id,
    ))
    if build is None:
        raise HTTPException(404, "Project build was not found")
    artifact = Path(build.artifact_path) if build.artifact_path else None
    if artifact is None or not artifact.is_file():
        raise HTTPException(404, "This build has no stored artifact")
    return FileResponse(artifact, media_type="application/zip", filename=f"{project.slug}-{build.version}.zip")


@router.post("/{project_id}/builds/{build_id}/installed", response_model=ProjectBuildResponse)
def mark_build_installed(
    project_id: str,
    build_id: str,
    payload: MarkProjectBuildInstalledRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    build = db.scalar(select(ExtensionProjectBuild).where(
        ExtensionProjectBuild.project_id == project.id,
        ExtensionProjectBuild.build_id == build_id,
    ))
    if build is None:
        raise HTTPException(404, "Project build was not found")
    if not build.artifact_path or not Path(build.artifact_path).is_file():
        raise HTTPException(409, "A build without a stored artifact cannot be marked installed")
    if payload.artifact_sha256 != build.artifact_sha256:
        raise HTTPException(409, "The installed artifact does not match this immutable build")
    for previous in db.scalars(select(ExtensionProjectBuild).where(
        ExtensionProjectBuild.project_id == project.id,
        ExtensionProjectBuild.status == "installed",
        ExtensionProjectBuild.id != build.id,
    )):
        previous.status = "built"
        previous.installed_at = None
    build.status = "installed"
    build.installed_at = datetime.now(timezone.utc)
    project.status = "installed"
    project.current_version = build.version
    project.revision += 1
    db.commit()
    db.refresh(build)
    return _build_response(build)
