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
        if model is ApplicationExtensionV1:
            # Authoring/compatibility information, NOT negotiation or grants.
            # Keep unavailable families explicit rather than implying that a
            # valid descriptor has a scoped runtime adapter.
            contracts[contract_id]["execution_profiles"] = {
                "compatibility": {
                    "existing_behavior": "preserved",
                    "scoped_resource_authority": False,
                },
                "reviewed_native_scoped": {
                    "artifact_scope": "installed_exact_artifact",
                    "frontend": "headless_only",
                    "resource_families": [
                        "command_bindings",
                        "connectors",
                        "event_subscriptions",
                        "event_publications",
                        "private_files",
                        "relational",
                        "checkpoints",
                        "installation.identity.read",
                        "installation.status.read",
                        "peer_bindings.outbound.read",
                    ],
                    "unsupported_features": [
                        "installation.identity.prove",
                        "peer_mutations",
                        "unfiltered_peer_listing",
                        "peer_receiver",
                        "jobs",
                        "public_http_routes",
                        "compiled_ui_resource_authority",
                        "arbitrary_capability_provides",
                        "relational_with_peer_bindings",
                    ],
                    "provides": "exact_event_publications_only",
                    "missing_feature_behavior": "refused_without_compatibility_fallback",
                    "browser_or_os_isolation": False,
                },
                "application_frontend_host_v1": {
                    "import": "@3mm/application-ui/v1",
                    "operations": ["getInfo", "invoke"],
                    "module_artifact_entrypoint_audience_bound": True,
                    "resource_authority": "separate",
                    "token_or_general_http_exposure": False,
                    "browser_isolation": False,
                },
                "reviewed_native_scoped_ui": {
                    "execution_profile": "supervised_reviewed_native_ui_v1",
                    "artifact_scope": "installed_exact_source_and_compiled_build",
                    "build_evidence": "core_owned_complete_output_inventory_v1",
                    "native_trust_administration": "local_core_only",
                    "same_origin_ui_risk_acceptance": "required_separately",
                    "resource_authority": "existing_exact_family_grants",
                    "human_access": "independent_current_audience_and_permissions",
                    "host_binding": "source_and_built_ui_sha256",
                    "legacy_build_without_evidence": "compatibility_only",
                    "unsupported_features": ["jobs", "public_http_routes", "peer_mutations",
                        "unfiltered_peer_listing", "peer_receiver", "installation.identity.prove",
                        "arbitrary_capability_provides", "relational_with_peer_bindings"],
                    "browser_or_os_isolation": False,
                },
            }
            # Bounded reviewed-native authority, not general installer or
            # hostile-code support. Structural validity still grants no rights.
            contracts[contract_id]["declaration_support"] = {
                "peer_bindings": {
                    "contract_version": 1,
                    "sdk_version": "1.3",
                    "declaration_validation": "supported",
                    "runtime_authority": "reviewed_native_scoped_outbound_read",
                    "runtime_directions": ["outbound"],
                    "runtime_operations": ["read"],
                    "sdk_method": "read_installation_peer",
                    "relational_combination": "unsupported",
                    "compatibility_fallback": "blocked",
                    "existing_peer_only": True,
                    "inbox_discovery_or_generic_signing": False,
                    "max_bindings": 32,
                },
                "platform_permissions.installation.identity.read": {
                    "sdk_version": "1.3",
                    "runtime_authority": "reviewed_native_scoped_local",
                    "authority_administration": "core_admin_review_api",
                    "native_trust_administration": "local_core_only",
                    "existing_public_identity_only": True,
                    "creates_identity": False,
                    "signing_or_possession_proof": False,
                },
                "platform_permissions.installation.status.read": {
                    "sdk_version": "1.3",
                    "runtime_authority": "reviewed_native_scoped_local",
                    "authority_administration": "core_admin_review_api",
                    "native_trust_administration": "local_core_only",
                    "existing_local_outbound_consent_only": True,
                    "max_existing_links": 32,
                    "creates_identity": False,
                    "signing_enrollment_or_reporting": False,
                },
                "checkpoints": {
                    "contract_version": 1,
                    "sdk_version": "1.3",
                    "declaration_validation": "supported",
                    "runtime_authority": "reviewed_native_scoped_local",
                    "authority_administration": "core_admin_review_api",
                    "native_trust_administration": "local_core_only",
                    "max_checkpoints": 32,
                    "max_value_bytes": 256 * 1024,
                },
                "storage.private_files": {
                    "contract_version": 1,
                    "sdk_version": "1.3",
                    "runtime_authority": "reviewed_native_scoped_local",
                    "authority_administration": "core_admin_review_api",
                    "native_trust_administration": "local_core_only",
                    "runtime_max_file_bytes": 1024 * 1024,
                },
                "storage.relational": {
                    "contract_version": 1,
                    "sdk_version": "1.3",
                    "declaration_validation": "supported",
                    "runtime_authority": "reviewed_native_scoped_prepared",
                    "authority_administration": "core_admin_review_api",
                    "native_trust_administration": "local_core_only",
                    "activation": "explicit_local_admin_helper",
                    "preparation_required": True,
                    "generic_activation": "blocked",
                    "limit_class": "cooperative_v1",
                },
            }
    return {
        "catalog_version": 1,
        "schema_mode": "validation",
        "validation_scope": "structural_only",
        "requires_authoritative_validation": True,
        "limitations": [
            "Custom model validators, cross-document references and archive rules remain authoritative.",
            "Opaque dictionaries (including theme v2 design and application schemas) need their existing semantic validators.",
            "Schema validity grants no publisher trust, permissions, compatibility or installation approval.",
            "Raw application descriptors require parse_application_extension; structural schemas cannot reject duplicate JSON keys.",
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
