"""Shared extension-domain identity adapters.

Native module packages keep their stable module_id. Legacy Extension rows do not
have a globally stable identity, so the adapter exposes only a local catalog ID
and marks them as migration-required instead of inventing a module ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from three_mm_protocol import ModuleManifestV2


@dataclass(frozen=True, slots=True)
class ExtensionDomainIdentity:
    catalog_id: str
    module_id: str | None
    compatibility_mode: str
    migration_required: bool
    publisher: dict[str, str] | None = None
    extension_api: str | None = None


def legacy_extension_identity(record_id: int) -> ExtensionDomainIdentity:
    return ExtensionDomainIdentity(
        catalog_id=f"legacy:{record_id}",
        module_id=None,
        compatibility_mode="legacy-trusted",
        migration_required=True,
    )


def native_extension_identity(
    module_id: str,
    manifest: Mapping[str, Any] | None = None,
    *,
    catalog_prefix: str = "runtime",
) -> ExtensionDomainIdentity:
    publisher = None
    extension_api = None
    if manifest is not None:
        try:
            parsed = ModuleManifestV2.model_validate(dict(manifest))
        except ValidationError:
            # Catalog rendering must not reinterpret or repair an invalid stored
            # package. Package validation remains the authoritative boundary.
            parsed = None
        if parsed is not None:
            extension_api = parsed.compatibility.extension_api
            if parsed.publisher is not None:
                publisher = parsed.publisher.model_dump()

    return ExtensionDomainIdentity(
        catalog_id=f"{catalog_prefix}:{module_id}",
        module_id=module_id,
        compatibility_mode="native-v2",
        migration_required=False,
        publisher=publisher,
        extension_api=extension_api,
    )
