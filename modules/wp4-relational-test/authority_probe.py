"""Explicit fixture-only admin API actions, never native trust or auto-apply.

beta.48's UI does not understand relational scopes. This uses the existing
authenticated API, with separate manual review/approve/apply/revoke commands.
"""

import argparse
import getpass
import json
import re
import sys
from urllib.error import HTTPError, URLError

from probe import APP, call

SCOPES = ["storage:relational_read", "storage:relational_write"]


def hex_value(value, size):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{" + str(size) + "}", value) is not None
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["review", "approve", "apply", "revoke"])
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--native-review-id")
    parser.add_argument("--expected-sha", help="Exact ZIP SHA-256, required for review")
    parser.add_argument("--plan-id")
    parser.add_argument("--expected-revision")
    parser.add_argument("--fingerprint")
    parser.add_argument("--confirm-reviewed-rights", action="store_true")
    args = parser.parse_args()
    if not hex_value(args.request_id, 32):
        parser.error(
            "Persist an explicit 32-hex request ID before each administrative action"
        )
    if args.action == "review" and not (
        hex_value(args.native_review_id, 32) and hex_value(args.expected_sha, 64)
    ):
        parser.error("review requires exact --native-review-id and --expected-sha")
    if args.action in {"approve", "apply"} and not (
        hex_value(args.plan_id, 32)
        and hex_value(args.expected_revision, 32)
        and hex_value(args.fingerprint, 64)
        and args.confirm_reviewed_rights
    ):
        parser.error(
            "approve/apply require exact plan/revision/fingerprint and explicit --confirm-reviewed-rights"
        )
    if args.action == "revoke" and not (
        hex_value(args.expected_revision, 32) and args.confirm_reviewed_rights
    ):
        parser.error(
            "revoke requires current grant record revision and --confirm-reviewed-rights"
        )
    try:
        email = input("Core administrator email (not the Linux user): ").strip()
        password = getpass.getpass("Core password: ")
        token = call("/api/user/login", {"email": email, "password": password})["token"]
        password = ""
        payload = {"request_id": args.request_id}
        if args.action == "review":
            status = call(APP + "/authority", token=token)
            if not (
                status["artifact_sha256"] == args.expected_sha
                and status.get("review_available") is True
                and sorted(status["scopes"]) == SCOPES
                and any(
                    item["native_review_id"] == args.native_review_id
                    for item in status["native_reviews"]
                )
            ):
                raise ValueError("Current exact reviewed fixture/resources unavailable")
            payload.update(native_review_id=args.native_review_id, scopes=SCOPES)
            path = "/authority/reviews"
        elif args.action == "revoke":
            path = "/authority/revoke"
            payload["expected_revision"] = args.expected_revision
        else:
            path = f"/authority/reviews/{args.plan_id}/{args.action}"
            payload.update(
                expected_revision=args.expected_revision, fingerprint=args.fingerprint
            )
        result = call(APP + path, payload, token)
        # One action only; returned revision is for the next HUMAN decision.
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except HTTPError as error:
        print(
            f"Core refused HTTP {error.code}. No retry or follow-up action was sent.",
            file=sys.stderr,
        )
    except (OSError, URLError, ValueError, KeyError, TypeError):
        print(
            "Authority result unavailable. No retry, automatic apply or fallback. Retain IDs/evidence.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
