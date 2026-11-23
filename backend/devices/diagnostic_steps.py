"""Observe trusted device boundaries without changing their results or deadlines."""
import sqlite3
import time
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError

from backend.installation.identity import InstallationIdentityError
from backend.system.diagnostics.failures import database_reason, finish_device_step
from packages.protocol.transport import DeviceProtocolError


def _reason(exc, stage):
    # Only explicit wrapped causes and typed codes. Never serialize messages,
    # statements, parameters, credential IDs or exception objects.
    from backend.applications.authority.management import AuthorityAdmissionUnavailable
    cause, unready = exc, False
    for _ in range(5):
        if isinstance(cause, AuthorityAdmissionUnavailable):
            return 'review_key_busy' if cause.reason == 'key_busy' else 'database_busy'
        if isinstance(cause, DBAPIError):
            return database_reason(cause.orig)
        if isinstance(cause, sqlite3.Error):
            return database_reason(cause)
        if isinstance(cause, InstallationIdentityError):
            unready = True
        if isinstance(cause, DeviceProtocolError):
            if cause.kind == 'unauthorized':
                return 'device_credential_refused'
            if cause.kind == 'forbidden':
                return 'device_access_denied'
        cause = cause.__cause__
        if cause is None:
            break
    if unready:
        return 'installation_identity_unavailable'
    if isinstance(exc, HTTPException) and stage == 'device.identity_match' and exc.status_code == 403:
        return 'device_identity_mismatch'
    if isinstance(exc, HTTPException) and stage == 'device.credential_header' and exc.status_code == 401:
        return 'device_credential_refused'
    return 'device_step_unknown'


@contextmanager
def device_step(stage):
    started = time.monotonic()
    try:
        yield
    except Exception as exc:
        finish_device_step(stage, started, _reason(exc, stage))
        raise
    else:
        finish_device_step(stage, started)
