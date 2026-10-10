"""Safe inspection plus negative real-source/native-manager storage adoption."""

import io
import json
import os
import zipfile

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import (
    ApplicationAuthorityAction as Action,
    ApplicationAuthorityGrant as Grant,
    ApplicationAuthorityPlan as Plan,
    ApplicationNativeReview as Native,
)
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
    ModulePackage,
)
from backend.services import application_authority_sources as sources
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_application_authority_management import (
    identity,
    installed as managed_installed,
    native,
    review,
)
from backend.tests.test_application_authority_review import (
    changes,
    review as declaration_review,
    validated,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
    source_installed,
)
from backend.tests.test_module_packages import (
    application_definition,
    application_package,
)
from three_mm_protocol.tests.test_application_private_files import file_request


def package(**bounds):
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["private_files"] = file_request(**bounds)
    return validated(definition=definition)


def test_inspection_preserves_old_storage_view_and_does_not_infer_files():
    original = validated()
    old = changes(declaration_review(original))["own_storage"].after
    assert "private_files" not in old
    changed = changes(declaration_review(package(), original))
    assert "own_storage" not in changed
    request = changed["storage:private_files"]
    assert request.change == "added" and request.potential_expansion
    assert request.after == file_request() and request.before is None
    assert "path" not in request.after and "owner" not in request.after


@pytest.mark.parametrize(
    "changed",
    [
        dict(mode="read"),
        dict(max_files=257),
        dict(max_file_bytes=2 * 1024 * 1024),
        dict(max_total_bytes=32 * 1024 * 1024),
    ],
)
def test_mode_and_bounds_changes_are_explicit_review_changes(changed):
    result = declaration_review(package(**changed), package())
    change = changes(result)["storage:private_files"]
    assert change.change == "changed" and change.potential_expansion
    assert change.before == file_request()
    assert change.after == file_request(**changed)
    assert result.permission_approval == "not_evaluated"
    assert any(
        item.scope == "storage:private_files"
        and item.reason == "private_file_grant_not_evaluated"
        for item in result.unresolved
    )


def test_exact_or_removed_declaration_is_never_permission_approval():
    current = package()
    same = declaration_review(current, current)
    assert same.changes == () and same.declaration_review_required
    assert same.permission_approval == "not_evaluated"
    removed = changes(declaration_review(validated(), current))["storage:private_files"]
    assert removed.change == "removed" and not removed.potential_expansion


@pytest.mark.parametrize(
    "invalid",
    [
        dict(max_files=True),
        dict(path="/opt/3mm/current"),
        dict(owner="foreign"),
        dict(max_total_bytes=0),
    ],
)
def test_real_zip_validator_refuses_unsafe_file_requests_without_execution(invalid):
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["private_files"] = file_request(**invalid)
    with pytest.raises(ModulePackageError):
        validate_module_package(application_package(definition=definition))


@pytest.mark.skipif(os.name != "posix", reason="Real POSIX Core authority keys")
@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_declared_files_cannot_acquire_grants_via_another_scope_or_native_review(
    managed_installed, mode
):
    state = managed_installed
    # Previously valid exact-artifact native review must not authorize new files.
    previous = native(state)
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["private_files"] = file_request(mode=mode, max_file_bytes=2 * 1024 * 1024)
    # Preserve the real headless package shape: adding UI files here would
    # correctly be refused before the new declaration reaches authority review.
    manifest = state.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with (
        zipfile.ZipFile(state.archive) as previous_archive,
        zipfile.ZipFile(output, "w") as archive,
    ):
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        archive.writestr(artifact, previous_archive.read(artifact))
    state.validated = validate_module_package(output.getvalue())
    state.archive = state.root / "modules" / f"{state.validated.sha256}.zip"
    state.archive.write_bytes(output.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=state.validated.sha256,
                size_bytes=len(output.getvalue()),
                manifest=manifest,
                file_path=str(state.archive),
            )
        )
    result = sources.resolve_installed_authority_sources(
        state.engine, 1, uploads_root=state.root, core_version="0.3.0"
    )
    assert result.sources_resolved
    assert any(
        item.scope == "storage:private_files"
        and item.reason == "unsupported_scope_family"
        for item in result.issues
    )
    with Session(state.engine) as db:
        before = (
            db.get(Installation, 1).authority_epoch,
            db.get(CoreAuthorityGuard, 1).revision,
        )
        counts = {
            model: db.scalar(select(func.count()).select_from(model))
            for model in (Action, Grant, Plan, Native, AuditLog)
        }
    # Selecting only old commands/connectors cannot omit the unsupported storage
    # family, and another explicit acceptance of native-host risk is not a grant.
    with pytest.raises(AuthorityManagementError, match="unsupported_authority"):
        review(state, previous)
    with pytest.raises(AuthorityManagementError, match="unsupported_authority"):
        state.manager.record_native_review(
            1,
            actor_token=state.token,
            request_id=identity(),
            artifact_sha256=result.baseline.artifact.sha256,
            review_document_sha256="b" * 64,
            native_code_review_completed=True,
            accepts_native_host_risk=True,
        )
    with Session(state.engine) as db:
        installation = db.get(Installation, 1)
        assert (
            installation.authority_epoch,
            db.get(CoreAuthorityGuard, 1).revision,
        ) == before
        assert installation.authority_mode == "compatibility"
        assert installation.enabled and installation.status == "active"
        assert {
            model: db.scalar(select(func.count()).select_from(model))
            for model in counts
        } == counts
