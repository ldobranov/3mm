"""A peer request cannot hide behind supported scopes or an earlier approval."""

import os

import pytest
from sqlalchemy import update, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.tests.test_application_authority_management import (
    installed as managed_state,
    native,
    review,
    decide,
    identity,
)
from backend.tests.test_application_authority_subjects import (
    installed as source_subject,
    source_installed,
)
from backend.tests.test_application_checkpoint_authority import store_checkpoint_package
from three_mm_protocol.tests.test_application_peer_bindings import peer_request


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Actual POSIX Core review keys/guard"
)


def test_new_peer_requests_invalidate_approved_plan_and_cannot_be_omitted_from_supported_selection(
    managed_state,
):
    state = managed_state
    with state.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status="disabled"))
    old_proof = native(state)
    old_plan = decide(state, review(state, old_proof), "approve")
    definition = state.validated.application_extension.model_dump(mode="json")
    manifest = state.validated.manifest.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["platform_permissions"] = ["installation.peers.enroll"]
    definition["peer_bindings"] = [peer_request(operations=["read"])]
    manifest["permissions"].append("installation.peers.enroll")
    manifest["configuration_schema"]["properties"]["PEER_LINK"] = {"type": "string"}
    store_checkpoint_package(state, definition, manifest)
    with state.engine.begin() as db:
        db.execute(
            update(Installation).values(
                configuration={**state.configuration, "PEER_LINK": "peer_" + "a" * 32}
            )
        )
    with pytest.raises(authority.AuthorityManagementError):
        decide(state, old_plan, "apply")
    # Unsupported subjects cannot even record a fresh native attestation through
    # this manager. Keep that stronger existing refusal; never relax it for a test.
    with pytest.raises(
        authority.AuthorityManagementError, match="unsupported_authority"
    ):
        native(state)
    status = state.manager.inspect(1)
    assert not status["review_available"] and not status["grant_effective"]
    assert "unsupported_authority" in status["review_blockers"]
    # An earlier genuine local native attestation is not approval of the new
    # artifact. Selecting a supported family cannot hide its unsupported peers.
    for scopes in (["command:pulse"], ["connector:business_api"]):
        with pytest.raises(authority.AuthorityManagementError):
            state.manager.create_review(
                1,
                actor_token=state.token,
                request_id=identity(),
                native_review_id=old_proof["native_review_id"],
                scopes=scopes,
            )
    with Session(state.engine) as db:
        assert db.scalar(select(Grant)) is None
