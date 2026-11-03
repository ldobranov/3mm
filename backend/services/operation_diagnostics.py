"""Single optional Core allocation, shared by the gateway and diagnostics API."""

from contextlib import contextmanager
from contextvars import ContextVar
import sqlite3

from backend.version import core_version
from three_mm_protocol.diagnostics import DiagnosticSession, DiagnosticSpan
from backend.services.http_failures import note_failure


try:
    _version = core_version()
except (OSError, ValueError):
    _version = "unknown"

core_diagnostics = DiagnosticSession("core", _version)

# Request-local metadata only; never cache policy, a key, a Session or a token.
_authority_trace = ContextVar('authority_diagnostic_trace', default=None)


@contextmanager
def authority_diagnostic_scope(trace_id, *, operation='application.invoke'):
    token = _authority_trace.set((trace_id, operation))
    try:
        yield
    finally:
        _authority_trace.reset(token)


def _authority_reason(error):
    """Classify before public redaction, without SQL/exception message text."""
    from fastapi import HTTPException
    from sqlalchemy.exc import SQLAlchemyError
    from backend.services.application_authority_keys import AuthorityReviewKeyError
    from backend.services.application_authority_management import AuthorityManagementError
    from backend.services.compiled_ui import CompiledUiBuildError
    from backend.services.application_extensions import ApplicationGatewayError
    from three_mm_runtime.application_transport import ApplicationTransportError

    if isinstance(error, ApplicationGatewayError):
        return error.diagnostic_reason  # Already restricted to protocol labels.
    if isinstance(error, ApplicationTransportError):
        return 'response_invalid'
    if isinstance(error, SQLAlchemyError):
        code = getattr(getattr(error, 'orig', None), 'sqlite_errorcode', None)
        if type(code) is int and (code & 0xff) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return 'authority_database_busy'
        return 'authority_database_unavailable'
    if isinstance(error, BlockingIOError):
        return 'review_key_busy'
    if isinstance(error, AuthorityReviewKeyError):
        return 'review_key_unavailable'
    if isinstance(error, AuthorityManagementError):
        return 'ui_code_unavailable' if error.reason in {
            'artifact_changed', 'artifact_unavailable', 'native_review_unavailable',
        } else 'authority_unavailable'
    if isinstance(error, CompiledUiBuildError):
        return 'ui_code_unavailable'
    if isinstance(error, HTTPException):
        return ('authentication_failed' if error.status_code == 401 else
                'operation_denied' if error.status_code == 403 else 'authority_unavailable')
    return 'authority_unavailable'


@contextmanager
def authority_failure_span(stage):
    """Record only failures, before surrounding key/UI adapters redact them.

    The yielded callback ends acquisition measurement BEFORE entering a lease's
    caller body. A later caller failure must not be labelled a key-lock failure.
    Successful low-level reads do not consume the bounded recorder's error budget.
    No recorder activation, I/O, permission decision or error substitution here.
    """
    current = _authority_trace.get()
    closed = False
    def complete():
        nonlocal closed
        closed = True
    span = (DiagnosticSpan(core_diagnostics, current[0], stage, operation=current[1])
            if current is not None else None)
    try:
        yield complete
    except Exception as error:
        if span is not None and not closed:
            try:
                reason = _authority_reason(error)
                note_failure(stage, reason)
                span.end('denied', reason)
            except Exception:
                pass  # Optional diagnostics must not replace the original error.
        raise
