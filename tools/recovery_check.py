"""Verify a portable Standalone recovery file offline. Never import, activate or restore it."""
import argparse
import getpass
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import warnings

from backend.installation.identity import InstallationIdentityError
from backend.system.backups.application_packages import ApplicationRecoveryError
from deployment.backup_compatibility import BackupCompatibilityError
from deployment.portable_backup import open_portable_source, stage_portable_envelopes
from deployment.restore_backup import RestoreStateError, _stage_for_target
from tools.recovery_result import GUIDANCE, MAX_ENTRIES, MAX_INNER_BYTES, SCOPE, SUPPORTED_ARCHITECTURES, result as _result


SPACE_RESERVE = 64 * 1024 * 1024


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


def verify_portable(path: Path, passphrase: str, *, target_architecture: str, scratch: Path | None = None):
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
                result = _result(arch,entry_count=len(manifest.entries),payload_size_bytes=manifest.total_size_bytes)
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
            result = verify_portable(args.file,password,target_architecture=args.target_architecture,scratch=args.scratch)
            del password
    if args.json:
        print(json.dumps(result,ensure_ascii=True))
    elif result["state"]=="validated":
        print(f"Archive validated for {result['target_architecture']}: {result['entry_count']} entries. "
              "No device, activation, restore or boot was tested.")
    else:
        print(f"Not verified ({result['reason']}). {result['next_check']}")
    return 0 if result["state"]=="validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
