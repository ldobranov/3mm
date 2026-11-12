"""Closed diagnostic vocabulary. Descriptions are observations, never authority.

No exception strings, URLs, credentials or application payloads enter this
catalog. Both the admin case exporter and offline tools use these explanations.
"""

CATALOG_VERSION = 1
AUTHORITY_FAILURES = {
    'grant_not_current': 'grant_not_current', 'stale_grant': 'grant_not_current',
    'native_review_required': 'native_review_required', 'ui_review_required': 'native_review_required',
    'stale_native_review': 'native_review_required', 'record_unavailable': 'authority_record_unavailable',
    'actor_unavailable': 'authentication_failed', 'installation_inactive': 'installation_unavailable',
    'policy_unavailable': 'authority_unavailable',
}
SESSION_OPERATIONS = {"session.targets", "session.ticket", "session.stream"}
SESSION_STAGES = {
    "session.targets", "session.ticket", "session.ui", "session.resource",
    "session.runtime", "session.authority", "session.capacity",
    "session.authentication", "session.opening", "session.stream",
    "session.input", "session.control", "session.cleanup",
    "session.opening.authority_initial", "session.opening.authority_recheck",
    "session.opening.total", "session.opening.audit", "session.opening.acceptance",
    "session.opening.process_guard", "session.opening.connect",
    "session.opening.bootstrap", "session.opening.ownership",
    "session.opening.artifact_send", "session.opening.artifact_verify",
    "session.opening.provider_load", "session.opening.provider_open",
    "session.opening.ready",
    "session.authority.queue", "session.authority.lock_queue",
    "session.authority.thread_queue", "session.authority.current",
    "session.runtime.current", "session.input.before", "session.input.provider",
    "session.input.after", "session.input.ack", "session.output.send",
    "session.output.send_queue", "session.control.provider",
}
SESSION_REASONS = {
    "session_authority_unavailable", "session_permission_denied",
    "session_application_inactive", "session_resource_unavailable",
    "session_target_unavailable", "session_request_mismatch",
    "session_runtime_unavailable", "session_request_used", "session_capacity_full",
    "session_binding_busy", "session_ticket_unavailable", "session_origin_denied",
    "session_cleanup_unconfirmed", "session_runtime_failed",
    "session_worker_identity_invalid",
    "review_key_busy", "review_key_unavailable", "authority_database_busy",
    "authority_database_unavailable", "ui_code_unavailable", "grant_not_current",
    "native_review_required", "authority_record_unavailable", "authority_unavailable",
    "authentication_failed", "operation_denied",
}

# Stable codes select fixed guidance; unknown codes do not become free text.
_EXPLANATIONS = {
    "authentication_failed": ("The current login could not be verified.", "check_login"),
    "operation_denied": ("Current access does not permit this operation.", "review_current_access"),
    "authority_unavailable": ("Current authority could not be established.", "inspect_authority_stages"),
    "grant_not_current": ("The approved application grant does not match current code, selection or authority.", "review_current_access"),
    "native_review_required": ("A current review of the exact native/UI code is required.", "review_exact_package"),
    "authority_record_unavailable": ("The protected authority record is absent or cannot be verified.", "inspect_authority_stages"),
    "review_key_busy": ("The authority review key could not be acquired in time.", "inspect_authority_contention"),
    "review_key_unavailable": ("The protected authority review key is unavailable.", "inspect_component_configuration"),
    "authority_database_busy": ("The authority database is busy.", "inspect_authority_contention"),
    "authority_database_unavailable": ("The authority database could not be read.", "inspect_component_configuration"),
    "ui_code_unavailable": ("The exact application UI code could not be verified.", "review_exact_package"),
    "session_authority_unavailable": ("Current session authority could not be established.", "inspect_authority_stages"),
    "session_permission_denied": ("The current user does not have the required session permission.", "review_current_access"),
    "session_application_inactive": ("The application is not currently active.", "inspect_application_status"),
    "session_resource_unavailable": ("The reviewed session resource is missing or unavailable.", "review_selected_resource"),
    "session_target_unavailable": ("The reviewed device capability is not currently available.", "inspect_provider_status"),
    "session_request_mismatch": ("The session request differs from the exact reviewed resource.", "compare_reviewed_request"),
    "session_runtime_unavailable": ("No current executor matches the reviewed session resource.", "inspect_provider_status"),
    "session_request_used": ("This session request identifier has already been used.", "inspect_original_session"),
    "session_capacity_full": ("The bounded session capacity has been reached.", "inspect_original_session"),
    "session_binding_busy": ("This resource already has a reserved or unfinished session.", "inspect_session_recovery"),
    "session_ticket_unavailable": ("The session ticket is expired, consumed or not valid for this route.", "inspect_original_session"),
    "session_origin_denied": ("The WebSocket origin or query is not permitted.", "inspect_allowed_origin"),
    "session_cleanup_unconfirmed": ("Cleanup of an owned session is not confirmed.", "inspect_session_recovery"),
    "session_runtime_failed": ("The session executor failed; no provider text was collected.", "inspect_provider_status"),
    "session_worker_identity_invalid": ("The executor did not provide a valid identity for this exact startup.", "inspect_component_versions"),
    "deadline_exceeded": ("The operation exceeded its deadline.", "inspect_original_outcome"),
    "response_unconfirmed": ("A response was not confirmed; execution may have happened.", "inspect_original_outcome"),
    "transport_unavailable": ("The component transport did not provide a confirmed response.", "inspect_component_configuration"),
    "request_invalid": ("The request did not meet the supported contract.", "compare_reviewed_request"),
    "response_invalid": ("The response did not meet the supported contract.", "inspect_component_versions"),
    "overloaded": ("The component refused work at its bounded capacity.", "inspect_component_load"),
    "unclassified_conflict": ("Core returned a conflict without a classified cause.", "record_next_attempt"),
    "client_refused": ("Core refused the request; no more specific cause was recorded.", "record_next_attempt"),
    "server_error": ("Core returned a server error without a classified cause.", "record_next_attempt"),
}

NEXT_CHECKS = {
    "check_login": "Check the current login without changing application rights.",
    "review_current_access": "Read current application and human permissions; do not grant access automatically.",
    "inspect_authority_stages": "Record the next user-initiated attempt and inspect the first failed authority stage.",
    "inspect_authority_contention": "Inspect the key/database failure stages for the same request identifier.",
    "inspect_component_configuration": "Read component status and configuration presence; do not restart or reset it.",
    "review_exact_package": "Compare the selected package and UI build with the approved package.",
    "inspect_application_status": "Read the application activation and host status.",
    "review_selected_resource": "Read the selected resource and its current review.",
    "inspect_provider_status": "Read provider registration, availability and exact executor version.",
    "compare_reviewed_request": "Compare only contract metadata with the reviewed resource; do not resend the action.",
    "inspect_original_session": "Read the original session status; do not reconnect or replay automatically.",
    "inspect_session_recovery": "Read session recovery status; cleanup requires a separate explicit action.",
    "inspect_allowed_origin": "Compare the page origin with the configured exact allowed origins.",
    "inspect_original_outcome": "Read the original outcome; an error is not permission to repeat an effect.",
    "inspect_component_versions": "Compare current component versions and supported contracts.",
    "inspect_component_load": "Read component load and capacity observations.",
    "record_next_attempt": "Start a bounded recording, then let the user perform one new attempt.",
}


def explain_failure(reason):
    summary, next_check = _EXPLANATIONS.get(reason, (
        "A failure was observed, but this catalog has no specific explanation.",
        "record_next_attempt",
    ))
    return {"summary": summary, "next_check": next_check,
            "next_check_help": NEXT_CHECKS[next_check]}


def operation_for_route(route):
    """Only a router-owned template is passed here, never a requested URL."""
    if type(route) is not str:
        return None
    if route.endswith("/session-host/{entrypoint_id}/ticket"):
        return "session.ticket"
    if route.endswith("/session-host/{entrypoint_id}/ws"):
        return "session.stream"
    if route.endswith("/session-host/{entrypoint_id}"):
        return "session.targets"
    return None
