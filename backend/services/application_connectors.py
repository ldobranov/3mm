"""Destination-restricted HTTP connector broker for supervised applications."""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.module import (
    ApplicationConnectorAttempt,
    ApplicationConnectorBinding,
    ApplicationExtensionInstallation,
    ApplicationSecretReference,
    ModulePackage,
)
from backend.services.application_extensions import (
    ApplicationGatewayError,
    load_application_definition,
)
from backend.services.application_secrets import (
    ApplicationSecretError,
    decrypt_secret_reference,
)


class ApplicationConnectorError(RuntimeError):
    pass


SAFE_REQUEST_HEADERS = {
    "accept",
    "content-type",
    "if-match",
    "if-none-match",
    "if-modified-since",
    "x-correlation-id",
}
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
REQUEST_ID_PATTERN = re.compile(r"^connector_[0-9a-f]{32}$")


def validate_destination_origin(origin: str, allowed_schemes: tuple[str, ...]) -> str:
    parsed = urlsplit(origin.strip())
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ApplicationConnectorError("Connector destination must be an allowed plain origin")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ApplicationConnectorError("Connector destination port is invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ApplicationConnectorError("Connector destination port is invalid")
    host = parsed.hostname.lower()
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{rendered_host}{f':{port}' if port else ''}"


def _connector_definition(
    db: Session,
    installation: ApplicationExtensionInstallation,
    connector_id: str,
):
    package = db.get(ModulePackage, installation.module_package_id)
    if package is None:
        raise ApplicationConnectorError("Active application package is unavailable")
    try:
        definition = load_application_definition(package)
    except ApplicationGatewayError as exc:
        raise ApplicationConnectorError(str(exc)) from exc
    connector = next(
        (item for item in definition.connectors if item.connector_id == connector_id),
        None,
    )
    if connector is None:
        raise ApplicationConnectorError("Application connector is not declared")
    return connector


def bind_application_connector(
    db: Session,
    installation: ApplicationExtensionInstallation,
    connector_id: str,
    destination_origin: str,
    secret_ref: str | None,
) -> ApplicationConnectorBinding:
    connector = _connector_definition(db, installation, connector_id)
    origin = validate_destination_origin(destination_origin, connector.allowed_schemes)
    secret = None
    if connector.authentication != "none":
        secret = db.scalar(
            select(ApplicationSecretReference).where(
                ApplicationSecretReference.application_installation_id == installation.id,
                ApplicationSecretReference.secret_ref == secret_ref,
                ApplicationSecretReference.revoked_at.is_(None),
            )
        )
        if secret is None or secret.credential_kind != connector.authentication:
            raise ApplicationConnectorError("Connector credential is unavailable or incompatible")
    elif secret_ref is not None:
        raise ApplicationConnectorError("Unauthenticated connector cannot use a credential")
    binding = db.scalar(
        select(ApplicationConnectorBinding).where(
            ApplicationConnectorBinding.application_installation_id == installation.id,
            ApplicationConnectorBinding.connector_id == connector_id,
        )
    )
    if binding is None:
        binding = ApplicationConnectorBinding(
            application_installation_id=installation.id,
            connector_id=connector_id,
            destination_origin=origin,
        )
        db.add(binding)
    binding.destination_origin = origin
    binding.secret_reference_id = secret.id if secret is not None else None
    binding.enabled = True
    db.commit()
    db.refresh(binding)
    return binding


def execute_connector_request(
    db: Session,
    installation: ApplicationExtensionInstallation,
    *,
    connector_id: str,
    request_id: str,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    idempotency_key: str | None,
    transport=requests.request,
) -> dict[str, object]:
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ApplicationConnectorError("Connector request identity is invalid")
    existing = db.scalar(
        select(ApplicationConnectorAttempt).where(
            ApplicationConnectorAttempt.request_id == request_id
        )
    )
    if existing is not None:
        if existing.application_installation_id != installation.id:
            raise ApplicationConnectorError("Connector request identity is already in use")
        return {
            "outcome": existing.outcome,
            "http_status": existing.http_status,
            "error_category": existing.error_category,
            "duplicate": True,
            "body_base64": "",
            "headers": {},
        }
    if not installation.enabled or installation.status != "active":
        raise ApplicationConnectorError("Application extension is not active")
    connector = _connector_definition(db, installation, connector_id)
    binding = db.scalar(
        select(ApplicationConnectorBinding).where(
            ApplicationConnectorBinding.application_installation_id == installation.id,
            ApplicationConnectorBinding.connector_id == connector_id,
            ApplicationConnectorBinding.enabled.is_(True),
        )
    )
    if binding is None:
        raise ApplicationConnectorError("Application connector is not configured")
    origin = validate_destination_origin(binding.destination_origin, connector.allowed_schemes)
    normalized_method = method.upper()
    if normalized_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ApplicationConnectorError("Connector method is not allowed")
    is_mutation = normalized_method in MUTATION_METHODS
    if is_mutation and not connector.supports_mutations:
        raise ApplicationConnectorError("Connector does not allow mutations")
    if is_mutation and not idempotency_key:
        raise ApplicationConnectorError("Connector mutations require an idempotency key")
    if (
        len(path) > 2048
        or not path.startswith(connector.path_prefix)
        or "?" in path
        or "#" in path
    ):
        raise ApplicationConnectorError("Connector path is outside its declared prefix")
    if ".." in path.split("/") or not path.startswith("/"):
        raise ApplicationConnectorError("Connector path is unsafe")
    if len(body) > connector.max_request_bytes:
        raise ApplicationConnectorError("Connector request is too large")
    if idempotency_key is not None and len(idempotency_key) > 256:
        raise ApplicationConnectorError("Connector idempotency key is too long")
    if len(headers) > 32:
        raise ApplicationConnectorError("Connector request has too many headers")
    normalized_headers: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() not in SAFE_REQUEST_HEADERS or not isinstance(value, str) or len(value) > 1024:
            raise ApplicationConnectorError("Connector request header is not allowed")
        normalized_headers[key] = value
    auth = None
    if connector.authentication != "none":
        secret = db.get(ApplicationSecretReference, binding.secret_reference_id)
        if secret is None or secret.application_installation_id != installation.id:
            raise ApplicationConnectorError("Connector credential is unavailable")
        try:
            credential = decrypt_secret_reference(secret)
        except ApplicationSecretError as exc:
            raise ApplicationConnectorError(str(exc)) from exc
        if connector.authentication == "basic":
            auth = (credential["username"], credential["password"])
        elif connector.authentication == "bearer":
            normalized_headers["Authorization"] = f"Bearer {credential['token']}"
        else:
            normalized_headers[credential["header"]] = credential["value"]
    if idempotency_key:
        normalized_headers["Idempotency-Key"] = idempotency_key
    attempt = ApplicationConnectorAttempt(
        request_id=request_id,
        application_installation_id=installation.id,
        connector_id=connector_id,
        method=normalized_method,
        path_hash=hashlib.sha256(path.encode("utf-8")).hexdigest(),
        outcome="in_progress",
    )
    db.add(attempt)
    db.commit()
    response_headers: dict[str, str] = {}
    response_body = b""
    try:
        response = transport(
            normalized_method,
            f"{origin}{path}",
            headers=normalized_headers,
            data=body or None,
            auth=auth,
            timeout=connector.timeout_seconds,
            allow_redirects=False,
        )
        response_body = bytes(response.content)
        if len(response_body) > connector.max_response_bytes:
            raise ApplicationConnectorError("Connector response is too large")
        attempt.http_status = int(response.status_code)
        if 200 <= response.status_code < 300:
            attempt.outcome = "succeeded"
        elif 400 <= response.status_code < 500:
            attempt.outcome = "rejected"
        else:
            attempt.outcome = "retryable"
        content_type = response.headers.get("Content-Type")
        if isinstance(content_type, str):
            response_headers["Content-Type"] = content_type[:256]
    except requests.ConnectTimeout:
        attempt.outcome = "retryable"
        attempt.error_category = "connect_timeout"
    except requests.ReadTimeout:
        attempt.outcome = "ambiguous" if is_mutation else "retryable"
        attempt.error_category = "response_timeout"
    except requests.ConnectionError:
        attempt.outcome = "ambiguous" if is_mutation else "retryable"
        attempt.error_category = "connection_lost"
    except ApplicationConnectorError:
        attempt.outcome = "failed"
        attempt.error_category = "response_limit"
    attempt.completed_at = datetime.now(UTC)
    binding.last_outcome = attempt.outcome
    binding.last_http_status = attempt.http_status
    binding.last_checked_at = attempt.completed_at
    binding.last_error_category = attempt.error_category
    db.commit()
    return {
        "outcome": attempt.outcome,
        "http_status": attempt.http_status,
        "error_category": attempt.error_category,
        "duplicate": False,
        "body_base64": base64.b64encode(response_body).decode("ascii"),
        "headers": response_headers,
    }
