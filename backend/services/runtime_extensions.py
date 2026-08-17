from datetime import date, datetime
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.runtime_extension import RuntimeExtensionDefinition
from backend.db.audit_log import AuditLog
from backend.db.user import User
from three_mm_protocol import RuntimeEntityV1, RuntimeExtensionV1


RuntimeAction = Literal["create", "read", "update", "delete"]
RESERVED_RUNTIME_PATH_PREFIXES = (
    "/user",
    "/settings",
    "/security",
    "/users",
    "/dashboard",
    "/extensions",
    "/automations",
)


def ensure_routes_available(
    db: Session, definition: RuntimeExtensionV1
) -> None:
    requested_paths = {page.path for page in definition.pages}
    reserved = sorted(
        path
        for path in requested_paths
        if any(
            path == prefix or path.startswith(f"{prefix}/")
            for prefix in RESERVED_RUNTIME_PATH_PREFIXES
        )
    )
    if reserved:
        raise HTTPException(409, f"runtime route is reserved by Core: {reserved[0]}")

    other_definitions = db.scalars(
        select(RuntimeExtensionDefinition).where(
            RuntimeExtensionDefinition.enabled.is_(True),
            RuntimeExtensionDefinition.module_id != definition.module_id,
        )
    )
    for other in other_definitions:
        other_paths = {
            page.path for page in RuntimeExtensionV1.model_validate(other.definition).pages
        }
        conflict = sorted(requested_paths & other_paths)
        if conflict:
            raise HTTPException(
                409,
                f"runtime route is already active for {other.module_id}: {conflict[0]}",
            )


def activate_definition(
    db: Session, definition: RuntimeExtensionV1, actor: User
) -> RuntimeExtensionDefinition:
    ensure_routes_available(db, definition)
    stored = definition.model_dump(mode="json")
    existing = db.scalar(
        select(RuntimeExtensionDefinition).where(
            RuntimeExtensionDefinition.module_id == definition.module_id,
            RuntimeExtensionDefinition.version == definition.version,
        )
    )
    if existing is not None and existing.definition != stored:
        raise HTTPException(409, "published runtime extension versions are immutable")

    db.query(RuntimeExtensionDefinition).filter(
        RuntimeExtensionDefinition.module_id == definition.module_id
    ).update(
        {
            RuntimeExtensionDefinition.enabled: False,
            RuntimeExtensionDefinition.is_selected: False,
        }
    )

    record = existing or RuntimeExtensionDefinition(
        module_id=definition.module_id,
        version=definition.version,
        definition=stored,
        enabled=True,
        is_selected=True,
        created_by=actor.id,
    )
    record.enabled = True
    record.is_selected = True
    db.add(record)
    db.flush()
    db.add(
        AuditLog(
            user_id=actor.id,
            action="CREATE" if existing is None else "UPDATE",
            entity_type="runtime_extension",
            entity_id=record.id,
            entity_name=f"{definition.module_id}@{definition.version}",
            changes={"enabled": True},
        )
    )
    db.commit()
    db.refresh(record)
    return record


def active_definition(db: Session, module_id: str) -> RuntimeExtensionDefinition:
    record = db.scalar(
        select(RuntimeExtensionDefinition).where(
            RuntimeExtensionDefinition.module_id == module_id,
            RuntimeExtensionDefinition.enabled.is_(True),
        )
    )
    if record is None:
        raise HTTPException(404, "active runtime extension was not found")
    return record


def parsed_definition(record: RuntimeExtensionDefinition) -> RuntimeExtensionV1:
    return RuntimeExtensionV1.model_validate(record.definition)


def entity_contract(definition: RuntimeExtensionV1, entity_id: str) -> RuntimeEntityV1:
    entity = next((item for item in definition.entities if item.entity_id == entity_id), None)
    if entity is None:
        raise HTTPException(404, "runtime entity was not found")
    return entity


def authorize_action(
    definition: RuntimeExtensionV1, entity_id: str, action: RuntimeAction, role: str
) -> None:
    accessible_pages = [
        page
        for page in definition.pages
        if page.entity_id == entity_id
        and (page.requires_role is None or page.requires_role == role)
    ]
    if not any(action in page.actions for page in accessible_pages):
        raise HTTPException(403, f"runtime action is not allowed: {action}")

    required_permission = (
        "runtime.data.read" if action == "read" else "runtime.data.write"
    )
    if required_permission not in definition.permissions:
        raise HTTPException(403, f"runtime permission is not declared: {required_permission}")


def validate_record_data(
    entity: RuntimeEntityV1, payload: dict[str, Any], *, partial: bool
) -> dict[str, Any]:
    fields = {field.field_id: field for field in entity.fields}
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        raise HTTPException(422, f"unknown runtime fields: {', '.join(unknown)}")

    if not partial:
        missing = sorted(
            field.field_id
            for field in entity.fields
            if field.required and not field.read_only and field.field_id not in payload
        )
        if missing:
            raise HTTPException(422, f"required runtime fields are missing: {', '.join(missing)}")

    for field_id, value in payload.items():
        field = fields[field_id]
        if field.read_only:
            raise HTTPException(422, f"runtime field is read-only: {field_id}")
        if value is None and not field.required:
            continue
        if not _matches_kind(field.kind, value):
            raise HTTPException(422, f"invalid value for runtime field: {field_id}")
    return dict(payload)


def _matches_kind(kind: str, value: Any) -> bool:
    if kind in {"text", "multiline"}:
        return isinstance(value, str)
    if kind == "integer":
        return type(value) is int
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "date":
        if not isinstance(value, str):
            return False
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if kind == "datetime":
        if not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return False
