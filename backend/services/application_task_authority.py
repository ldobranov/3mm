"""Exact owned task profile in the existing sealed authority framework."""
from typing import Literal
from pydantic import Field, model_validator
from three_mm_protocol.application_tasks import ApplicationTaskV1
from three_mm_protocol.application_extension import ApplicationOperationV1
from backend.services.application_authority_context import (
    ContextModel, AuthorityPrincipal, Digest, TaskScopeKey, AuthorityTaskPolicyV11,
    AuthorityReviewContextV1, AuthoritySelectionV1,
)
from backend.services.application_authority_policy import PolicySubjectV1, CorePolicyEvidenceV1


class ResolvedTaskScope(ContextModel):
    declaration: ApplicationTaskV1
    operation: ApplicationOperationV1
    owner: AuthorityPrincipal
    package_artifact_sha256: Digest

    @model_validator(mode="after")
    def exact_handler(self):
        if (self.operation.operation_id != self.declaration.handler_operation_id
                or self.operation.kind != "task" or self.operation.audiences != ("internal",)
                or self.operation.timeout_seconds != self.declaration.max_runtime_seconds):
            raise ValueError("Task scope requires its exact internal handler")
        return self


def validate_tasks(value, principal, artifact):
    if value.connectors or not value.tasks:
        raise ValueError("Task authority requires the bounded task profile")
    if value.commands and any(task.declaration.profile != "bounded_task_v1" for task in value.tasks):
        raise ValueError("Command effects require the explicit composed task profile")
    ids = set()
    for task in value.tasks:
        if (task.owner != principal or task.package_artifact_sha256 != artifact
                or task.declaration.task_id in ids):
            raise ValueError("Tasks require distinct exact owned artifact requests")
        ids.add(task.declaration.task_id)


class TaskPolicySubjectV11(PolicySubjectV1):
    subject_version: Literal[11]
    tasks: tuple[ResolvedTaskScope, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def exact_owned(self):
        validate_tasks(self, self.binding.principal, self.binding.candidate.sha256)
        return self


class TaskPolicyEvidenceV11(CorePolicyEvidenceV1):
    evidence_version: Literal[11]
    tasks: tuple[ResolvedTaskScope, ...] = Field(min_length=1, max_length=8)
    required_scopes: tuple[TaskScopeKey, ...] = Field(max_length=72)

    @model_validator(mode="after")
    def exact_owned(self):
        validate_tasks(self, self.binding.principal, self.binding.candidate.sha256)
        return self


class TaskReviewContextV11(AuthorityReviewContextV1):
    context_version: Literal[11]
    policy: AuthorityTaskPolicyV11
    tasks: tuple[ResolvedTaskScope, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def exact_owned(self):
        validate_tasks(self, self.principal, self.candidate.sha256)
        return self


class TaskSelectionV11(AuthoritySelectionV1):
    selection_version: Literal[11]
    scopes: tuple[TaskScopeKey, ...] = Field(max_length=72)
