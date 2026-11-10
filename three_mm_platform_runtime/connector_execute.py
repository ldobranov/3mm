"""One-shot HTTP executor; do not load the Runtime or worker in this child."""
import base64
import json
import sys

MAX_BODY = 4 * 1024 * 1024


def failure(method, category):
    return {"outcome": "ambiguous" if method in {"POST", "PUT", "PATCH", "DELETE"} else "retryable",
        "http_status": None, "error_category": category, "body_base64": "", "headers": {}}


def execute(plan):
    """One HTTP attempt; parent enforces the absolute deadline and never retries."""
    import http.client
    import ssl
    from urllib.parse import urlsplit

    parsed = urlsplit(plan["url"])
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Invalid connector destination")
    options = {"timeout": plan["timeout_seconds"]}
    if parsed.scheme == "https": options["context"] = ssl.create_default_context()
    connection = (http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection)(
        parsed.hostname, parsed.port, **options)
    try:
        connection.request(plan["method"], parsed.path or "/", body=base64.b64decode(plan["body_base64"], validate=True) or None,
            headers=plan["headers"])
        response = connection.getresponse()
        limit = min(plan["max_response_bytes"], MAX_BODY)
        body = response.read(limit + 1)
        if len(body) > limit:
            return {**failure(plan["method"], "response_limit"), "outcome": "failed"}
        status = response.status
        headers = {}
        content_type = response.getheader("Content-Type")
        if content_type is not None: headers["Content-Type"] = content_type[:256]
        return {"outcome": "succeeded" if 200 <= status < 300 else "rejected" if 400 <= status < 500 else "retryable",
            "http_status": status, "error_category": None,
            "body_base64": base64.b64encode(body).decode("ascii"), "headers": headers}
    except (TimeoutError, OSError, ValueError, http.client.HTTPException):
        return failure(plan["method"], "connection_lost")
    finally: connection.close()


def main():
    # Only anonymous pipes carry a selected target credential. Never argv/env/logs.
    try:
        plan = json.loads(sys.stdin.buffer.read(6 * 1024 * 1024 + 1))
        result = execute(plan)
    except Exception:
        return 1
    # Base64 of MAX_BODY plus bounded metadata fits the worker's 6 MiB frame.
    sys.stdout.buffer.write(json.dumps(result, separators=(",", ":"), allow_nan=False).encode() + b"\n")
    return 0
