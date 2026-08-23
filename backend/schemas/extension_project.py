from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProjectType = Literal["extension", "widget"]
ProjectStatus = Literal["draft", "built", "installed", "failed"]
ChangeKind = Literal["patch", "minor", "major", "prerelease"]


class ProjectFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=500_000)
    model_config = ConfigDict(extra="forbid")


class CreateExtensionProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=120)
    project_type: ProjectType
    spec: dict = Field(default_factory=dict)
    files: list[ProjectFileInput] = Field(default_factory=list, max_length=200)
    model_config = ConfigDict(extra="forbid")


class UpdateExtensionProjectRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    spec: dict | None = None
    status: ProjectStatus | None = None
    model_config = ConfigDict(extra="forbid")


class ReplaceProjectFilesRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    files: list[ProjectFileInput] = Field(max_length=200)
    model_config = ConfigDict(extra="forbid")


class CreateProjectBuildRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    change_kind: ChangeKind = "patch"
    change_request: str | None = Field(default=None, max_length=10_000)
    status: Literal["built", "failed"] = "built"
    report: dict = Field(default_factory=dict)
    artifact_base64: str | None = Field(default=None, max_length=14_000_000)
    model_config = ConfigDict(extra="forbid")


class MarkProjectBuildInstalledRequest(BaseModel):
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid")


class ModifyExtensionProjectRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    change_request: str = Field(min_length=1, max_length=10_000)
    ai_provider: Literal["auto", "groq", "openrouter"] = "auto"
    model: str | None = Field(default=None, max_length=160)
    model_config = ConfigDict(extra="forbid")


class ModifyExtensionProjectResponse(BaseModel):
    project_id: str
    base_revision: int
    changed_files: list[str]
    proposed_files: dict[str, str]
    diffs: dict[str, str]
    warnings: list[dict]
    model_config = ConfigDict(extra="forbid")


class ProjectFileResponse(BaseModel):
    path: str
    content: str
    sha256: str
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ExtensionProjectSummaryResponse(BaseModel):
    project_id: str
    name: str
    slug: str
    project_type: str
    status: str
    current_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ExtensionProjectResponse(ExtensionProjectSummaryResponse):
    owner_user_id: int
    spec: dict
    files: list[ProjectFileResponse]


class ProjectBuildResponse(BaseModel):
    build_id: str
    version: str
    status: str
    change_kind: str
    change_request: str | None
    spec_snapshot: dict
    files_snapshot: dict
    report: dict
    artifact_sha256: str | None
    has_artifact: bool = False
    package_kind: str | None
    installed_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")
