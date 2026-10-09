"""Local Core administration for explicit reviewed-native trust, NOT isolation.

Run as the Core service account with its existing environment and local DB.
Login tokens are prompted without echo, never CLI arguments or printed output.
No source code is executed, no helper/device/network operation is dispatched.
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
    revoke = commands.add_parser('revoke-native-review')
    revoke.add_argument('--installation-id', required=True, type=int)
    revoke.add_argument('--native-review-id', required=True)
    revoke.add_argument('--expected-revision', required=True)
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
        elif args.command == 'native-review':
            with args.review_document.open('rb') as document:
                contents = document.read(1_048_577)
            if not contents or len(contents) > 1_048_576:
                raise AuthorityManagementError('invalid_review_document')
            result = manager.record_native_review(args.installation_id, actor_token=token,
                request_id=uuid.uuid4().hex, artifact_sha256=args.artifact_sha256,
                review_document_sha256=hashlib.sha256(contents).hexdigest(),
                native_code_review_completed=args.code_review_completed,
                accepts_native_host_risk=args.accept_native_host_risk)
        else:
            result = manager.revoke_native_review(args.installation_id, actor_token=token,
                request_id=uuid.uuid4().hex, native_review_id=args.native_review_id,
                expected_revision=args.expected_revision)
        print(json.dumps(result, sort_keys=True))
    except (AuthorityManagementError, AuthorityReviewKeyError, PolicyReviewStoreError, OSError, ValueError):
        raise SystemExit('Local authority administration failed; no permission fallback was applied') from None


if __name__ == '__main__':
    main()
