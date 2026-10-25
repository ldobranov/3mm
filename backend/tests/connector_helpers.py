"""Fake I/O driver for current-admission tests; production Core has no HTTP client."""
import base64
import requests
from backend.db.module import ApplicationConnectorAttempt
from backend.services.application_connectors import prepare_connector_request, record_connector_outcome
from backend.services.application_connector_transport import failure


def execute_connector_request(db, installation, *, transport, **arguments):
    plan = prepare_connector_request(db, installation, **arguments)
    if "attempt_id" not in plan: return plan
    attempt = db.get(ApplicationConnectorAttempt, plan["attempt_id"])
    try:
        response = transport(plan["method"], plan["url"], headers=plan["headers"],
            data=base64.b64decode(plan["body_base64"]) or None, timeout=plan["timeout_seconds"], allow_redirects=False)
        status = response.status_code
        result = {"outcome": "succeeded" if 200 <= status < 300 else "rejected" if 400 <= status < 500 else "retryable",
            "http_status": status, "error_category": None, "body_base64": base64.b64encode(response.content).decode(),
            "headers": {"Content-Type": response.headers["Content-Type"][:256]} if "Content-Type" in response.headers else {}}
    except requests.RequestException:
        result = failure(plan["method"], "response_timeout")
    return record_connector_outcome(db, attempt, result)
