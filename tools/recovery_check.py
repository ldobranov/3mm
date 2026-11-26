"""Verify a portable Standalone recovery file offline. Never import, activate or restore it."""
import argparse
import getpass
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import stat
import sys
import tarfile
import tempfile
import warnings
from contextlib import closing
from itertools import count

from backend.installation.identity import InstallationIdentityError
from backend.system.backups.application_packages import ApplicationRecoveryError
from deployment.backup_compatibility import BackupCompatibilityError
from deployment.portable_backup import open_portable_source, stage_portable_envelopes
from deployment.restore_backup import RestoreStateError, _stage_for_target
from tools.recovery_result import ACCESS_FOLLOWUP, INTERFACE_FOLLOWUP, GUIDANCE, MAX_ENTRIES, MAX_INNER_BYTES, SCOPE, SUPPORTED_ARCHITECTURES, result as _result


SPACE_RESERVE = 64 * 1024 * 1024


def _application_access_followup(staging):
    """Advisory only, after successful validation. Never open keys or grant tables."""
    database = staging / "payload/core/3mm.db"
    try:
        with closing(sqlite3.connect(database.as_uri()+"?mode=ro", uri=True, timeout=0.2)) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA query_only=ON")
            db.set_progress_handler(lambda steps=count(): next(steps) >= 256, 1000)
            if db.execute("SELECT type FROM sqlite_schema WHERE name='application_extension_installations'").fetchone() != ("table",):
                return "not_checked"
            # No names, IDs, permissions, rows or private configuration are exported.
            # Prefer a positive observation even if older/unknown modes coexist.
            modes = db.execute("""SELECT max(CASE WHEN authority_mode IN ('enforced','review_required') THEN 2
                                               WHEN authority_mode='compatibility' THEN 0 ELSE 1 END)
                                  FROM application_extension_installations WHERE enabled=1 AND status='active'""").fetchone()[0]
            return "fresh_review_needed" if modes == 2 else "not_checked" if modes == 1 else "none_observed"
    except (sqlite3.Error, ValueError, OSError):
        return "not_checked"


def _private_scratch_parent(scratch):
    # A private leaf alone is insufficient in a replaceable shared parent.
    # Permit the customary root-owned sticky /tmp and trusted non-writable
    # ancestors. Resolve symlinks first (e.g. /var -> /private/var).
    parent = Path(scratch if scratch is not None else tempfile.gettempdir()).resolve(strict=True)
    for directory in (parent,*parent.parents):
        info = directory.stat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid()) or
                info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise OSError("Unsafe scratch parent")
    return parent


def verify_portable(path: Path, passphrase: str, *, target_architecture: str, scratch: Path | None = None,
                    check_interfaces: bool = False):
    """No device, catalog, network, local backup key, systemd or live service dependency.

    Only explicit staging uses disk. The source is opened read-only and never
    consumed like an uploaded import. Output is safe to share; no paths,
    manifests, identities, password, hashes or exception strings are returned.
    """
    arch = target_architecture
    if sys.platform != "linux":
        return _result(arch,issue="linux_required")
    if arch not in SUPPORTED_ARCHITECTURES:
        return _result(arch,issue="target_not_supported")
    phase = "input_unavailable"
    try:
        with open_portable_source(path, MAX_INNER_BYTES) as (source,size):
            phase = "scratch_unavailable"
            with tempfile.TemporaryDirectory(prefix="recovery-check-",dir=_private_scratch_parent(scratch)) as folder:
                work = Path(folder)
                info = work.stat()
                if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
                    return _result(arch,issue=phase)
                # Both envelopes are uncompressed. Allow for unpacked staging,
                # a private SQLite+WAL copy and filesystem overhead too.
                if shutil.disk_usage(work).free < 5 * size + SPACE_RESERVE:
                    return _result(arch,issue="insufficient_scratch_space")
                phase = "password_or_envelope_invalid"
                backup_id, plaintext = stage_portable_envelopes(source,size,passphrase,work,max_archive_bytes=MAX_INNER_BYTES)
                phase = "payload_invalid"
                staging = work/"staging"
                staging.mkdir(mode=0o700)
                manifest = _stage_for_target(plaintext, staging, backup_id, arch,
                    entry_budget=MAX_ENTRIES, payload_budget=min(MAX_INNER_BYTES,size))
                result = _result(arch,entry_count=len(manifest.entries),payload_size_bytes=manifest.total_size_bytes,
                                 application_access_followup=_application_access_followup(staging))
                if check_interfaces:
                    from tools.recovery_interfaces import observe
                    result["interface_builds"] = observe(staging,manifest.entries)
                phase = "storage_error"
        return result
    except (ApplicationRecoveryError, RestoreStateError) as exc:
        return _result(arch,issue=exc.restore_code if exc.restore_code in GUIDANCE else "payload_invalid")
    except BackupCompatibilityError:
        return _result(arch,issue="target_incompatible")
    except InstallationIdentityError:
        return _result(arch,issue="installation_identity_invalid")
    except OSError:
        return _result(arch,issue=phase if phase in ("input_unavailable","scratch_unavailable") else "storage_error")
    except (ValueError,tarfile.TarError,EOFError,OverflowError):
        return _result(arch,issue=phase)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file",type=Path)
    parser.add_argument("--target-architecture",choices=SUPPORTED_ARCHITECTURES,default=platform.machine(),
                        help="intended restore machine (default: current machine); the verifier never contacts it")
    parser.add_argument("--scratch",type=Path,help="existing trusted Linux filesystem for private transient plaintext")
    parser.add_argument("--json",action="store_true",help="print bounded metadata and fixed reason codes only")
    parser.add_argument("--check-interfaces",action="store_true",
                        help="also check existing compiled interface inventories; never compiles or approves code")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or args.target_architecture not in SUPPORTED_ARCHITECTURES:
        result = _result(args.target_architecture,issue="linux_required" if sys.platform!="linux" else "target_not_supported")
    else:
        try:
            # Do not let getpass fall back to echoing input from the console or a pipe.
            with warnings.catch_warnings():
                warnings.simplefilter("error",getpass.GetPassWarning)
                password = getpass.getpass("Recovery password (not saved): ")
        except (getpass.GetPassWarning,EOFError,KeyboardInterrupt,OSError):
            result = _result(args.target_architecture,issue="password_prompt_unavailable")
        else:
            result = verify_portable(args.file,password,target_architecture=args.target_architecture,scratch=args.scratch,
                                     check_interfaces=args.check_interfaces)
            del password
    if args.json:
        print(json.dumps(result,ensure_ascii=True))
    elif result["state"]=="validated":
        print(f"Archive validated for {result['target_architecture']}: {result['entry_count']} entries. "
              "No device, activation, restore or boot was tested.")
        print(ACCESS_FOLLOWUP[result["application_access_followup"]])
        if "interface_builds" in result: print(INTERFACE_FOLLOWUP[result["interface_builds"]])
    else:
        print(f"Not verified ({result['reason']}). {result['next_check']}")
    return 0 if result["state"]=="validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
