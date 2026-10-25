"""Single optional Core allocation, shared by the gateway and diagnostics API."""

from backend.version import core_version
from three_mm_protocol.diagnostics import DiagnosticSession


try:
    _version = core_version()
except (OSError, ValueError):
    _version = "unknown"

core_diagnostics = DiagnosticSession("core", _version)
