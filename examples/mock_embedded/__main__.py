"""Run from the repository root: python -m examples.mock_embedded --help."""

import argparse
from pathlib import Path
import time

import requests

from examples.mock_embedded.client import MockEmbeddedClient, ProtocolRejected
from examples.mock_embedded.contracts import control_contract


def main():
    parser = argparse.ArgumentParser(
        description="Mock-only embedded protocol client; no hardware access"
    )
    parser.add_argument(
        "--core-url",
        required=True,
        help="Explicit Core API origin, e.g. http://localhost:8887",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Private directory; use a different one for each node",
    )
    parser.add_argument("--name", default="Mock embedded")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--versioned-contracts", action="store_true",
                        help="Opt into the strict v1 capability contract; requires updated Core")
    parser.add_argument("--explicit-capabilities", action="store_true",
                        help="Use provider v2 and health; Core administrator must configure capabilities")
    args = parser.parse_args()
    if not 1 <= args.interval <= 60:
        parser.error("interval must be 1-60 seconds")
    node = MockEmbeddedClient(args.core_url, args.data_dir, display_name=args.name,
                              contract=control_contract() if args.versioned_contracts else None,
                              explicit_capabilities=args.explicit_capabilities)
    try:
        while True:
            try:
                status = node.tick()
                print(
                    f"{node.device_id}: {status}; pending={node.pending_count}",
                    flush=True,
                )
                if status in {"revoked", "rejected", "expired"}:
                    return 1
            except requests.RequestException:
                print("Core unavailable; durable node data retained", flush=True)
            except (ProtocolRejected, ValueError) as exc:
                # No credentials, response bodies or stored state in diagnostic output.
                print(f"Stopped safely: {type(exc).__name__}", flush=True)
                return 1
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        node.close()


if __name__ == "__main__":
    raise SystemExit(main())
