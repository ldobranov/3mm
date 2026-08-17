from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.db.extension import Extension
from backend.db.runtime_extension import RuntimeEntityRecord, RuntimeExtensionDefinition
from backend.db.module import ModulePackage
from backend.db.user import User
from backend.services.runtime_extensions import (
    active_definition,
    activate_definition,
    authorize_action,
    ensure_routes_available,
    entity_contract,
    parsed_definition,
    validate_record_data,
)
from backend.utils.auth_dep import require_admin, require_user
from backend.utils.db_utils import get_db
from three_mm_protocol import RuntimeExtensionV1
from pathlib import Path
from backend.services.module_packages import ModulePackageError, validate_module_package


router = APIRouter(prefix="/api/v1/runtime-extensions", tags=["runtime-extensions"])


class DefinitionResponse(BaseModel):
    module_id: str
    version: str
    definition: dict
    enabled: bool
    model_config = ConfigDict(from_attributes=True)


class RecordResponse(BaseModel):
    record_id: str
    data: dict
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CatalogExtensionResponse(BaseModel):
    id: str
    source: str
    name: str
    type: str
    version: str
    description: str | None = None
    author: str | None = None
    status: str
    is_enabled: bool
    created_at: datetime
    can_manage: bool
    available_versions: list[str] = Field(default_factory=list)
    package_sha256: str | None = None
    is_installed: bool = True


class RuntimeEnabledUpdate(BaseModel):
    enabled: bool


class RuntimeUninstallResponse(BaseModel):
    module_id: str
    deleted_versions: int
    deleted_records: int
    data_preserved: bool


def _current_user(claims: dict, db: Session) -> User:
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.get(User, int(user_id)) if user_id else None
    if user is None:
        raise HTTPException(401, "authenticated user was not found")
    return user


def _localized_value(value: dict, language: str) -> str:
    return (value.get("translations") or {}).get(language) or value["en"]


@router.post("/definitions", response_model=DefinitionResponse, status_code=status.HTTP_201_CREATED)
def publish_definition(
    payload: RuntimeExtensionV1,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return activate_definition(db, payload, admin)


@router.post(
    "/packages/{sha256}/activate",
    response_model=DefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
def activate_package(
    sha256: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None:
        raise HTTPException(404, "module package was not found")
    try:
        validated = validate_module_package(Path(package.file_path).read_bytes())
    except (OSError, ModulePackageError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if validated.sha256 != package.sha256:
        raise HTTPException(409, "module package no longer matches its catalog hash")
    if validated.runtime_extension is None:
        raise HTTPException(409, "module package is not a runtime extension")
    return activate_definition(db, validated.runtime_extension, admin)


@router.get("/definitions", response_model=list[DefinitionResponse])
def list_definitions(
    _claims: dict = Depends(require_user), db: Session = Depends(get_db)
):
    return list(
        db.scalars(
            select(RuntimeExtensionDefinition)
            .where(RuntimeExtensionDefinition.enabled.is_(True))
            .order_by(RuntimeExtensionDefinition.module_id)
        )
    )


@router.get("/catalog", response_model=list[CatalogExtensionResponse])
def list_extension_catalog(
    language: str = Query(default="en", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$"),
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Return legacy and declarative runtime extensions through one read model."""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(401, "invalid token payload")

    legacy = list(
        db.scalars(
            select(Extension)
            .where(Extension.user_id == int(user_id))
            .order_by(Extension.name, Extension.version)
        )
    )
    runtime_versions = list(
        db.scalars(
            select(RuntimeExtensionDefinition)
            .order_by(
                RuntimeExtensionDefinition.module_id,
                RuntimeExtensionDefinition.is_selected.desc(),
                RuntimeExtensionDefinition.enabled.desc(),
                RuntimeExtensionDefinition.created_at.desc(),
                RuntimeExtensionDefinition.id.desc(),
            )
        )
    )
    runtime_packages = [
        package
        for package in db.scalars(
            select(ModulePackage).order_by(
                ModulePackage.created_at.desc(), ModulePackage.id.desc()
            )
        )
        if (package.manifest.get("entrypoints") or {}).get("ui")
        == "runtime-extension.json"
    ]
    packages_by_module = {}
    for package in runtime_packages:
        packages_by_module.setdefault(package.module_id, package)
    runtime = []
    versions_by_module: dict[str, list[str]] = {}
    seen_module_ids = set()
    for item in runtime_versions:
        versions_by_module.setdefault(item.module_id, []).append(item.version)
        if item.module_id not in seen_module_ids:
            runtime.append(item)
            seen_module_ids.add(item.module_id)

    items = [
        CatalogExtensionResponse(
            id=f"legacy:{item.id}",
            source="legacy",
            name=item.name,
            type=item.type,
            version=item.version,
            description=item.description,
            author=item.author,
            status=item.status,
            is_enabled=item.is_enabled,
            created_at=item.created_at,
            can_manage=True,
        )
        for item in legacy
    ]
    items.extend(
        CatalogExtensionResponse(
            id=f"runtime:{item.module_id}",
            source="runtime",
            name=_localized_value(item.definition["name"], language),
            type="runtime",
            version=item.version,
            description=_localized_value(item.definition["description"], language),
            status="active" if item.enabled else "inactive",
            is_enabled=item.enabled,
            created_at=item.created_at,
            can_manage=claims.get("role") == "admin",
            available_versions=versions_by_module[item.module_id],
            package_sha256=(
                packages_by_module[item.module_id].sha256
                if item.module_id in packages_by_module
                else None
            ),
        )
        for item in runtime
    )
    installed_module_ids = {item.module_id for item in runtime}
    items.extend(
        CatalogExtensionResponse(
            id=f"runtime:{package.module_id}",
            source="runtime",
            name=package.manifest.get("name") or package.module_id,
            type="runtime",
            version=package.version,
            description=package.manifest.get("description"),
            status="uninstalled",
            is_enabled=False,
            created_at=package.created_at,
            can_manage=claims.get("role") == "admin",
            available_versions=[package.version],
            package_sha256=package.sha256,
            is_installed=False,
        )
        for package in packages_by_module.values()
        if package.module_id not in installed_module_ids
    )
    return items


@router.patch("/definitions/{module_id}", response_model=DefinitionResponse)
def set_runtime_extension_enabled(
    module_id: str,
    payload: RuntimeEnabledUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    versions = list(
        db.scalars(
            select(RuntimeExtensionDefinition)
            .where(RuntimeExtensionDefinition.module_id == module_id)
            .order_by(
                RuntimeExtensionDefinition.is_selected.desc(),
                RuntimeExtensionDefinition.enabled.desc(),
                RuntimeExtensionDefinition.created_at.desc(),
                RuntimeExtensionDefinition.id.desc(),
            )
        )
    )
    if not versions:
        raise HTTPException(404, "runtime extension was not found")

    selected = next((version for version in versions if version.is_selected), versions[0])
    if payload.enabled:
        ensure_routes_available(db, RuntimeExtensionV1.model_validate(selected.definition))
        for version in versions:
            version.enabled = version.id == selected.id
            version.is_selected = version.id == selected.id
    else:
        for version in versions:
            version.enabled = False

    db.add(
        AuditLog(
            user_id=admin.id,
            action="UPDATE",
            entity_type="runtime_extension",
            entity_id=selected.id,
            entity_name=f"{module_id}@{selected.version}",
            changes={"enabled": payload.enabled},
        )
    )
    db.commit()
    db.refresh(selected)
    return selected


@router.post(
    "/definitions/{module_id}/versions/{version}/activate",
    response_model=DefinitionResponse,
)
def activate_runtime_extension_version(
    module_id: str,
    version: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    selected = db.scalar(
        select(RuntimeExtensionDefinition).where(
            RuntimeExtensionDefinition.module_id == module_id,
            RuntimeExtensionDefinition.version == version,
        )
    )
    if selected is None:
        raise HTTPException(404, "runtime extension version was not found")

    ensure_routes_available(db, RuntimeExtensionV1.model_validate(selected.definition))

    db.query(RuntimeExtensionDefinition).filter(
        RuntimeExtensionDefinition.module_id == module_id
    ).update(
        {
            RuntimeExtensionDefinition.enabled: False,
            RuntimeExtensionDefinition.is_selected: False,
        }
    )
    selected.enabled = True
    selected.is_selected = True
    db.add(
        AuditLog(
            user_id=admin.id,
            action="UPDATE",
            entity_type="runtime_extension",
            entity_id=selected.id,
            entity_name=f"{module_id}@{version}",
            changes={"enabled": True, "reason": "version_activation"},
        )
    )
    db.commit()
    db.refresh(selected)
    return selected


@router.delete(
    "/definitions/{module_id}",
    response_model=RuntimeUninstallResponse,
)
def uninstall_runtime_extension(
    module_id: str,
    delete_data: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    versions = list(
        db.scalars(
            select(RuntimeExtensionDefinition).where(
                RuntimeExtensionDefinition.module_id == module_id
            )
        )
    )
    if not versions:
        raise HTTPException(404, "runtime extension was not found")

    deleted_records = 0
    if delete_data:
        deleted_records = (
            db.query(RuntimeEntityRecord)
            .filter(RuntimeEntityRecord.module_id == module_id)
            .delete(synchronize_session=False)
        )

    version_count = len(versions)
    db.add(
        AuditLog(
            user_id=admin.id,
            action="DELETE",
            entity_type="runtime_extension",
            entity_id=versions[0].id,
            entity_name=module_id,
            changes={
                "deleted_versions": version_count,
                "deleted_records": deleted_records,
                "data_preserved": not delete_data,
            },
        )
    )
    for version in versions:
        db.delete(version)
    db.commit()
    return RuntimeUninstallResponse(
        module_id=module_id,
        deleted_versions=version_count,
        deleted_records=deleted_records,
        data_preserved=not delete_data,
    )


@router.get("/{module_id}/definition", response_model=DefinitionResponse)
def read_definition(
    module_id: str, _claims: dict = Depends(require_user), db: Session = Depends(get_db)
):
    return active_definition(db, module_id)


@router.get("/{module_id}/entities/{entity_id}/records", response_model=list[RecordResponse])
def list_records(
    module_id: str,
    entity_id: str,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _current_user(claims, db)
    definition_record = active_definition(db, module_id)
    definition = parsed_definition(definition_record)
    entity_contract(definition, entity_id)
    authorize_action(definition, entity_id, "read", user.role)
    return list(
        db.scalars(
            select(RuntimeEntityRecord)
            .where(
                RuntimeEntityRecord.module_id == module_id,
                RuntimeEntityRecord.entity_id == entity_id,
            )
            .order_by(RuntimeEntityRecord.id)
        )
    )


@router.post(
    "/{module_id}/entities/{entity_id}/records",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_record(
    module_id: str,
    entity_id: str,
    payload: dict,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _current_user(claims, db)
    definition_record = active_definition(db, module_id)
    definition = parsed_definition(definition_record)
    entity = entity_contract(definition, entity_id)
    authorize_action(definition, entity_id, "create", user.role)
    data = validate_record_data(entity, payload, partial=False)
    record = RuntimeEntityRecord(
        module_id=module_id,
        entity_id=entity_id,
        record_id=uuid4().hex,
        data=data,
        created_by=user.id,
    )
    db.add(record)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="CREATE",
            entity_type="runtime_record",
            entity_id=record.id,
            entity_name=f"{module_id}:{entity_id}:{record.record_id}",
            changes={"fields": sorted(data)},
        )
    )
    db.commit()
    db.refresh(record)
    return record


def _record_or_404(
    db: Session, module_id: str, entity_id: str, record_id: str
) -> RuntimeEntityRecord:
    record = db.scalar(
        select(RuntimeEntityRecord).where(
            RuntimeEntityRecord.module_id == module_id,
            RuntimeEntityRecord.entity_id == entity_id,
            RuntimeEntityRecord.record_id == record_id,
        )
    )
    if record is None:
        raise HTTPException(404, "runtime record was not found")
    return record


@router.patch(
    "/{module_id}/entities/{entity_id}/records/{record_id}",
    response_model=RecordResponse,
)
def update_record(
    module_id: str,
    entity_id: str,
    record_id: str,
    payload: dict,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _current_user(claims, db)
    definition_record = active_definition(db, module_id)
    definition = parsed_definition(definition_record)
    entity = entity_contract(definition, entity_id)
    authorize_action(definition, entity_id, "update", user.role)
    changes = validate_record_data(entity, payload, partial=True)
    record = _record_or_404(db, module_id, entity_id, record_id)
    record.data = {**record.data, **changes}
    db.add(
        AuditLog(
            user_id=user.id,
            action="UPDATE",
            entity_type="runtime_record",
            entity_id=record.id,
            entity_name=f"{module_id}:{entity_id}:{record.record_id}",
            changes={"fields": sorted(changes)},
        )
    )
    db.commit()
    db.refresh(record)
    return record


@router.delete(
    "/{module_id}/entities/{entity_id}/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_record(
    module_id: str,
    entity_id: str,
    record_id: str,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _current_user(claims, db)
    definition_record = active_definition(db, module_id)
    definition = parsed_definition(definition_record)
    entity_contract(definition, entity_id)
    authorize_action(definition, entity_id, "delete", user.role)
    record = _record_or_404(db, module_id, entity_id, record_id)
    db.add(
        AuditLog(
            user_id=user.id,
            action="DELETE",
            entity_type="runtime_record",
            entity_id=record.id,
            entity_name=f"{module_id}:{entity_id}:{record.record_id}",
            changes={"fields": sorted(record.data)},
        )
    )
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
