import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from three_mm_protocol.application_event_publication import (
    ApplicationEventPublicationsV1,
)
from three_mm_protocol.application_extension import ApplicationExtensionV1
from three_mm_protocol.compiled_extension import CompiledUiExtensionV1
from three_mm_protocol.extension_schemas import (
    JSON_SCHEMA_DIALECT,
    extension_schema_catalog,
)
from three_mm_protocol.module_manifest import ModuleManifestV2
from three_mm_protocol.runtime_extension import RuntimeExtensionV1
from three_mm_protocol.theme_extension import ThemeExtensionV1
from three_mm_protocol.theme_extension_v2 import ThemeExtensionV2


MODELS = (
    ("module-manifest.v2", ModuleManifestV2, "manifest_version", 2, "manifest.json"),
    (
        "application-extension.v1",
        ApplicationExtensionV1,
        "application_extension_version",
        1,
        "application-extension.json",
    ),
    (
        "application-event-publications.v1",
        ApplicationEventPublicationsV1,
        "publication_contract_version",
        1,
        "application-event-publications.json",
    ),
    (
        "runtime-extension.v1",
        RuntimeExtensionV1,
        "runtime_extension_version",
        1,
        "runtime-extension.json",
    ),
    (
        "compiled-ui.v1",
        CompiledUiExtensionV1,
        "compiled_ui_version",
        1,
        "compiled-ui.json",
    ),
    (
        "theme-extension.v1",
        ThemeExtensionV1,
        "theme_extension_version",
        1,
        "theme-extension.json",
    ),
    (
        "theme-extension.v2",
        ThemeExtensionV2,
        "theme_extension_version",
        2,
        "theme-extension.json",
    ),
)


def assert_local_references(value, root):
    if isinstance(value, dict):
        if "$ref" in value:
            ref = value["$ref"]
            assert ref.startswith("#/")
            target = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            assert isinstance(target, dict)
        for child in value.values():
            assert_local_references(child, root)
    elif isinstance(value, list):
        for child in value:
            assert_local_references(child, root)


@pytest.mark.parametrize("contract_id,model,version_field,version,document", MODELS)
def test_exports_authoritative_models_without_structural_drift(
    contract_id, model, version_field, version, document
):
    entry = extension_schema_catalog()["contracts"][contract_id]
    schema = entry["schema"].copy()
    assert schema.pop("$schema") == JSON_SCHEMA_DIALECT
    assert schema.pop("$id") == f"urn:3mm:schema:{contract_id}"
    assert schema == model.model_json_schema(mode="validation")
    assert schema["additionalProperties"] is False
    assert entry["contract_version"] == version
    assert entry["version_field"] == version_field
    assert entry["document"] == document
    assert entry["source_model"] == f"{model.__module__}.{model.__name__}"
    assert_local_references(schema, schema)


def test_catalog_is_deterministic_independent_and_does_not_invent_contracts():
    first = extension_schema_catalog()
    second = extension_schema_catalog()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert set(first["contracts"]) == {row[0] for row in MODELS}
    first["contracts"]["module-manifest.v2"]["schema"]["properties"].clear()
    assert extension_schema_catalog() == second
    assert second["catalog_version"] == 1
    assert second["schema_mode"] == "validation"


def test_preserves_sdk_and_explicit_semantic_validation_limits():
    catalog = extension_schema_catalog()
    assert catalog["validation_scope"] == "structural_only"
    assert catalog["requires_authoritative_validation"] is True
    application = catalog["contracts"]["application-extension.v1"]["schema"]
    assert application["$defs"]["ApplicationServiceV1"]["properties"]["sdk_version"][
        "enum"
    ] == ["1.0", "1.1", "1.2", "1.3"]
    # This deliberately opaque structural field is still checked by the model.
    theme = catalog["contracts"]["theme-extension.v2"]["schema"]
    assert theme["properties"]["design"]["type"] == "object"
    assert any("Opaque dictionaries" in limit for limit in catalog["limitations"])
    assert (
        catalog["contracts"]["application-event-publications.v1"]["runtime_support"]
        == "reviewed_native_scoped"
    )
    assert any("applied resource grant" in limit for limit in catalog["limitations"])
    with pytest.raises(ValidationError, match="unknown design fields"):
        ThemeExtensionV2.model_validate(
            {
                "theme_extension_version": 2,
                "design_api_version": 2,
                "module_id": "org.example.theme",
                "version": "1.0.0",
                "name": {"en": "Example"},
                "design": {"design_api_version": 2, "unapproved_css": "body {}"},
            }
        )


def run_export(*args):
    return subprocess.run(
        [sys.executable, *args],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )


def test_real_cli_outputs_only_the_catalog():
    result = run_export("-m", "three_mm_protocol.extension_schemas")
    assert result.stderr == ""
    assert json.loads(result.stdout) == extension_schema_catalog()
    assert result.stdout.endswith("\n")


def test_export_does_not_import_core_agent_runtime_or_sdk():
    result = run_export(
        "-c",
        """
import sys
class BlockHostImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'backend', 'agent', 'three_mm_runtime', 'three_mm_application_sdk'}:
            raise AssertionError('Host import: ' + fullname)
sys.meta_path.insert(0, BlockHostImports())
from three_mm_protocol.extension_schemas import extension_schema_catalog
assert len(extension_schema_catalog()['contracts']) == 7
""",
    )
    assert result.stdout == result.stderr == ""
