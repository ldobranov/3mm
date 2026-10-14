"""Manual local-VM probes. No trust/grants/start/stop/boot changes or retries."""

import argparse
import getpass
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "http://127.0.0.1:8887"
MODULE = "org.3mm.wp4-relational-test"
APP = "/api/v1/application-extensions/" + MODULE
MAX_RESPONSE = 1024 * 1024
MAX_PACKAGE = 10 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def call(path, payload=None, token=None, *, raw=None, content_type="application/json"):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = (
        raw
        if raw is not None
        else json.dumps(payload).encode() if payload is not None else None
    )
    with build_opener(ProxyHandler({}), NoRedirect()).open(
        Request(BASE + path, data=body, headers=headers), timeout=15
    ) as response:
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("Response exceeds the probe bound")
        return json.loads(data)


def preflight():
    if os.name != "posix" or not Path("/run/systemd/system").is_dir():
        raise ValueError("Use the disposable Ubuntu/WSL systemd VM")
    import pwd

    accounts = {}
    for name in ("3mm", "3mm-app"):
        try:
            account = pwd.getpwnam(name)
            accounts[name] = {"uid": account.pw_uid, "gid": account.pw_gid}
        except KeyError:
            accounts[name] = None
    instance = hashlib.sha256(MODULE.encode()).hexdigest()[:24]
    unit = f"3mm-application-extension@{instance}.service"
    services = subprocess.run(
        [
            "/usr/bin/systemctl",
            "is-active",
            "3mm-core",
            "3mm-agent",
            "3mm-web",
            "3mm-update-helper",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    template = subprocess.run(
        [
            "/usr/bin/systemctl",
            "show",
            unit,
            "--no-pager",
            "--property=LoadState,User,Group,ActiveState,UnitFileState,MainPID",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    fields = dict(
        line.split("=", 1) for line in template.stdout.splitlines() if "=" in line
    )
    valid = (
        services.returncode == 0
        and services.stdout.splitlines() == ["active"] * 4
        and all(accounts.values())
        and accounts["3mm"]["uid"] > 0
        and accounts["3mm-app"]["uid"] > 0
        and accounts["3mm"]["uid"] != accounts["3mm-app"]["uid"]
        and accounts["3mm-app"]["gid"] > 0
        and template.returncode == 0
        and fields.get("LoadState") == "loaded"
        and fields.get("User") == "3mm-app"
        and fields.get("Group") == "3mm-app"
        and fields.get("ActiveState") in {"inactive", "failed"}
        and fields.get("MainPID") == "0"
        and fields.get("UnitFileState") == "disabled"
    )
    return {
        "status": "ready_for_catalog_only" if valid else "blocked",
        "version": Path("/opt/3mm/current/VERSION").read_text(encoding="utf-8").strip(),
        "accounts": accounts,
        "services": services.stdout.splitlines(),
        "instance_id": instance,
        "unit": unit,
        "unit_state": fields,
        "authority_checked": False,
        "changes_performed": False,
    }


def upload_body(path, expected_sha):
    with path.open("rb") as source:
        payload = source.read(MAX_PACKAGE + 1)
    if (
        len(payload) > MAX_PACKAGE
        or hashlib.sha256(payload).hexdigest() != expected_sha
    ):
        raise ValueError("Exact ZIP digest/size check failed before login")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in ("manifest.json", "application-extension.json"):
            if archive.getinfo(name).file_size > 131072:
                raise ValueError("Declaration exceeds the probe bound")
        manifest = json.loads(archive.read("manifest.json"))
        definition = json.loads(archive.read("application-extension.json"))
    if not (
        manifest.get("module_id") == MODULE
        and manifest.get("manifest_version") == 2
        and manifest.get("version") == "1.0.0"
        and definition.get("module_id") == MODULE
        and definition.get("service", {}).get("sdk_version") == "1.3"
        and definition.get("storage", {}).get("relational") is not None
        and not definition.get("frontend")
        and not definition.get("routes")
    ):
        raise ValueError("Use only the exact headless relational fixture ZIP")
    boundary = "wp4r-" + uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="package"; '
            'filename="wp4-relational-test-1.0.0.zip"\r\nContent-Type: application/zip\r\n\r\n'
        ).encode()
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, "multipart/form-data; boundary=" + boundary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "preflight",
            "catalog",
            "upload",
            "status",
            "get",
            "put",
            "record",
            "boundary",
        ],
    )
    parser.add_argument(
        "--request-id", help="Persist a new 32-hex ID before each different write"
    )
    parser.add_argument("--text", help="Synthetic text only, at most 256 characters")
    parser.add_argument("--package", type=Path)
    parser.add_argument(
        "--expected-sha", help="Exact ZIP SHA-256 for catalog upload, not a grant"
    )
    parser.add_argument("--confirm-catalog-upload-only", action="store_true")
    args = parser.parse_args()
    if args.action in {"put", "record"} and not re.fullmatch(
        r"[0-9a-f]{32}", args.request_id or ""
    ):
        parser.error("put/record require an explicit persisted --request-id")
    if args.action == "put" and (args.text is None or len(args.text) > 256):
        parser.error("put requires --text of at most 256 characters")
    if args.action == "upload" and not (
        args.package
        and args.confirm_catalog_upload_only
        and re.fullmatch(r"[0-9a-f]{64}", args.expected_sha or "")
    ):
        parser.error(
            "upload requires --package, --expected-sha and --confirm-catalog-upload-only"
        )
    try:
        if args.action == "preflight":
            result = preflight()
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "ready_for_catalog_only" else 1
        body = media = None
        if args.action == "upload":
            body, media = upload_body(args.package, args.expected_sha)
        email = input("Core administrator email (not the Linux user): ").strip()
        password = getpass.getpass("Core password: ")
        login = call("/api/user/login", {"email": email, "password": password})
        password = ""
        token = login["token"]
        if args.action == "catalog":
            packages = call("/api/v1/modules/packages", token=token)
            result = [
                {key: item[key] for key in ("module_id", "version", "sha256")}
                for item in packages
                if item["module_id"] == MODULE
            ]
        elif args.action == "upload":
            item = call(
                "/api/v1/modules/packages", token=token, raw=body, content_type=media
            )
            if item["sha256"] != args.expected_sha or item["module_id"] != MODULE:
                raise ValueError(
                    "Unexpected catalog reply; inspect catalog, do not upload again"
                )
            result = {key: item[key] for key in ("module_id", "version", "sha256")}
            result["installation_or_start_requested"] = False
            result["local_package_id_lookup_required"] = True
        elif args.action == "status":
            result = call(APP + "/authority", token=token)
        else:
            request = {"payload": {}}
            if args.action in {"put", "record"}:
                request["payload"]["request_id"] = args.request_id
            if args.action == "put":
                request["payload"]["text"] = args.text
                request["idempotency_key"] = args.request_id
            operation = {
                "get": "db_get",
                "put": "db_put",
                "record": "db_record",
                "boundary": "db_boundary",
            }[args.action]
            result = call(APP + "/operations/" + operation, request, token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except HTTPError as error:
        print(f"Core refused HTTP {error.code}. No retry was sent.", file=sys.stderr)
    except (
        OSError,
        URLError,
        ValueError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ):
        print(
            "Outcome unavailable. No retry was sent. Preserve IDs/evidence; inspect before another mutation.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
