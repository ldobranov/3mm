"""Declarative runtime-extension v1 contract shared by Core and its UI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from three_mm_protocol.module_manifest import MODULE_ID_PATTERN, SEMVER_PATTERN


IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
ROUTE_PATTERN = r"^/[a-z0-9][a-z0-9/_-]*$"


class StrictRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LocalizedTextV1(StrictRuntimeModel):
    en: str = Field(min_length=1, max_length=160)
    translations: dict[str, str] = Field(default_factory=dict)


class RuntimeFieldV1(StrictRuntimeModel):
    field_id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: LocalizedTextV1
    kind: Literal["text", "multiline", "integer", "number", "boolean", "date", "datetime"]
    required: bool = False
    read_only: bool = False


class RuntimeEntityV1(StrictRuntimeModel):
    entity_id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: LocalizedTextV1
    fields: tuple[RuntimeFieldV1, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_fields(self):
        field_ids = [field.field_id for field in self.fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("entity field IDs must be unique")
        return self


class RuntimePageV1(StrictRuntimeModel):
    page_id: str = Field(pattern=IDENTIFIER_PATTERN)
    path: str = Field(pattern=ROUTE_PATTERN, max_length=160)
    title: LocalizedTextV1
    entity_id: str = Field(pattern=IDENTIFIER_PATTERN)
    view: Literal["table", "form", "detail"]
    actions: tuple[Literal["create", "read", "update", "delete"], ...] = ("read",)
    requires_role: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_actions(self):
        if len(self.actions) != len(set(self.actions)):
            raise ValueError("page actions must be unique")
        return self


class RuntimeNavigationItemV1(StrictRuntimeModel):
    navigation_id: str = Field(pattern=IDENTIFIER_PATTERN)
    page_id: str = Field(pattern=IDENTIFIER_PATTERN)
    label: LocalizedTextV1
    icon: str | None = Field(default=None, pattern=r"^bi-[a-z0-9-]+$", max_length=80)
    order: int = Field(default=100, ge=0, le=10_000)


class RuntimeExtensionV1(StrictRuntimeModel):
    runtime_extension_version: Literal[1]
    module_id: str = Field(pattern=MODULE_ID_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    name: LocalizedTextV1
    description: LocalizedTextV1
    entities: tuple[RuntimeEntityV1, ...] = Field(min_length=1, max_length=32)
    pages: tuple[RuntimePageV1, ...] = Field(min_length=1, max_length=64)
    navigation: tuple[RuntimeNavigationItemV1, ...] = ()
    permissions: tuple[Literal["runtime.data.read", "runtime.data.write"], ...] = (
        "runtime.data.read",
    )

    @model_validator(mode="after")
    def validate_references_and_permissions(self):
        entity_ids = [entity.entity_id for entity in self.entities]
        page_ids = [page.page_id for page in self.pages]
        routes = [page.path for page in self.pages]
        navigation_ids = [item.navigation_id for item in self.navigation]

        for label, values in (
            ("entity IDs", entity_ids),
            ("page IDs", page_ids),
            ("page routes", routes),
            ("navigation IDs", navigation_ids),
            ("permissions", list(self.permissions)),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")

        known_entities = set(entity_ids)
        for page in self.pages:
            if page.entity_id not in known_entities:
                raise ValueError(f"page references unknown entity: {page.entity_id}")

        known_pages = set(page_ids)
        for item in self.navigation:
            if item.page_id not in known_pages:
                raise ValueError(f"navigation references unknown page: {item.page_id}")

        has_write_action = any(
            action in {"create", "update", "delete"}
            for page in self.pages
            for action in page.actions
        )
        if has_write_action and "runtime.data.write" not in self.permissions:
            raise ValueError("write actions require runtime.data.write permission")
        return self
