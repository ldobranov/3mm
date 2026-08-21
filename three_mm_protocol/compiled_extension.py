"""Source contract for install-time compiled UI extensions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN
from three_mm_protocol.runtime_extension import IDENTIFIER_PATTERN, LocalizedTextV1, ROUTE_PATTERN


class StrictCompiledUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompiledUiEntrypointV1(StrictCompiledUiModel):
    entrypoint_id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: Literal["widget", "route", "editor", "component"]
    source: str = Field(min_length=1, max_length=240)
    label: LocalizedTextV1
    route: str | None = Field(default=None, pattern=ROUTE_PATTERN, max_length=160)
    target_entrypoint_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    requires_role: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_kind_and_source(self):
        normalized = self.source.replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/")
            or ".." in parts
            or not normalized.startswith("source/frontend/")
            or not normalized.endswith(".vue")
        ):
            raise ValueError("compiled UI source must be a safe .vue file under source/frontend")
        if (self.kind == "route") != (self.route is not None):
            raise ValueError("route entrypoints require route and other entrypoints forbid it")
        if (self.kind == "editor") != (self.target_entrypoint_id is not None):
            raise ValueError(
                "editor entrypoints require target_entrypoint_id and other entrypoints forbid it"
            )
        return self


class CompiledUiExtensionV1(StrictCompiledUiModel):
    compiled_ui_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    entrypoints: tuple[CompiledUiEntrypointV1, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_entrypoints(self):
        entrypoint_ids = [item.entrypoint_id for item in self.entrypoints]
        sources = [item.source.replace("\\", "/") for item in self.entrypoints]
        routes = [item.route for item in self.entrypoints if item.route is not None]
        for label, values in (
            ("entrypoint IDs", entrypoint_ids),
            ("entrypoint sources", sources),
            ("entrypoint routes", routes),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")

        kinds = {item.entrypoint_id: item.kind for item in self.entrypoints}
        for item in self.entrypoints:
            if item.kind == "editor" and kinds.get(item.target_entrypoint_id) != "widget":
                raise ValueError("editor target_entrypoint_id must reference a widget entrypoint")
        return self
