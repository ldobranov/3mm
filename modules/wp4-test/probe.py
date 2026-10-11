"""Explicit manual tests against local Core; no install, approval or retries."""
import argparse
import getpass
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:8887"
APP = "/api/v1/application-extensions/org.3mm.wp4-test"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward a password or bearer credential elsewhere.


def call(path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    with build_opener(ProxyHandler({}), NoRedirect()).open(Request(BASE + path, data=body, headers=headers), timeout=15) as response:
        return json.loads(response.read(131072))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["echo", "status", "get", "put", "receipt"])
    parser.add_argument("--request-id", help="Persist this 32-hex ID before a write; reuse for receipt checks")
    parser.add_argument("--expected-sha", help="Exact current digest; omission means create only if absent")
    parser.add_argument("--text", default="WP4 test", help="Synthetic test text only")
    args = parser.parse_args()
    if args.action in {"put", "receipt"} and not re.fullmatch(r"[0-9a-f]{32}", args.request_id or ""):
        parser.error("put/receipt require an explicit --request-id of 32 lowercase hex characters")
    if args.expected_sha is not None and not re.fullmatch(r"[0-9a-f]{64}", args.expected_sha):
        parser.error("--expected-sha must be a 64-character lowercase hex digest")
    if len(args.text) > 256:
        parser.error("Test text must be at most 256 characters")
    # Credentials are prompted, never command-line arguments, files or output.
    email = input("Core administrator email (not the Linux user): ").strip()
    password = getpass.getpass("Core password: ")
    try:
        login = call("/api/user/login", {"email": email, "password": password})
        token = login["token"]
        password = ""
        if args.action == "status":
            result = call(APP + "/authority", token=token)
        else:
            operation = {"echo": "echo", "get": "file_get", "put": "file_put", "receipt": "file_receipt"}[args.action]
            payload = {"message": "WP4 test"} if args.action == "echo" else {}
            if args.action in {"put", "receipt"}:
                payload["request_id"] = args.request_id
            if args.action == "put":
                payload.update(text=args.text, expected_sha256=args.expected_sha)
            request = {"payload": payload}
            if args.action == "put":
                request["idempotency_key"] = args.request_id
            result = call(APP + "/operations/" + operation, request, token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HTTPError as error:
        print(f"Core refused the request: HTTP {error.code}. No retry was sent.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ValueError, KeyError):
        print("Outcome unavailable. No retry was sent. For a write, inspect the SAME request ID before doing anything else.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
