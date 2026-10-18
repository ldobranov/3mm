"""Closed additive HTTP scope grammar, not native trust or resource authority."""

import pytest

from backend.routes.application_authority import ReviewRequest


def request(scopes, **extra):
    return ReviewRequest.model_validate(
        {
            "request_id": "a" * 32,
            "native_review_id": "b" * 32,
            "scopes": scopes,
            **extra,
        }
    )


def test_new_http_bound_requires_an_exact_peer_read_and_keeps_old_caps():
    # Request parsing cannot authorize or prove a declared resource; unknown
    # logical IDs still require the real current-source manager to refuse them.
    peers = [f"peer:binding_{index}:read" for index in range(261)]
    assert len(request(peers).scopes) == 261
    with pytest.raises(ValueError):
        request([*peers, "peer:one_more:read"])
    legacy = [f"command:binding_{index}" for index in range(198)]
    with pytest.raises(ValueError):
        request(legacy)
    assert len(request(legacy[:197]).scopes) == 197
    status = [*legacy, "status:peer_" + "c" * 32 + ":read"]
    status += [f"connector:extra_{index}" for index in range(30)]
    assert len(request(status).scopes) == 229
    with pytest.raises(ValueError):
        request([*status, "connector:one_more"])


@pytest.mark.parametrize(
    "scope",
    [
        "peer:*:read",
        "peer:binding:write",
        "peer:binding:enroll",
        "peer:binding:revoke",
        "peer:binding:approve",
        "peer:binding:report",
        "peer:binding:rotate",
        "platform:installation.peers.enroll",
        "platform:installation.identity.prove",
        "peer:binding:read:extra",
        True,
        1,
        None,
    ],
)
def test_http_peer_vocabulary_cannot_be_a_wildcard_signer_or_mutation(scope):
    with pytest.raises(ValueError):
        request([scope])


@pytest.mark.parametrize(
    "field,value",
    [
        ("configuration", {"PEER_LINK": "peer_" + "c" * 32}),
        ("resources", {"peer_reads": []}),
        ("owner", "foreign"),
        ("review_completed", True),
        ("subject_version", 9),
        ("scopes", [{"binding_id": "binding"}]),
    ],
)
def test_http_caller_cannot_replace_sources_or_create_native_trust(field, value):
    if field == "scopes":
        with pytest.raises(ValueError):
            request(value)
    else:
        with pytest.raises(ValueError):
            request(["peer:binding:read"], **{field: value})
