"""Local Core administration for explicit reviewed-native trust, NOT isolation.

Run as the Core service account with its existing environment and local DB.
Login tokens are prompted without echo, never CLI arguments or printed output.
Trust commands execute no source code. Explicit relational lifecycle commands call
the fixed local helper with separate consent, without approving runtime rights.
"""

import argparse
import getpass
import hashlib
import json
from pathlib import Path
import uuid

from sqlalchemy.orm import Session

from backend.db.audit_log import AuditLog
from backend.services.application_authority_management import configured_manager, AuthorityManagementError
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import _actor, PolicyReviewStoreError
from backend.services.authority_metadata import authority_transaction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('provision-key', help='Explicit local key creation, never permission approval')
    for operation in ('rotate-key', 'recover-key'):
        key_command = commands.add_parser(operation, help='Invalidate old seals; never restore grants automatically')
        key_command.add_argument('--expected-key-id', required=True)
    native = commands.add_parser('native-review', help='Record completed manual review of an EXACT installed artifact')
    native.add_argument('--installation-id', required=True, type=int)
    native.add_argument('--artifact-sha256', required=True)
    native.add_argument('--review-document', required=True, type=Path)
    native.add_argument('--code-review-completed', required=True, action='store_true')
    native.add_argument('--accept-native-host-risk', required=True, action='store_true')
    native.add_argument('--accept-same-origin-ui-risk', action='store_true', help='Compiled UI is trusted same-origin native code, NOT a sandbox')
    native.add_argument('--built-ui-sha256', help='Exact locally inspected compiled build; required with UI risk acceptance')
    ui_build = commands.add_parser('inspect-ui-build', help='Read verified build identity; no compilation, execution or permission approval')
    ui_build.add_argument('--installation-id', required=True, type=int)
    revoke = commands.add_parser('revoke-native-review')
    revoke.add_argument('--installation-id', required=True, type=int)
    revoke.add_argument('--native-review-id', required=True)
    revoke.add_argument('--expected-revision', required=True)
    preparation = commands.add_parser('prepare-relational', help='Explicit first preparation; never enable or approve rights')
    preparation.add_argument('--installation-id', required=True, type=int)
    preparation.add_argument('--expected-grant-record-revision', required=True)
    preparation.add_argument('--confirm-fresh-owned-namespace', required=True, action='store_true')
    preparation.add_argument('--confirm-owned-business-migrations', required=True, action='store_true')
    registration = commands.add_parser('register-relational', help='Register a new relational package without execution or rights')
    registration.add_argument('--package-id', required=True, type=int)
    registration.add_argument('--artifact-sha256', required=True)
    registration.add_argument('--request-id', required=True)
    registration.add_argument('--configuration-file', type=Path)
    registration.add_argument('--confirm-register-without-start', required=True, action='store_true')
    activation = commands.add_parser('activate-relational', help='Start an exact prepared service; fresh rights review still required')
    activation.add_argument('--installation-id', required=True, type=int)
    activation.add_argument('--source-preparation-id', required=True)
    activation.add_argument('--request-id', required=True)
    activation.add_argument('--expected-grant-record-revision', required=True)
    activation.add_argument('--confirm-start-prepared-service', required=True, action='store_true')
    start_status = commands.add_parser('inspect-relational-start', help='Read exact historical Core start revision; no process or permission changes')
    start_status.add_argument('--installation-id', required=True, type=int)
    start_status.add_argument('--source-activation-id', required=True)
    recovery = commands.add_parser('recover-relational-start', help='Explicit verified stop; preserves prepared state, never restarts or grants rights')
    recovery.add_argument('--installation-id', required=True, type=int)
    recovery.add_argument('--source-activation-id', required=True)
    recovery.add_argument('--expected-activation-revision', required=True)
    recovery.add_argument('--request-id', required=True)
    recovery.add_argument('--confirm-stop-preserve-prepared-state', required=True, action='store_true')
    recovery_status = commands.add_parser('inspect-relational-recovery', help='Read sealed recovery revision; never infer current process outcome')
    recovery_status.add_argument('--installation-id', required=True, type=int)
    recovery_status.add_argument('--source-recovery-id', required=True)
    reactivation = commands.add_parser('reactivate-relational', help='Fresh one-shot start after confirmed stop and current rights review; never enable boot')
    reactivation.add_argument('--installation-id', required=True, type=int)
    reactivation.add_argument('--source-recovery-id', required=True)
    reactivation.add_argument('--expected-recovery-revision', required=True)
    reactivation.add_argument('--expected-grant-record-revision', required=True)
    reactivation.add_argument('--request-id', required=True)
    reactivation.add_argument('--confirm-restart-stopped-prepared-service', required=True, action='store_true')
    boot = commands.add_parser('enable-relational-boot', help='Explicit boot enable for an exact healthy prepared start; never start/restart or grant rights')
    boot.add_argument('--installation-id', required=True, type=int)
    boot.add_argument('--source-activation-id', required=True)
    boot.add_argument('--expected-activation-revision', required=True)
    boot.add_argument('--expected-grant-record-revision', required=True)
    boot.add_argument('--request-id', required=True)
    boot.add_argument('--confirm-enable-prepared-boot', required=True, action='store_true')
    prep_status = commands.add_parser('inspect-relational-preparation', help='Read sealed failed migration revision; no runtime effects')
    prep_recovery = commands.add_parser('recover-relational-preparation', help='Reconcile ONLY a restored-empty initial checkpoint; never migrate or start')
    for command in (prep_status, prep_recovery):
        command.add_argument('--installation-id', required=True, type=int)
        command.add_argument('--source-preparation-id', required=True)
        command.add_argument('--source-namespace-id', required=True)
        command.add_argument('--expected-grant-record-revision', required=True)
    prep_recovery.add_argument('--expected-preparation-revision', required=True)
    prep_recovery.add_argument('--request-id', required=True)
    prep_recovery.add_argument('--confirm-restored-empty-checkpoint', required=True, action='store_true')
    resume = commands.add_parser('resume-relational-preparation', help='Separate fresh migration consent AFTER confirmed empty recovery; never start')
    resume.add_argument('--installation-id', required=True, type=int)
    resume.add_argument('--source-recovery-id', required=True)
    resume.add_argument('--expected-recovery-revision', required=True)
    resume.add_argument('--expected-grant-record-revision', required=True)
    resume.add_argument('--request-id', required=True)
    resume.add_argument('--confirm-owned-business-migrations', required=True, action='store_true')
    resume_status = commands.add_parser('inspect-relational-preparation-recovery', help='Read sealed empty-recovery revision; no runtime effects')
    resume_status.add_argument('--installation-id', required=True, type=int)
    resume_status.add_argument('--source-recovery-id', required=True)
    from backend.services.application_relational_upgrade_cli import add_commands, COMMANDS as UPGRADE_COMMANDS, LOCAL_COMMANDS
    add_commands(commands)
    args = parser.parse_args()
    from backend.database import engine
    manager = configured_manager(engine)
    token = getpass.getpass('Current Core administrator login token (hidden): ')
    try:
        if args.command in {'provision-key', 'rotate-key', 'recover-key'}:
            # Check current login before touching disk; recheck when auditing.
            # A crash may leave a key with no audit, but never a native review or
            # grant. First-provision retry reuses that SAME key. Rotation/recovery
            # with the old expected key ID instead fails closed after replacement.
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            if args.command == 'provision-key':
                key = manager.keys.provision()
            elif args.command == 'rotate-key':
                key = manager.keys.rotate(expected_key_id=args.expected_key_id)
            else:
                key = manager.keys.recover(expected_key_id=args.expected_key_id)
            with manager.keys.locked() as lease, Session(engine) as db, authority_transaction(db) as mutation:
                actor = _actor(db, token)
                lease._check(db)
                db.add(AuditLog(user_id=actor[0], action='APPLICATION_AUTHORITY_KEY',
                    entity_type='core_authority', changes={'key_id': key.key_id, 'operation': args.command}))
                mutation.advance_guard_revision()
            result = {'key_id': key.key_id, 'permission_approval': 'not_evaluated'}
        elif args.command in set(UPGRADE_COMMANDS) | LOCAL_COMMANDS | {'inspect-relational-upgrade'}:
            from backend.services.application_relational_upgrade_cli import execute
            result = execute(manager, args, token)
        elif args.command == 'inspect-ui-build':
            with Session(engine) as db:
                _actor(db, token)
            prepared = manager._prepare(args.installation_id)
            if prepared.built_ui_sha256 is None:
                raise AuthorityManagementError('ui_build_unavailable')
            result = {'installation_id': args.installation_id, 'artifact_sha256': prepared[0].sha256,
                'built_ui_sha256': prepared.built_ui_sha256, 'permission_approval': 'not_evaluated',
                'browser_isolation': False}
        elif args.command == 'native-review':
            with args.review_document.open('rb') as document:
                contents = document.read(1_048_577)
            if not contents or len(contents) > 1_048_576:
                raise AuthorityManagementError('invalid_review_document')
            result = manager.record_native_review(args.installation_id, actor_token=token,
                request_id=uuid.uuid4().hex, artifact_sha256=args.artifact_sha256,
                review_document_sha256=hashlib.sha256(contents).hexdigest(),
                native_code_review_completed=args.code_review_completed,
                accepts_native_host_risk=args.accept_native_host_risk,
                accepts_same_origin_ui_risk=args.accept_same_origin_ui_risk,
                built_ui_sha256=args.built_ui_sha256)
        elif args.command == 'register-relational':
            from backend.services.application_authority_context import _unique_object
            from backend.services.application_relational_registration import register_relational_package
            configuration = {}
            if args.configuration_file is not None:
                with args.configuration_file.open('rb') as source:
                    contents = source.read(32_769)
                if not contents or len(contents) > 32_768:
                    raise AuthorityManagementError('invalid_configuration')
                configuration = json.loads(contents, object_pairs_hook=_unique_object)
            result = register_relational_package(manager, package_id=args.package_id,
                artifact_sha256=args.artifact_sha256, configuration=configuration,
                actor_token=token, request_id=args.request_id,
                confirm_register_without_start=args.confirm_register_without_start)
        elif args.command == 'inspect-relational-preparation':
            from backend.services.application_relational_preparation_recovery import inspect_empty_preparation_source
            result = inspect_empty_preparation_source(manager, args.installation_id,
                actor_token=token, source_preparation_id=args.source_preparation_id,
                source_namespace_id=args.source_namespace_id,
                expected_grant_record_revision=args.expected_grant_record_revision)
        elif args.command == 'inspect-relational-preparation-recovery':
            from backend.services.application_relational_preparation_recovery import inspect_empty_recovery_record
            result = inspect_empty_recovery_record(manager, args.installation_id,
                actor_token=token, source_recovery_id=args.source_recovery_id)
        elif args.command in {'recover-relational-preparation', 'resume-relational-preparation'}:
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            resumed = args.command == 'resume-relational-preparation'
            payload = {'action': 'resume_application_relational_preparation' if resumed else 'recover_application_relational_preparation',
                'installation_id': args.installation_id, 'actor_token': token,
                'expected_grant_record_revision': args.expected_grant_record_revision, 'request_id': args.request_id}
            if resumed:
                payload.update(source_recovery_id=args.source_recovery_id, expected_recovery_revision=args.expected_recovery_revision,
                    confirm_owned_business_migrations=args.confirm_owned_business_migrations)
            else:
                payload.update(source_preparation_id=args.source_preparation_id, source_namespace_id=args.source_namespace_id,
                    expected_preparation_revision=args.expected_preparation_revision,
                    confirm_restored_empty_checkpoint=args.confirm_restored_empty_checkpoint)
            recovered = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=180).reconcile_relational_preparation(payload)
            result = {'status': 'prepared_not_started' if resumed else 'restored_empty_not_started',
                'preparation' if resumed else 'recovery': recovered, 'permission_approval': 'not_evaluated'}
        elif args.command == 'prepare-relational':
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            # Explicit timeout only for this bounded, non-retried preparation.
            prepared = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=180).prepare_application_relational(
                args.installation_id, token, args.expected_grant_record_revision,
                confirm_fresh_owned_namespace=args.confirm_fresh_owned_namespace,
                confirm_owned_business_migrations=args.confirm_owned_business_migrations)
            result = {'status': 'prepared_not_started', 'preparation': prepared,
                'permission_approval': 'not_evaluated'}
        elif args.command == 'activate-relational':
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            # Bounded start/health/cleanup, without replay on timeout/lost reply.
            activated = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=420).activate_application_relational(
                args.installation_id, token, args.expected_grant_record_revision,
                source_preparation_id=args.source_preparation_id, request_id=args.request_id,
                confirm_start_prepared_service=args.confirm_start_prepared_service)
            result = {'status': 'active_review_required', 'activation': activated,
                'permission_approval': 'not_evaluated', 'boot_autostart_enabled': False}
        elif args.command == 'inspect-relational-start':
            from backend.services.application_relational_activation_recovery import inspect_activation_recovery_source
            result = inspect_activation_recovery_source(manager, args.installation_id,
                actor_token=token, source_activation_id=args.source_activation_id)
        elif args.command == 'inspect-relational-recovery':
            from backend.services.application_relational_reactivation import inspect_reactivation_source
            result = inspect_reactivation_source(manager, args.installation_id,
                actor_token=token, source_recovery_id=args.source_recovery_id)
        elif args.command == 'reactivate-relational':
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            restarted = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=420).reactivate_application_relational(
                args.installation_id, token, args.expected_grant_record_revision,
                source_recovery_id=args.source_recovery_id,
                expected_recovery_revision=args.expected_recovery_revision, request_id=args.request_id,
                confirm_restart_stopped_prepared_service=args.confirm_restart_stopped_prepared_service)
            result = {'status': 'active_review_required', 'reactivation': restarted,
                'permission_approval': 'not_evaluated', 'boot_autostart_enabled': False}
        elif args.command == 'enable-relational-boot':
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            boot_result = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=420).enable_application_relational_boot(
                args.installation_id, token, args.expected_grant_record_revision,
                source_activation_id=args.source_activation_id,
                expected_activation_revision=args.expected_activation_revision,
                request_id=args.request_id, confirm_enable_prepared_boot=args.confirm_enable_prepared_boot)
            result = {'status': 'boot_enabled_not_started', 'boot': boot_result,
                'permission_approval': 'not_evaluated', 'boot_autostart_enabled': True}
        elif args.command == 'recover-relational-start':
            with Session(engine) as db, authority_transaction(db):
                _actor(db, token)
            from backend.config import get_settings
            from three_mm_runtime.update_helper_client import UpdateHelperClient
            recovered = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=420).recover_application_relational_start(
                args.installation_id, token, args.expected_activation_revision,
                source_activation_id=args.source_activation_id, request_id=args.request_id,
                confirm_stop_preserve_prepared_state=args.confirm_stop_preserve_prepared_state)
            result = {'status': 'stopped_review_required', 'recovery': recovered,
                'permission_approval': 'not_evaluated', 'boot_autostart_enabled': False}
        else:
            result = manager.revoke_native_review(args.installation_id, actor_token=token,
                request_id=uuid.uuid4().hex, native_review_id=args.native_review_id,
                expected_revision=args.expected_revision)
        print(json.dumps(result, sort_keys=True))
    except (AuthorityManagementError, AuthorityReviewKeyError, PolicyReviewStoreError, OSError, ValueError, RuntimeError):
        if args.command in UPGRADE_COMMANDS:
            raise SystemExit('Relational upgrade/reconciliation is unconfirmed. Do not retry; retain evidence for fresh local review.') from None
        if args.command in {'recover-relational-preparation', 'resume-relational-preparation'}:
            raise SystemExit('Preparation reconciliation is unconfirmed. Do not retry; retain evidence for fresh local review.') from None
        if args.command == 'enable-relational-boot':
            raise SystemExit('Relational boot enable is unconfirmed. Do not retry; retain evidence for explicit stop/review.') from None
        if args.command in {'activate-relational', 'reactivate-relational'}:
            raise SystemExit('Relational activation is unconfirmed. Do not retry; preserve evidence for explicit recovery review.') from None
        if args.command == 'recover-relational-start':
            raise SystemExit('Relational start recovery is unconfirmed. Do not retry; retain evidence and obtain a fresh local review.') from None
        raise SystemExit('Local authority administration failed; no permission fallback was applied') from None


if __name__ == '__main__':
    main()
