"""M21 session-provider SDK interface tests (WP1): declaration validation."""

import pytest

from three_mm_application_sdk.session import (
    SESSION_SDK_ERROR,
    SessionProviderError,
    SessionTargetLimits,
    validate_session_provider_metadata,
)


def test_sdk_error_constant():
    assert SESSION_SDK_ERROR == "core.unsupported_session"


def test_valid_provider_metadata():
    validate_session_provider_metadata(
        provider_id="org.example.echo",
        contract_version="1.0",
        capability_ids=["org.example.echo"],
        control_actions=["resize"],
    )


def test_rejects_bad_provider_id():
    with pytest.raises(SessionProviderError):
        validate_session_provider_metadata(
            provider_id="Bad",
            contract_version="1.0",
            capability_ids=["org.example.echo"],
        )


def test_rejects_bad_contract_version():
    with pytest.raises(SessionProviderError):
        validate_session_provider_metadata(
            provider_id="org.example.echo",
            contract_version="latest",
            capability_ids=["org.example.echo"],
        )


def test_rejects_empty_capabilities():
    with pytest.raises(SessionProviderError):
        validate_session_provider_metadata(
            provider_id="org.example.echo", contract_version="1.0", capability_ids=[]
        )


def test_rejects_duplicate_capabilities():
    with pytest.raises(SessionProviderError):
        validate_session_provider_metadata(
            provider_id="org.example.echo",
            contract_version="1.0",
            capability_ids=["org.example.echo", "org.example.echo"],
        )


def test_rejects_invalid_control_action():
    with pytest.raises(SessionProviderError):
        validate_session_provider_metadata(
            provider_id="org.example.echo",
            contract_version="1.0",
            capability_ids=["org.example.echo"],
            control_actions=["Bad Action"],
        )


def test_limits_defaults():
    limits = SessionTargetLimits()
    assert limits.max_sessions == 1
    assert limits.max_buffer_bytes == 65536


def test_limits_reject_idle_above_lifetime():
    with pytest.raises(ValueError):
        SessionTargetLimits(idle_timeout_seconds=1000, max_lifetime_seconds=100)


def test_limits_reject_zero_sessions():
    with pytest.raises(ValueError):
        SessionTargetLimits(max_sessions=0)
