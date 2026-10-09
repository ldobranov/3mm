"""Advisory inspection against a Core-selected, pinned installation snapshot."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import Literal
import zipfile
import zlib

from pydantic import BaseModel, ConfigDict

from backend.services.application_authority_review import (
    ApplicationAuthorityReview,
    review_application_authority,
)
from backend.services.module_packages import (
    MAX_PACKAGE_BYTES,
    ValidatedModulePackage,
    validate_module_package,
)


@dataclass(frozen=True)
class AuthorityInspectionBaseline:
    module_id: str | None
    version: str | None
    sha256: str | None
    active_version: str | None
    status: str
    configuration: dict | None


class InspectionAuthorityReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    review_version: Literal[1] = 1
    status: Literal["available", "unavailable", "not_applicable"]
    reason: (
        Literal[
            "application_only",
            "installation_not_stable",
            "baseline_unavailable",
            "review_failed",
        ]
        | None
    ) = None
    configuration_source: Literal["saved_installation_reused", "not_supplied"]
    review: ApplicationAuthorityReview | None = None


def _read_baseline(
    baseline: AuthorityInspectionBaseline,
    uploads_root: Path,
    core_version: str,
) -> ValidatedModulePackage:
    if not isinstance(baseline.sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", baseline.sha256
    ):
        raise ValueError("Invalid baseline digest")
    # Never read a client path or even the catalog's arbitrary file_path column.
    root = (uploads_root / "modules").resolve()
    path = root / f"{baseline.sha256}.zip"
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("Invalid baseline path")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PACKAGE_BYTES:
            raise ValueError("Invalid baseline file")
        blob = stream.read(MAX_PACKAGE_BYTES + 1)
    package = validate_module_package(blob, core_version=core_version)
    if (
        package.sha256 != baseline.sha256
        or package.manifest.module_id != baseline.module_id
        or package.manifest.version != baseline.version
        or package.application_extension is None
    ):
        raise ValueError("Baseline package identity mismatch")
    return package


def inspect_application_authority(
    candidate: ValidatedModulePackage,
    *,
    baseline: AuthorityInspectionBaseline | None,
    uploads_root: Path,
    core_version: str,
) -> InspectionAuthorityReview:
    """No writes, execution or approval; unavailable baseline is never a new install."""
    if candidate.application_extension is None:
        return InspectionAuthorityReview(
            status="not_applicable",
            reason="application_only",
            configuration_source="not_supplied",
        )
    source = "saved_installation_reused" if baseline is not None else "not_supplied"
    previous = None
    if baseline is not None:
        if (
            baseline.status not in {"active", "disabled"}
            or not baseline.active_version
            or baseline.active_version != baseline.version
        ):
            return InspectionAuthorityReview(
                status="unavailable",
                reason="installation_not_stable",
                configuration_source=source,
            )
        try:
            previous = _read_baseline(baseline, uploads_root, core_version)
            if previous.manifest.module_id != candidate.manifest.module_id:
                raise ValueError("Baseline module identity mismatch")
        except (
            OSError,
            ValueError,
            zipfile.BadZipFile,
            zlib.error,
            RuntimeError,
            NotImplementedError,
            RecursionError,
        ):
            return InspectionAuthorityReview(
                status="unavailable",
                reason="baseline_unavailable",
                configuration_source=source,
            )
    try:
        configuration = baseline.configuration if baseline is not None else None
        review = review_application_authority(
            candidate,
            previous=previous,
            candidate_configuration=configuration,
            previous_configuration=configuration,
        )
    except (ValueError, TypeError, RecursionError):
        return InspectionAuthorityReview(
            status="unavailable", reason="review_failed", configuration_source=source
        )
    return InspectionAuthorityReview(
        status="available", configuration_source=source, review=review
    )
