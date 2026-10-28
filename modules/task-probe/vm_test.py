"""Owner-VM SDK exercise; run as root to select the installed app principal.

The actual client runs as 3mm-app using the pinned independent host's SDK, not
Core imports or credentials. Persist the request before its one submit attempt.
"""
import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
import uuid


ROOT = Path("/var/lib/3mm/application-extensions")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookup", action="store_true", help="Read the last request without submitting")
    parser.add_argument("--cancel", action="store_true", help="Cancel the last request if still queued")
    parser.add_argument("--upper", type=int, default=100)
    parser.add_argument("--delay", type=int, default=5)
    timing=parser.add_mutually_exclusive_group()
    timing.add_argument("--interval",type=int,help="UTC interval in seconds, minimum 5")
    timing.add_argument("--calendar",action="store_true",help="One local calendar occurrence at the next minute")
    parser.add_argument("--timezone",default="Europe/Sofia")
    parser.add_argument("--runs",type=int,default=3)
    parser.add_argument("--instance", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.lookup and args.cancel:
        parser.error("Choose lookup or cancel")
    if not 0 <= args.upper <= 1000000 or not 0 <= args.delay <= 3600:
        parser.error("upper must be 0..1000000 and delay 0..3600")
    if os.geteuid() == 0:
        matches = []
        for path in ROOT.glob("*/active.json"):
            metadata = json.loads(path.read_text())
            if metadata.get("module_id") == "org.3mm.task-probe":
                matches.append(metadata["instance_id"])
        if len(matches) != 1:
            parser.error("Install and approve Result task probe first")
        instance = matches[0]
        host = Path("/opt/3mm-application-hosts/instances") / instance / "current"
        forwarded = [v for v in sys.argv[1:]]
        if args.instance:
            parser.error("The root launcher selects the installed instance")
        return subprocess.call(["runuser", "-u", "3mm-app", "--", str(host / ".venv/bin/python"),
            "-I", str(Path(__file__).resolve()), *forwarded, "--instance", instance])
    if os.geteuid() != pwd.getpwnam("3mm-app").pw_uid or not args.instance:
        parser.error("Use the root launcher; the SDK client must be the application principal")
    import re
    if re.fullmatch(r"[0-9a-f]{24}", args.instance) is None:
        parser.error("Invalid instance")
    host = Path("/opt/3mm-application-hosts/instances") / args.instance / "current"
    sys.path[:0] = [str(host / "vendor"), str(host / "host.pyz")]
    from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
    metadata = json.loads((ROOT / args.instance / "active.json").read_text())
    assert metadata["module_id"] == "org.3mm.task-probe" and metadata["instance_id"] == args.instance
    secret = (Path("/etc/3mm/application-extensions") / (args.instance + ".key")).read_bytes()
    client = ApplicationPlatformClient(Path(metadata["platform_socket"]), args.instance, secret)
    state = ROOT / args.instance / "data" / "sdk-test-request.json"
    if args.interval or args.calendar or state.is_file() and json.loads(state.read_text()).get("kind")=="schedule":
        import importlib.util
        spec=importlib.util.spec_from_file_location("schedule_test",Path(__file__).with_name("schedule_test.py"))
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        outcome=helper.run(args,client,state,parser)
        if outcome is not None:return outcome
    if args.lookup or args.cancel:
        if not state.is_file():
            parser.error("No saved test request")
        saved = json.loads(state.read_text())
    else:
        if state.is_file():
            previous = json.loads(state.read_text())
            observed = client.lookup_task("calculate", request_id=previous["request_id"])
            if observed["status"] in {"queued", "running", "unknown"}:
                parser.error("Previous request is unresolved; use --lookup or --cancel")
        due = datetime.now(UTC) + timedelta(seconds=args.delay)
        saved = {"request_id": uuid.uuid4().hex, "upper": args.upper,
            "due_at": due.isoformat(), "not_after": (due + timedelta(seconds=10)).isoformat()}
        with state.open("w") as stream:
            json.dump(saved, stream); stream.flush(); os.fsync(stream.fileno())
        directory = os.open(state.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        print("Request:", saved["request_id"], flush=True)
        try:
            observed = client.submit_task("calculate", request_id=saved["request_id"],
                payload={"upper": saved["upper"], "pause_ms": 800},
                due_at=datetime.fromisoformat(saved["due_at"]), not_after=datetime.fromisoformat(saved["not_after"]))
        except ApplicationPlatformError:
            print("Submit reply unavailable. Request saved; use --lookup. Do not resubmit.", flush=True)
            return 2
        print("Admitted:", observed["status"], flush=True)
    last = None
    limit = time.monotonic() + (1 if args.lookup or args.cancel else args.delay + 15)
    while True:
        observed = (client.cancel_task if args.cancel else client.lookup_task)("calculate", request_id=saved["request_id"])
        marker = (observed["status"], observed["progress"])
        if marker != last:
            print(json.dumps(observed, ensure_ascii=False), flush=True); last = marker
        if observed["status"] not in {"queued", "running"} or args.lookup or args.cancel:
            break
        if time.monotonic() >= limit:
            print("Still pending. Use --lookup to read the same request.", flush=True)
            return 2
        time.sleep(.15)
    if observed["status"] == "succeeded":
        expected = saved["upper"] * (saved["upper"] + 1) // 2
        assert observed["result"] == {"total": expected}, "Unexpected calculation result"
        print("PASS: total =", expected, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
