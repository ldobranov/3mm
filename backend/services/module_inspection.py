"""Read-only projections of the existing validated manifest-v2 contract.

This is not an install plan, publisher verification or permission approval.
No artifact storage, build or activation belongs in this module.
"""

from typing import Literal

from pydantic import BaseModel

from backend.services.application_authority_inspection import InspectionAuthorityReview
from backend.services.module_packages import ValidatedModulePackage
from three_mm_protocol import ModuleManifestV2


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


class PackageInspectionResponse(BaseModel):
    inspection_version: Literal[1] = 1
    module_id: str
    version: str
    sha256: str
    size_bytes: int
    package_kind: Literal[
        "module", "agent_module", "application", "runtime_ui", "compiled_ui", "theme"
    ]
    manifest: ModuleManifestV2
    descriptors: dict[str, dict]
    catalog: InspectionCatalog
    compatibility: InspectionCompatibility
    dependency_resolution: Literal["not_resolved"] = "not_resolved"
    trust: InspectionTrust = InspectionTrust()
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    authority_review: InspectionAuthorityReview | None = None


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
            ("runtime_extension", package.runtime_extension),
            ("compiled_ui", package.compiled_ui),
            ("application_extension", package.application_extension),
            ("theme_extension", package.theme_extension),
        )
        if descriptor is not None
    }
    kind = "module"
    if package.application_extension is not None:
        kind = "application"
    elif package.theme_extension is not None:
        kind = "theme"
    elif package.runtime_extension is not None:
        kind = "runtime_ui"
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
        catalog=InspectionCatalog(status=status, existing_sha256=existing_sha256),
        compatibility=InspectionCompatibility(
            core="matched" if "core" in package.manifest.runtimes else "not_checked",
            core_version=core_version,
        ),
    )
