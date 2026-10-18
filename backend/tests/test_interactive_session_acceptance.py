"""M21 local acceptance harness tests (WP5)."""

from backend.services.interactive_session_acceptance import (
    AcceptanceReport,
    CounterSessionProvider,
    run_local_session_acceptance,
)


def test_local_acceptance_passes():
    report = run_local_session_acceptance()
    assert isinstance(report, AcceptanceReport)
    assert report.passed, report.failed()


def test_acceptance_covers_expected_criteria():
    report = run_local_session_acceptance()
    ids = {item.criterion_id for item in report.criteria}
    assert ids == {
        "public_sdk_protocol",
        "public_sdk_metadata",
        "second_provider",
        "cross_user_denied",
        "oversized_refused",
        "revocation_terminates",
        "ticket_single_use",
        "discovery_local_and_remote",
        "multiplex_independent",
        "missing_capability_refused",
        "disconnect_no_replay",
    }


def test_counter_provider_is_independent():
    provider = CounterSessionProvider()
    assert provider.provider_id == "org.3mm.counter"
    assert provider.capability_ids == ("org.3mm.counter",)
