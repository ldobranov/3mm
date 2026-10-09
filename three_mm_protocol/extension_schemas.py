"""Public structural schema exports, derived from existing extension models.

These schemas are authoring aids, not a replacement for model validators,
ZIP inspection, compatibility checks or authorization. No Core imports or
extension payloads are needed to export them.
"""

import argparse
import json

from pydantic import BaseModel

from three_mm_protocol.application_event_publication import (
    ApplicationEventPublicationsV1,
)
from three_mm_protocol.application_extension import ApplicationExtensionV1
from three_mm_protocol.compiled_extension import CompiledUiExtensionV1
from three_mm_protocol.module_manifest import ModuleManifestV2
from three_mm_protocol.runtime_extension import RuntimeExtensionV1
from three_mm_protocol.theme_extension import ThemeExtensionV1
from three_mm_protocol.theme_extension_v2 import ThemeExtensionV2


JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# Contract IDs identify schemas, not publishers, package IDs or install rights.
_CONTRACTS: tuple[tuple[str, str, str, type[BaseModel]], ...] = (
    ("module-manifest.v2", "manifest_version", "manifest.json", ModuleManifestV2),
    (
        "application-extension.v1",
        "application_extension_version",
        "application-extension.json",
        ApplicationExtensionV1,
    ),
    (
        "application-event-publications.v1",
        "publication_contract_version",
        "application-event-publications.json",
        ApplicationEventPublicationsV1,
    ),
    (
        "runtime-extension.v1",
        "runtime_extension_version",
        "runtime-extension.json",
        RuntimeExtensionV1,
    ),
    (
        "compiled-ui.v1",
        "compiled_ui_version",
        "compiled-ui.json",
        CompiledUiExtensionV1,
    ),
    (
        "theme-extension.v1",
        "theme_extension_version",
        "theme-extension.json",
        ThemeExtensionV1,
    ),
    (
        "theme-extension.v2",
        "theme_extension_version",
        "theme-extension.json",
        ThemeExtensionV2,
    ),
)


def extension_schema_catalog() -> dict:
    """Return independent validation-mode JSON Schemas with local-only refs.

    The catalog's version is independent of manifest, SDK and Core versions.
    In particular, custom model validators and archive rules cannot all be
    represented by Pydantic's structural JSON Schema export.
    """
    contracts = {}
    for contract_id, version_field, document, model in _CONTRACTS:
        schema = model.model_json_schema(mode="validation")
        schema["$schema"] = JSON_SCHEMA_DIALECT
        schema["$id"] = f"urn:3mm:schema:{contract_id}"
        contracts[contract_id] = {
            "document": document,
            "version_field": version_field,
            "contract_version": schema["properties"][version_field]["const"],
            "source_model": f"{model.__module__}.{model.__name__}",
            "schema": schema,
        }
        if model is ApplicationEventPublicationsV1:
            contracts[contract_id]["runtime_support"] = "reviewed_native_scoped"
    return {
        "catalog_version": 1,
        "schema_mode": "validation",
        "validation_scope": "structural_only",
        "requires_authoritative_validation": True,
        "limitations": [
            "Custom model validators, cross-document references and archive rules remain authoritative.",
            "Opaque dictionaries (including theme v2 design and application schemas) need their existing semantic validators.",
            "Schema validity grants no publisher trust, permissions, compatibility or installation approval.",
            "reviewed_native_scoped requires an exact installed artifact, local code review and applied resource grant; it is not isolation or cross-application stream access.",
        ],
        "contracts": contracts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    # Stable stdout only: no generated source files, network, builds or installer.
    print(
        json.dumps(
            extension_schema_catalog(), ensure_ascii=False, indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
