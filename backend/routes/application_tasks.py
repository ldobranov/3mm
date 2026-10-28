"""Administrator reconciliation only; scheduling remains an owned SDK action."""
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.application_task import ApplicationTaskRun as Run
from backend.services.application_authority_management import configured_manager, AuthorityManagementError
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_tasks import _snapshot, _sweep
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router = APIRouter(tags=["application-tasks"])


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmed_external_outcome_reviewed: Literal[True]

    @field_validator("confirmed_external_outcome_reviewed", mode="before")
    @classmethod
    def explicit_review(cls, value):
        if value is not True:
            raise ValueError("Explicit outcome review is required")
        return value


@router.post("/{module_id}/tasks/{task_run_id}/resolve", dependencies=[Depends(require_admin)])
def resolve_task(module_id: str, task_run_id: str, request: ResolveRequest,
                 authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    app = db.scalar(select(Installation).where(Installation.module_id == module_id))
    if app is None:
        raise HTTPException(404, "Application was not found")
    identifier = app.id
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "A current administrator login is required")
    manager = configured_manager(db.get_bind().engine)
    db.rollback()
    try:
        with manager._write(identifier, authorization.split(" ", 1)[1], request.request_id,
                "task_resolution", {"task_run_id": task_run_id, "confirmed_external_outcome_reviewed": True}) as (scope, _key, _mutation, _actor, result):
            if result:
                return result
            current = scope.get(Installation, identifier, populate_existing=True)
            if current.enabled or current.status != "disabled":
                raise ValueError("Stop the application and review the task outcome first")
            _sweep(scope, identifier)
            row = scope.get(Run, task_run_id)
            if (row is None or row.installation_id != identifier or row.incarnation != current.authority_incarnation
                    or row.state != "unknown"):
                raise ValueError("Task has no unresolved execution")
            row.state, row.lease_token, row.worker_generation = "resolved", None, None
            result.update(_snapshot(scope, row))
            return result
    except AuthorityManagementError as error:
        raise HTTPException(403 if error.reason == "actor_unavailable" else 409, "Task reconciliation is unavailable") from None
    except (AuthorityReviewKeyError, ValueError):
        raise HTTPException(409, "Stop the application and review its unresolved outcome") from None
