"""Read sealed local lifecycle revisions; never infer runtime effects or rights."""

from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.services import application_authority_management as authority
from backend.services.application_authority_sources import _configuration
from backend.services.application_policy_reviews import _actor
from backend.services.authority_metadata import authority_transaction
from three_mm_runtime.application_activation import application_instance_id


def inspect_upgrade_source(
    manager,
    installation_id,
    *,
    actor_token,
    source_action_id,
    expected_source_revision=None,
    expected_grant_record_revision=None,
    include_configuration=False,
):
    identifier = authority._identifier(source_action_id)
    prepared = manager._prepare(installation_id)
    status = manager.inspect(installation_id)
    with (
        manager.keys.locked() as key,
        Session(manager.engine) as db,
        authority_transaction(db),
    ):
        _actor(db, actor_token)
        row = db.get(Action, identifier, populate_existing=True)
        value = authority._load(db, key, "action", row, identifier)
        if (
            value["installation_id"] != installation_id
            or value["data"].get("operation")
            not in {
                "relational_prepare",
                "relational_prepare_migrated",
                "relational_recovery",
                "relational_upgrade_prepared",
                "relational_upgrade_confirmation",
                "relational_upgrade_rollback_confirmation",
            }
            or expected_source_revision is not None
            and value["revision"] != authority._identifier(expected_source_revision)
            or expected_grant_record_revision is not None
            and status["grant_record_revision"]
            != authority._identifier(expected_grant_record_revision)
        ):
            raise authority.AuthorityManagementError("upgrade_source_changed")
        result = {
            "source_action_id": identifier,
            "source_revision": value["revision"],
            "state": value["state"],
            "operation": value["data"]["operation"],
            "grant_record_revision": status["grant_record_revision"],
            "permission_approval": "not_evaluated",
        }
        if not include_configuration:
            return result
        return {
            "source_revision": value["revision"],
            "state": value["state"],
            "sha256": prepared[0].sha256,
            "instance_id": application_instance_id(prepared[0].module_id),
            "configuration": _configuration(db, installation_id, prepared[1]),
            "source_ticket": value["data"]["result"]["ticket"],
        }
