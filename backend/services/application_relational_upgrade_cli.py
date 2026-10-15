"""Local admin upgrade commands; token stays in hidden prompt/private pipes."""

from sqlalchemy.orm import Session

from backend.services.application_policy_reviews import _actor
from backend.services.application_relational_upgrade_admin import inspect_upgrade_source
from backend.services.authority_metadata import authority_transaction
from three_mm_runtime.application_relational_upgrade_control import (
    OPERATIONS,
    response_status,
)

COMMANDS = {
    "upgrade-relational": "upgrade_application_relational",
    "confirm-relational-upgrade": "confirm_application_relational_upgrade",
    "confirm-relational-rollback": "confirm_application_relational_rollback",
    "finish-relational-restore": "finish_application_relational_restore",
}
LOCAL_COMMANDS = {"adopt-relational-version"}


def add_commands(commands):
    candidate = commands.add_parser(
        "adopt-relational-version",
        help="Bind an uploaded newer version after confirmed stop; no execution or rights",
    )
    candidate.add_argument("--installation-id", required=True, type=int)
    candidate.add_argument("--package-id", required=True, type=int)
    candidate.add_argument("--artifact-sha256", required=True)
    candidate.add_argument("--expected-current-artifact-sha256", required=True)
    candidate.add_argument("--source-recovery-id", required=True)
    candidate.add_argument("--expected-recovery-revision", required=True)
    candidate.add_argument("--request-id", required=True)
    candidate.add_argument(
        "--confirm-adopt-without-execution", required=True, action="store_true"
    )
    inspect = commands.add_parser(
        "inspect-relational-upgrade",
        help="Read a sealed lifecycle revision; no runtime effects",
    )
    inspect.add_argument("--installation-id", required=True, type=int)
    inspect.add_argument("--source-action-id", required=True)
    for name, action in COMMANDS.items():
        command = commands.add_parser(
            name,
            help={
                "upgrade": "Explicit forward migration of the exact reviewed candidate; never start",
                "published": "Readonly confirmation of a fully published upgrade; never replay migrations",
                "rollback": "Readonly confirmation of a completed witnessed rollback; never restore again",
                "restore": "Finish a partially interrupted fixed restore; preserve candidates and stopped state",
            }[OPERATIONS[action][0]],
        )
        command.add_argument("--installation-id", required=True, type=int)
        command.add_argument("--source-action-id", required=True)
        command.add_argument("--expected-source-revision", required=True)
        command.add_argument("--expected-grant-record-revision", required=True)
        command.add_argument("--request-id", required=True)
        command.add_argument(
            "--" + OPERATIONS[action][1].replace("_", "-"),
            required=True,
            action="store_true",
        )


def execute(manager, args, token):
    if args.command == "adopt-relational-version":
        from backend.services.application_relational_candidate import (
            adopt_relational_version,
        )

        return adopt_relational_version(
            manager,
            args.installation_id,
            actor_token=token,
            request_id=args.request_id,
            package_id=args.package_id,
            artifact_sha256=args.artifact_sha256,
            expected_current_artifact_sha256=args.expected_current_artifact_sha256,
            source_recovery_id=args.source_recovery_id,
            expected_recovery_revision=args.expected_recovery_revision,
            confirm_adopt_without_execution=args.confirm_adopt_without_execution,
        )
    if args.command == "inspect-relational-upgrade":
        return inspect_upgrade_source(
            manager,
            args.installation_id,
            actor_token=token,
            source_action_id=args.source_action_id,
        )
    with Session(manager.engine) as db, authority_transaction(db):
        _actor(db, token)
    from backend.config import get_settings
    from three_mm_runtime.update_helper_client import UpdateHelperClient

    action = COMMANDS[args.command]
    consent = OPERATIONS[action][1]
    payload = {
        "action": action,
        "installation_id": args.installation_id,
        "source_action_id": args.source_action_id,
        "actor_token": token,
        "expected_source_revision": args.expected_source_revision,
        "expected_grant_record_revision": args.expected_grant_record_revision,
        "request_id": args.request_id,
        consent: getattr(args, consent),
    }
    result = UpdateHelperClient(
        get_settings().applications.helper_socket, timeout_seconds=420
    ).application_relational_upgrade(payload)
    return {
        "status": response_status(action),
        "upgrade": result,
        "permission_approval": "not_evaluated",
    }
