"""Build-only fixture variants; no import/execution of packaged application code."""

import base64
import csv
import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

from backend.artifacts.packages import validate_module_package

SOURCE = Path(__file__).resolve().parents[2] / "modules/wp4-relational-test"
CURRENT_BASELINE_SHA256 = "261434b328129b82742971434c3cdae3f5f925c41984763d37ac9d9d0797fb0b"
HISTORICAL_LIVE_SHA256 = "e3afeeba492b1eb30351ebbf8229c27fa1337ccd940f575bba9b96f2f09157d0"


def builder():
    spec = importlib.util.spec_from_file_location(
        "candidate_fixture_builder", SOURCE / "build_test_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_baseline_is_pinned_and_candidate_build_does_not_mutate_it():
    module = builder()
    assert hashlib.sha256(module.build_package()).hexdigest() == CURRENT_BASELINE_SHA256
    module.build_package(upgrade_candidate=True)
    assert hashlib.sha256(module.build_package()).hexdigest() == CURRENT_BASELINE_SHA256


def test_historical_sdk_spelling_alone_reproduces_accepted_zip(tmp_path, monkeypatch):
    """Recreate inert historical inputs; never import or install their service."""
    historical = tmp_path / "historical-inputs"
    replacements = {
        "service/wp4_relational_test/service.py": (
            b"from packages.application_sdk.scoped_relational import (",
            b"from three_mm_application_sdk.scoped_relational import (",
        ),
        "service/wp4_relational_test/migrations.py": (
            b"from packages.application_sdk import ApplicationMigration",
            b"from three_mm_application_sdk import ApplicationMigration",
        ),
    }
    names = (
        "manifest.json",
        "application-extension.json",
        "service/wp4_relational_test/__init__.py",
        *replacements,
    )
    for name in names:
        contents = (SOURCE / name).read_bytes()
        if name in replacements:
            current, previous = replacements[name]
            assert contents.count(current) == 1
            contents = contents.replace(current, previous, 1)
        destination = historical / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    module = builder()
    monkeypatch.setattr(module, "ROOT", historical)
    assert hashlib.sha256(module.build_package()).hexdigest() == HISTORICAL_LIVE_SHA256


@pytest.mark.parametrize("candidate", [False, True])
def test_both_variants_are_valid_deterministic_and_have_correct_wheel_records(
    candidate,
):
    module = builder()
    blob = module.build_package(upgrade_candidate=candidate)
    assert blob == module.build_package(upgrade_candidate=candidate)
    package = validate_module_package(blob)
    assert package.manifest.version == ("1.1.0" if candidate else "1.0.0")
    assert package.application_extension.storage.schema_revision == (
        "0002" if candidate else "0001"
    )
    assert package.application_extension.service.sdk_version == "1.3"
    assert (
        package.sha256 != CURRENT_BASELINE_SHA256
        if candidate
        else package.sha256 == CURRENT_BASELINE_SHA256
    )
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        wheel_bytes = archive.read(package.application_extension.service.artifact)
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        dist = f"wp4_relational_test-{package.manifest.version}.dist-info"
        record = csv.reader(io.StringIO(wheel.read(dist + "/RECORD").decode()))
        for name, digest, size in record:
            if name.endswith("/RECORD"):
                assert (digest, size) == ("", "")
                continue
            contents = wheel.read(name)
            expected = (
                base64.urlsafe_b64encode(hashlib.sha256(contents).digest())
                .rstrip(b"=")
                .decode()
            )
            assert (digest, int(size)) == ("sha256=" + expected, len(contents))
        migrations = wheel.read("wp4_relational_test/migrations.py")
        assert (b"upgrade_probe" in migrations) is candidate
        assert (
            b"Previously applied 0001 must not execute again" in migrations
        ) is candidate


@pytest.mark.parametrize("value", [1, "true", None])
def test_variant_is_an_explicit_boolean_not_implicit_coercion(value):
    with pytest.raises(ValueError):
        builder().build_package(upgrade_candidate=value)
