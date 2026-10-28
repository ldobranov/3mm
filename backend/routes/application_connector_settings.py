"""Core administrator dialog transport; deliberately not application invoke."""
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services import application_connector_settings as settings
from backend.services.application_authority_context import _unique_object
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import PolicyReviewStoreError
from backend.services.application_connectors import ApplicationConnectorError
from backend.services.application_secrets import ApplicationSecretError
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router = APIRouter()
ROOT = '/packages/{sha256}/connector-settings'


def _token(authorization):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, {'code': 'access_denied'})
    return authorization.split(' ', 1)[1].strip()


def _engine(db):
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, {'code': 'unavailable'})
    engine = db.get_bind().engine
    db.rollback()  # End the read-only authentication snapshot before the writer.
    return engine


def _call(function, engine, sha256, token, *args):
    try:
        return function(authority.configured_manager(engine), sha256, *args, token)
    except (authority.AuthorityManagementError, PolicyReviewStoreError) as error:
        reason = getattr(error, 'reason', 'actor_unavailable')
        code = ('access_denied' if reason in {'actor_unavailable', 'review_required'} else
            'invalid_request' if reason == 'invalid_request' else
            'stop_required' if reason == 'stop_required' else
            'conflict' if reason in {'snapshot_conflict', 'request_conflict', 'artifact_changed'} else 'unavailable')
        raise HTTPException(403 if code == 'access_denied' else 422 if code == 'invalid_request' else 409, {'code': code}) from None
    except (ApplicationSecretError, ApplicationConnectorError, ValidationError):
        raise HTTPException(422, {'code': 'invalid_request'}) from None
    except (AuthorityReviewKeyError, SQLAlchemyError, OSError, ValueError, RuntimeError, KeyError, TypeError):
        # Never stringify failures carrying request objects or credential values.
        raise HTTPException(409, {'code': 'unavailable'}) from None


@router.get(ROOT)
def inspect(sha256: str, response: Response, authorization: str | None = Header(default=None),
        _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return _call(settings.inspect, _engine(db), sha256, _token(authorization))


@router.get(ROOT + '/outcomes/{request_id}')
def outcome(sha256: str, request_id: str, response: Response, authorization: str | None = Header(default=None),
        _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return _call(settings.outcome, _engine(db), sha256, _token(authorization), request_id)


@router.post(ROOT + '/{connector_id}')
async def configure(sha256: str, connector_id: str, request: Request, response: Response,
        authorization: str | None = Header(default=None), _admin: User = Depends(require_admin),
        db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    # FastAPI's ordinary validation response echoes invalid input. Parse this
    # credential-bearing body privately and return only a fixed redacted code.
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 48 * 1024:
            raise HTTPException(413, {'code': 'invalid_request'})
        raw.extend(chunk)
    try:
        body = settings.ConnectorSettingsRequest.model_validate(
            json.loads(raw, object_pairs_hook=_unique_object))
        if body.credential and any(len(value) > 4096 for value in body.credential.values()):
            raise ValueError()
    except (ValueError, TypeError, ValidationError, RecursionError):
        raise HTTPException(422, {'code': 'invalid_request'}) from None
    return await run_in_threadpool(_call, settings.configure, _engine(db),
        sha256, _token(authorization), connector_id, body)
