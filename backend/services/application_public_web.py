"""Generic public-web route registry and supervised application dispatcher."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import ApplicationRuntimeSettings
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services.application_extensions import (
    ApplicationGatewayError,
    invoke_application,
    load_application_definition,
)
from three_mm_protocol import (
    ApplicationExtensionV1,
    ApplicationPublicHttpRequestV1,
    ApplicationPublicHttpResponseV1,
    ApplicationPublicHttpRouteV1,
)


_FORWARDED_REQUEST_HEADERS = frozenset(
    {"accept", "accept-language", "if-none-match", "if-modified-since"}
)
_PARAMETER_SEGMENT = re.compile(r"^\{([a-z][a-z0-9_]{0,63})\}$")


class ApplicationPublicWebError(RuntimeError):
    """Fail-closed public-web error with an HTTP status for the future adapter."""

    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PublicRouteBinding:
    module_id: str
    package_id: int
    installation_id: int | None
    route: ApplicationPublicHttpRouteV1


def _template_segments(path: str) -> tuple[str, ...]:
    if path == "/":
        return ()
    return tuple(path.removeprefix("/").split("/"))


def _routes_overlap(left: str, right: str) -> bool:
    left_segments = _template_segments(left)
    right_segments = _template_segments(right)
    if len(left_segments) != len(right_segments):
        return False
    for left_segment, right_segment in zip(left_segments, right_segments):
        left_parameter = _PARAMETER_SEGMENT.fullmatch(left_segment) is not None
        right_parameter = _PARAMETER_SEGMENT.fullmatch(right_segment) is not None
        if not left_parameter and not right_parameter and left_segment != right_segment:
            return False
    return True


def _validate_bindings(bindings: Sequence[PublicRouteBinding]) -> None:
    for index, left in enumerate(bindings):
        for right in bindings[index + 1 :]:
            if _routes_overlap(left.route.path, right.route.path):
                raise ApplicationPublicWebError(
                    "Public HTTP route conflict: "
                    f"{left.module_id}:{left.route.route_id} ({left.route.path}) overlaps "
                    f"{right.module_id}:{right.route.route_id} ({right.route.path})",
                    status_code=409,
                )


def _binding(
    definition: ApplicationExtensionV1,
    package: ModulePackage,
    installation_id: int | None,
) -> list[PublicRouteBinding]:
    return [
        PublicRouteBinding(
            module_id=definition.module_id,
            package_id=package.id,
            installation_id=installation_id,
            route=route,
        )
        for route in definition.public_http_routes
    ]


def _active_bindings(
    db: Session,
    *,
    exclude_module_id: str | None = None,
) -> list[PublicRouteBinding]:
    installations = list(
        db.scalars(
            select(ApplicationExtensionInstallation)
            .where(
                ApplicationExtensionInstallation.enabled.is_(True),
                ApplicationExtensionInstallation.status == "active",
            )
            .order_by(ApplicationExtensionInstallation.module_id)
        )
    )
    bindings: list[PublicRouteBinding] = []
    for installation in installations:
        if installation.module_id == exclude_module_id:
            continue
        package = db.get(ModulePackage, installation.module_package_id)
        if (
            package is None
            or package.module_id != installation.module_id
            or package.version != installation.active_version
        ):
            raise ApplicationPublicWebError(
                "Active application package is unavailable or inconsistent"
            )
        try:
            definition = load_application_definition(package)
        except ApplicationGatewayError as exc:
            raise ApplicationPublicWebError(str(exc)) from exc
        bindings.extend(_binding(definition, package, installation.id))
    return bindings


def build_public_route_registry(db: Session) -> tuple[PublicRouteBinding, ...]:
    """Reconstruct public route ownership from validated active application state."""

    bindings = _active_bindings(db)
    _validate_bindings(bindings)
    return tuple(bindings)


def validate_public_http_candidate(
    db: Session,
    package: ModulePackage,
    definition: ApplicationExtensionV1,
) -> None:
    """Reject an activation whose public routes overlap another active package."""

    if not definition.public_http_routes:
        return
    bindings = _active_bindings(db, exclude_module_id=definition.module_id)
    bindings.extend(_binding(definition, package, None))
    _validate_bindings(bindings)


def _normalized_request_path(path: str) -> str:
    if (
        not path.startswith("/")
        or "?" in path
        or "#" in path
        or "%" in path
        or "\\" in path
        or "\x00" in path
        or "\r" in path
        or "\n" in path
    ):
        raise ApplicationPublicWebError("Public HTTP request path is invalid", status_code=400)
    if path != "/" and (
        path.endswith("/")
        or "//" in path
        or any(segment in {".", ".."} for segment in path.split("/")[1:])
    ):
        raise ApplicationPublicWebError("Public HTTP request path is invalid", status_code=400)
    return path


def _match_template(template: str, path: str) -> dict[str, str] | None:
    template_segments = _template_segments(template)
    path_segments = _template_segments(path)
    if len(template_segments) != len(path_segments):
        return None
    parameters: dict[str, str] = {}
    for expected, actual in zip(template_segments, path_segments):
        parameter = _PARAMETER_SEGMENT.fullmatch(expected)
        if parameter is not None:
            if not actual:
                return None
            parameters[parameter.group(1)] = actual
        elif expected != actual:
            return None
    return parameters


def resolve_public_route(
    db: Session,
    method: str,
    path: str,
) -> tuple[PublicRouteBinding, dict[str, str]]:
    normalized_method = method.upper()
    if normalized_method not in {"GET", "HEAD"}:
        raise ApplicationPublicWebError("Public HTTP method is not allowed", status_code=405)
    normalized_path = _normalized_request_path(path)
    path_match: tuple[PublicRouteBinding, dict[str, str]] | None = None
    for binding in build_public_route_registry(db):
        parameters = _match_template(binding.route.path, normalized_path)
        if parameters is None:
            continue
        path_match = (binding, parameters)
        break
    if path_match is None:
        raise ApplicationPublicWebError("Public HTTP route was not found", status_code=404)
    binding, parameters = path_match
    if normalized_method not in binding.route.methods:
        raise ApplicationPublicWebError("Public HTTP method is not allowed", status_code=405)
    return binding, parameters


def _normalize_query(
    query: Mapping[str, str | Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for name, value in query.items():
        if isinstance(value, str):
            values = (value,)
        else:
            values = tuple(value)
        if not all(isinstance(item, str) for item in values):
            raise ApplicationPublicWebError("Public HTTP query is invalid", status_code=400)
        result[str(name)] = values
    return result


def _forwarded_headers(headers: Mapping[str, str]) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for name, value in headers.items():
        normalized = name.lower()
        if normalized not in _FORWARDED_REQUEST_HEADERS:
            continue
        if normalized in forwarded and forwarded[normalized] != value:
            raise ApplicationPublicWebError(
                "Public HTTP request contains duplicate forwarded headers",
                status_code=400,
            )
        forwarded[normalized] = value
    return forwarded


def dispatch_public_http(
    db: Session,
    settings: ApplicationRuntimeSettings,
    *,
    method: str,
    path: str,
    query: Mapping[str, str | Sequence[str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> ApplicationPublicHttpResponseV1:
    """Resolve and invoke one public route without exposing raw HTTP authority."""

    binding, path_params = resolve_public_route(db, method, path)
    if binding.installation_id is None:
        raise ApplicationPublicWebError("Public HTTP route is not active")
    installation = db.get(ApplicationExtensionInstallation, binding.installation_id)
    package = db.get(ModulePackage, binding.package_id)
    if (
        installation is None
        or package is None
        or not installation.enabled
        or installation.status != "active"
        or installation.module_package_id != package.id
        or installation.module_id != package.module_id
        or installation.active_version != package.version
    ):
        raise ApplicationPublicWebError("Public HTTP application is unavailable")

    try:
        request = ApplicationPublicHttpRequestV1.model_validate(
            {
                "method": method.upper(),
                "path": _normalized_request_path(path),
                "path_params": path_params,
                "query": _normalize_query(query or {}),
                "headers": _forwarded_headers(headers or {}),
            }
        )
    except ValidationError as exc:
        raise ApplicationPublicWebError(
            "Public HTTP request is invalid", status_code=400
        ) from exc

    try:
        result = invoke_application(
            installation,
            package,
            settings,
            binding.route.handler_operation_id,
            request.model_dump(mode="json"),
            {
                "audience": "public",
                "correlation_id": uuid.uuid4().hex,
            },
            required_audience="public",
        )
        response = ApplicationPublicHttpResponseV1.model_validate(result)
    except (ApplicationGatewayError, ValidationError) as exc:
        raise ApplicationPublicWebError(
            "Public HTTP application returned an invalid response"
        ) from exc

    if (
        response.content_type is not None
        and response.content_type not in binding.route.content_types
    ):
        raise ApplicationPublicWebError(
            "Public HTTP application returned an undeclared content type"
        )
    if response.body is not None and len(response.body.encode("utf-8")) > binding.route.max_response_bytes:
        raise ApplicationPublicWebError("Public HTTP application response is too large")
    return response
