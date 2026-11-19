"""Read-only projections of the existing validated manifest-v2 contract.

This is not an install plan, publisher verification or permission approval.
No artifact storage, build or activation belongs in this module.
"""

from typing import Literal

from pydantic import BaseModel

from backend.applications.authority.inspection import InspectionAuthorityReview
from backend.artifacts.packages import ValidatedModulePackage
from packages.protocol import ApplicationExtensionV1, ModuleManifestV2


class InspectionCatalog(BaseModel):
    status: Literal["new", "exact_artifact", "version_conflict"]
    existing_sha256: str | None


class InspectionCompatibility(BaseModel):
    protocol: Literal["matched"] = "matched"
    core: Literal["matched", "not_checked"]
    core_version: str
    agent: Literal["not_checked"] = "not_checked"
    architecture: Literal["not_checked"] = "not_checked"
    target_device: Literal["not_checked"] = "not_checked"


class InspectionTrust(BaseModel):
    publisher: Literal["not_verified"] = "not_verified"
    signature: Literal["not_verified"] = "not_verified"


class DeclaredDataOperation(BaseModel):
    purpose: Literal["export", "erasure", "retention"]
    operation_id: str
    kind: str
    audiences: tuple[str, ...]
    required_permission: str | None


class ApplicationDataPractices(BaseModel):
    source: Literal["package_declaration"] = "package_declaration"
    contains_personal_data: bool
    classifications: tuple[str, ...]
    schema_revision: str
    retention: Literal["until_explicit_erasure", "application_job", "not_declared"]
    operations: tuple[DeclaredDataOperation, ...]
    external_copies: Literal["not_erased_by_local_action"] = "not_erased_by_local_action"


def declared_data_practices(application: ApplicationExtensionV1) -> ApplicationDataPractices:
    """Join validated declarations by exact IDs. No subject lookup, grant or lifecycle action."""
    storage = application.storage
    by_id = {op.operation_id: op for op in application.operations}
    controls = []
    for purpose, key in (("export", storage.export_operation_id), ("erasure", storage.erasure_operation_id),
                         ("retention", storage.retention_operation_id)):
        if key is not None:
            op = by_id[key]  # reference integrity checked by the v2 package reader
            controls.append(DeclaredDataOperation(purpose=purpose, operation_id=key, kind=op.kind,
                                                  audiences=op.audiences, required_permission=op.required_permission))
    return ApplicationDataPractices(
        contains_personal_data=storage.contains_personal_data, classifications=storage.classifications,
        schema_revision=storage.schema_revision, operations=tuple(controls),
        retention=storage.retention_policy or ("application_job" if storage.retention_operation_id else "not_declared"),
    )


class PackageInspectionResponse(BaseModel):
    inspection_version: Literal[1] = 1
    module_id: str
    version: str
    sha256: str
    size_bytes: int
    package_kind: Literal[
        "module", "agent_module", "application", "compiled_ui", "theme", "language"
    ]
    manifest: ModuleManifestV2
    descriptors: dict[str, dict]
    catalog: InspectionCatalog
    compatibility: InspectionCompatibility
    dependency_resolution: Literal["not_resolved"] = "not_resolved"
    trust: InspectionTrust = InspectionTrust()
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    authority_review: InspectionAuthorityReview | None = None
    data_practices: ApplicationDataPractices | None = None


def describe_module_package(
    package: ValidatedModulePackage,
    *,
    core_version: str,
    existing_sha256: str | None,
) -> PackageInspectionResponse:
    """Project validated declarations, never infer trust or install readiness."""
    descriptors = {
        name: descriptor.model_dump(mode="json")
        for name, descriptor in (
            ("compiled_ui", package.compiled_ui),
            ("application_extension", package.application_extension),
            ("theme_extension", package.theme_extension),
            ("language_extension", package.language_extension),
        )
        if descriptor is not None
    }
    kind = "module"
    if package.application_extension is not None:
        kind = "application"
    elif package.language_extension is not None:
        kind = "language"
    elif package.theme_extension is not None:
        kind = "theme"
    elif package.compiled_ui is not None:
        kind = "compiled_ui"
    elif package.manifest.runtimes == ("agent",):
        kind = "agent_module"
    status = (
        "new" if existing_sha256 is None
        else "exact_artifact" if existing_sha256 == package.sha256
        else "version_conflict"
    )
    return PackageInspectionResponse(
        module_id=package.manifest.module_id,
        version=package.manifest.version,
        sha256=package.sha256,
        size_bytes=package.size_bytes,
        package_kind=kind,
        manifest=package.manifest,
        descriptors=descriptors,
        data_practices=(declared_data_practices(package.application_extension)
                        if package.application_extension is not None else None),
        catalog=InspectionCatalog(status=status, existing_sha256=existing_sha256),
        compatibility=InspectionCompatibility(
            core="matched" if "core" in package.manifest.runtimes else "not_checked",
            core_version=core_version,
        ),
    )
