"""Single optional Core allocation, shared by the gateway and diagnostics API."""

from contextlib import contextmanager
from contextvars import ContextVar
import sqlite3

from backend.version import core_version
from packages.protocol.diagnostics import DiagnosticSession, DiagnosticSpan
from backend.system.diagnostics.failures import note_failure


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
    from backend.applications.authority.keys import AuthorityReviewKeyBusy, AuthorityReviewKeyError
    from backend.applications.authority.management import AuthorityManagementError
    from backend.artifacts.compiled_ui import CompiledUiBuildError
    from backend.applications.runtime.gateway import ApplicationGatewayError
    from components.system_runtime.application_transport import ApplicationTransportError
    from packages.protocol.diagnostic_cases import SESSION_REASONS, AUTHORITY_FAILURES

    reason = getattr(error, 'diagnostic_reason', None)
    if type(reason) is str and reason in SESSION_REASONS:
        return reason

    if isinstance(error, ApplicationGatewayError):
        return error.diagnostic_reason  # Already restricted to protocol labels.
    if isinstance(error, ApplicationTransportError):
        return 'response_invalid'
    if isinstance(error, SQLAlchemyError):
        code = getattr(getattr(error, 'orig', None), 'sqlite_errorcode', None)
        if type(code) is int and (code & 0xff) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            return 'authority_database_busy'
        return 'authority_database_unavailable'
    if isinstance(error, (BlockingIOError, AuthorityReviewKeyBusy)):
        return 'review_key_busy'
    if isinstance(error, AuthorityReviewKeyError):
        return 'review_key_unavailable'
    if isinstance(error, AuthorityManagementError):
        if error.reason in AUTHORITY_FAILURES:
            return AUTHORITY_FAILURES[error.reason]
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
def operation_step(stage, *, operation=None):
    """A safe stage over the current request; never consumes or changes errors."""
    from backend.system.diagnostics.failures import current_trace_id
    current = _authority_trace.get()
    trace = current[0] if current else current_trace_id(None)
    if trace is None:
        yield None  # No request context: no allocations on repeated live policy checks.
        return
    operation = operation or (current[1] if current else 'application.invoke')
    span = DiagnosticSpan(core_diagnostics, trace, stage, operation=operation)
    with authority_diagnostic_scope(trace, operation=operation):
        try:
            yield trace
        except Exception as error:
            try:
                reason = ('deadline_exceeded' if isinstance(error, TimeoutError)
                          else _authority_reason(error))
                note_failure(stage, reason)
                span.end('denied', reason)
            except Exception:
                pass
            raise
        else:
            span.end()


def observed_step(stage):
    """Synchronous stage annotation for existing Core boundaries."""
    from functools import wraps
    def decorate(method):
        @wraps(method)
        def invoke(*args, **kwargs):
            with operation_step(stage):
                return method(*args, **kwargs)
        return invoke
    return decorate


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
