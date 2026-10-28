"""Bounded admin-only query choices. Catalog matches are not grants or leases."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services.application_authority_management import configured_manager
from three_mm_protocol.application_composition import assess_application_query


def configuration_fields(engine, definition, current):
    manager = configured_manager(engine)
    with Session(engine) as db:
        rows = db.execute(select(Installation.id, Installation.instance_id).where(
            Installation.enabled.is_(True), Installation.status == 'active',
            Installation.module_id != definition.module_id).order_by(Installation.module_id).limit(65)).all()
    candidates = []
    for identifier, instance in rows[:64]:
        try:
            prepared = manager._prepare(identifier, include_queries=False)
            app = prepared.package.application_extension
            if app.query_dependencies or app.storage.relational is not None:
                continue
            candidates.append((instance, prepared, app))
        except Exception:
            continue  # Never substitute unchecked package metadata.
    fields = []
    for dependency in definition.query_dependencies:
        choices = []
        for instance, prepared, app in candidates:
            for export in app.query_exports:
                if assess_application_query(definition, app, binding_id=dependency.binding_id,
                        export_id=export.export_id).compatible:
                    choices.append(dict(instance_id=instance, export_id=export.export_id,
                        module_id=app.module_id, version=app.version, artifact_sha256=prepared.pin.sha256))
        fields.append(dict(key=dependency.provider_instance_config_key, kind='application_query',
            export_key=dependency.provider_export_config_key, label=dependency.contract.contract_id + ' · ' + dependency.contract.contract_version,
            binding_id=dependency.binding_id, required=True, description=None,
            value=current.get(dependency.provider_instance_config_key),
            export_value=current.get(dependency.provider_export_config_key), choices=choices[:64],
            choices_truncated=len(rows)>64 or len(choices)>64))
    return fields
