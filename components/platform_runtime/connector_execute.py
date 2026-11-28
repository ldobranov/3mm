"""One-shot HTTP executor; do not load the Runtime or worker in this child."""
import base64
import json
import sys

MAX_BODY = 4 * 1024 * 1024
MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}


def failure(method, category):
    return {"outcome": "ambiguous" if method in MUTATIONS else "retryable",
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
    status = None
    try:
        connection.request(plan["method"], parsed.path or "/", body=base64.b64decode(plan["body_base64"], validate=True) or None,
            headers=plan["headers"])
        response = connection.getresponse()
        status = response.status
        limit = min(plan["max_response_bytes"], MAX_BODY)
        # HTTPResponse accounts for HEAD, 204 and chunked framing here; a
        # Content-Length header alone does not promise a body in those cases.
        expected = response.length
        body = response.read(limit + 1)
        if len(body) > limit:
            # The bound is local; it cannot undo a change at the destination.
            return {**failure(plan["method"], "response_limit"), "http_status": status,
                    "outcome": "ambiguous" if plan["method"] in MUTATIONS else "failed"}
        if expected is not None and len(body) < expected:
            # read(n) can return a short, even valid-looking JSON prefix at EOF.
            # A status line isn't proof that the promised result was received.
            return {**failure(plan["method"], "connection_lost"), "http_status": status}
        headers = {}
        content_type = response.getheader("Content-Type")
        if content_type is not None: headers["Content-Type"] = content_type[:256]
        if 200 <= status < 300:
            outcome = "succeeded"
        elif 400 <= status < 500:
            outcome = "rejected"
        else:
            # A redirect or server error can arrive after the mutation happened.
            outcome = "ambiguous" if plan["method"] in MUTATIONS else "retryable"
        return {"outcome": outcome,
            "http_status": status, "error_category": None,
            "body_base64": base64.b64encode(body).decode("ascii"), "headers": headers}
    except (TimeoutError, OSError, ValueError, http.client.HTTPException):
        return {**failure(plan["method"], "connection_lost"), "http_status": status}
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
