"""Real archive/advisory review; new DB requests cannot reuse native proof."""

import io
import json
import os
import zipfile

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.application_authority_grant import ApplicationAuthorityPlan as Plan
from backend.db.application_authority_grant import ApplicationNativeReview as Native
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ModulePackage
from backend.services import application_authority_sources as sources
from backend.services.application_authority_management import AuthorityManagementError
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.tests.test_application_authority_management import (
    identity,
)
from backend.tests.test_application_authority_management import (
    installed as managed_installed,
)
from backend.tests.test_application_authority_management import native, review
from backend.tests.test_application_authority_review import changes
from backend.tests.test_application_authority_review import review as inspect
from backend.tests.test_application_authority_review import validated
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
)
from backend.tests.test_application_authority_subjects import source_installed
from backend.tests.test_module_packages import (
    application_definition,
    application_package,
)
from three_mm_protocol.tests.test_application_relational_storage import (
    relational_request,
)


def package(**changes):
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request(**changes)
    return validated(definition=definition)


def test_inspection_keeps_legacy_storage_bytes_and_separates_db_request():
    legacy = validated()
    assert "relational" not in changes(inspect(legacy))["own_storage"].after
    changed = changes(inspect(package(), legacy))
    assert "own_storage" not in changed
    request = changed["storage:relational"]
    assert request.change == "added" and request.potential_expansion
    assert request.after == relational_request() and request.before is None


@pytest.mark.parametrize(
    "change",
    [
        dict(mode="read"),
        dict(max_database_bytes=128 * 1024 * 1024),
        dict(auxiliary_pause_bytes=1024 * 1024),
        dict(max_busy_ms=0),
    ],
)
def test_profile_changes_and_unresolved_grants_are_visible_not_approval(change):
    result = inspect(package(**change), package())
    item = changes(result)["storage:relational"]
    assert item.change == "changed" and item.after == relational_request(**change)
    assert result.permission_approval == "not_evaluated"
    assert any(
        item.scope == "storage:relational"
        and item.reason == "relational_storage_grant_not_evaluated"
        for item in result.unresolved
    )


def test_identical_or_removed_request_does_not_reuse_or_create_approval():
    current = package()
    same = inspect(current, current)
    assert same.changes == () and same.declaration_review_required
    assert same.permission_approval == "not_evaluated"
    removed = changes(inspect(validated(), current))["storage:relational"]
    assert removed.change == "removed" and not removed.potential_expansion


@pytest.mark.parametrize(
    "invalid",
    [
        dict(max_busy_ms=True),
        dict(path="/var/lib/3mm/core/3mm.db"),
        dict(owner="foreign"),
        dict(max_database_bytes=0),
        dict(max_result_bytes=1),
    ],
)
def test_real_zip_validation_refuses_invalid_profiles(invalid):
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request(**invalid)
    with pytest.raises(ModulePackageError):
        validate_module_package(application_package(definition=definition))


def test_real_zip_validation_cannot_hide_profile_with_duplicate_storage():
    definition = application_definition()
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request()
    raw = json.dumps(definition)
    legacy = {
        key: value
        for key, value in definition["storage"].items()
        if key != "relational"
    }
    raw = raw[:-1] + ', "storage": ' + json.dumps(legacy) + "}"
    output = io.BytesIO()
    with (
        zipfile.ZipFile(
            io.BytesIO(application_package(definition=definition))
        ) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        for item in source.infolist():
            target.writestr(
                item,
                (
                    raw
                    if item.filename == "application-extension.json"
                    else source.read(item)
                ),
            )
    with pytest.raises(ModulePackageError, match="duplicate JSON keys"):
        validate_module_package(output.getvalue())


@pytest.mark.skipif(os.name != "posix", reason="Actual POSIX Core authority keys")
@pytest.mark.parametrize("mode", ["read", "read_write"])
def test_new_db_request_cannot_reuse_previous_artifact_native_attestation(
    managed_installed, mode
):
    state = managed_installed
    previous_native = native(state)
    definition = state.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["storage"]["relational"] = relational_request(mode=mode)
    manifest = state.validated.manifest.model_dump(mode="json")
    output = io.BytesIO()
    with (
        zipfile.ZipFile(state.archive) as source,
        zipfile.ZipFile(output, "w") as target,
    ):
        target.writestr("manifest.json", json.dumps(manifest))
        target.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        target.writestr(artifact, source.read(artifact))
    checked = validate_module_package(output.getvalue())
    archive = state.root / "modules" / (checked.sha256 + ".zip")
    archive.write_bytes(output.getvalue())
    with state.engine.begin() as db:
        db.execute(
            update(ModulePackage)
            .where(ModulePackage.id == 1)
            .values(
                sha256=checked.sha256,
                size_bytes=len(output.getvalue()),
                file_path=str(archive),
                manifest=manifest,
            )
        )
    result = sources.resolve_installed_authority_sources(
        state.engine, 1, uploads_root=state.root, core_version="0.3.0"
    )
    assert result.sources_resolved
    assert {item.operation for item in result.relational} == (
        {"read", "write"} if mode == "read_write" else {"read"}
    )
    assert all(item.package_artifact_sha256 == checked.sha256 for item in result.relational)
    with Session(state.engine) as db:
        before = (
            db.get(Installation, 1).authority_epoch,
            db.get(CoreAuthorityGuard, 1).revision,
        )
        counts = {
            model: db.scalar(select(func.count()).select_from(model))
            for model in (Action, Grant, Plan, Native, AuditLog)
        }
    with pytest.raises(AuthorityManagementError, match="native_review_unavailable"):
        review(state, previous_native)
    with Session(state.engine) as db:
        installation = db.get(Installation, 1)
        assert (
            installation.authority_epoch,
            db.get(CoreAuthorityGuard, 1).revision,
        ) == before
        assert installation.authority_mode == "compatibility" and installation.enabled
        assert {
            model: db.scalar(select(func.count()).select_from(model))
            for model in counts
        } == counts
