"""Admin-only installed-artifact permission review. No native-proof upload API."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.module import ApplicationExtensionInstallation
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services import application_authority_management as authority
from backend.services.application_authority_management import AuthorityManagementError
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db


router = APIRouter(prefix='/api/v1/application-extensions', tags=['application-authority'])
Identifier = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Scope = Annotated[str, Field(pattern=r'^(command|connector|event|publication):[a-z][a-z0-9_]{0,95}$')]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: Identifier
    native_review_id: Identifier
    scopes: list[Scope] = Field(max_length=96)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: Identifier
    expected_revision: Identifier
    fingerprint: Digest


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: Identifier
    expected_revision: Identifier


def _target(db, module_id):
    identifier = db.scalar(select(ApplicationExtensionInstallation.id).where(
        ApplicationExtensionInstallation.module_id == module_id))
    if identifier is None:
        raise HTTPException(404, 'Application extension was not found')
    return identifier


def _token(authorization):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'A current administrator login is required')
    return authorization.split(' ', 1)[1].strip()


def _call(db, response, operation):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return operation(authority.configured_manager(db.get_bind().engine))
    except AuthorityManagementError as exc:
        raise HTTPException(403 if exc.reason == 'actor_unavailable' else 409,
            {'code': exc.reason}) from None
    except (AuthorityReviewKeyError, SQLAlchemyError, OSError, ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(409, {'code': 'authority_unavailable'}) from None


@router.get('/{module_id}/authority', dependencies=[Depends(require_admin)])
def authority_status(module_id: str, response: Response, db: Session = Depends(get_db)):
    identifier = _target(db, module_id)
    return _call(db, response, lambda manager: manager.inspect(identifier))


@router.post('/{module_id}/authority/reviews', dependencies=[Depends(require_admin)])
def create_review(module_id: str, request: ReviewRequest, response: Response,
        authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    identifier, token = _target(db, module_id), _token(authorization)
    return _call(db, response, lambda manager: manager.create_review(identifier,
        actor_token=token, **request.model_dump()))


@router.post('/{module_id}/authority/reviews/{plan_id}/{decision}', dependencies=[Depends(require_admin)])
def decide_review(module_id: str, plan_id: Identifier, decision: Literal['approve', 'deny', 'apply'],
        request: DecisionRequest, response: Response, authorization: str | None = Header(default=None),
        db: Session = Depends(get_db)):
    identifier, token = _target(db, module_id), _token(authorization)
    return _call(db, response, lambda manager: manager.decide(identifier, actor_token=token,
        plan_id=plan_id, decision=decision, **request.model_dump()))


@router.post('/{module_id}/authority/revoke', dependencies=[Depends(require_admin)])
def revoke_grant(module_id: str, request: RevokeRequest, response: Response,
        authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    identifier, token = _target(db, module_id), _token(authorization)
    return _call(db, response, lambda manager: manager.revoke(identifier,
        actor_token=token, **request.model_dump()))
