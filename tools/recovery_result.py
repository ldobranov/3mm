"""Portable verifier evidence format and fixed operator guidance. No archive access."""
from deployment.build_release import SUPPORTED_ARCHITECTURES


SCOPE = "offline_archive_validation_only"
GUIDANCE = {
    "linux_required": "Use a Linux checkout of the intended Core release.",
    "target_not_supported": "Select a supported target architecture explicitly.",
    "input_unavailable": "Select a regular portable recovery file within the supported size limit.",
    "scratch_unavailable": "Choose a writable Linux filesystem for the private temporary directory.",
    "insufficient_scratch_space": "Choose a temporary filesystem with more free space.",
    "password_or_envelope_invalid": "Recheck the password and the original exported file; no restore was attempted.",
    "target_incompatible": "Check the selected architecture, Core version, protocol and supported database migration path.",
    "restore_application_package_invalid": "An active application has no verified matching package in the archive.",
    "restore_application_schema_invalid": "An active application database did not pass the integrity or schema check.",
    "restore_application_profile_unavailable": "The archive requests a separately prepared application that ordinary Standalone restore cannot activate.",
    "installation_identity_invalid": "The archived installation identity could not be verified with its captured configuration.",
    "restore_core_database_invalid": "The Core database failed its read-only integrity check. Keep the original and verify another export.",
    "restore_core_revision_invalid": "Core could not verify exactly one database revision matching the archive. Verify another export; do not edit the database.",
    "restore_device_state_invalid": "The archived Agent identity or setup state could not be read. Use a complete Standalone export.",
    "restore_device_identity_mismatch": "The archived Agent identity differs from the archive record. Use an intact export from the intended device.",
    "restore_role_invalid": "This recovery path requires an archive from a configured Standalone device.",
    "restore_payload_checksum_failed": "Authenticated file contents do not match the archive inventory. Keep the original and verify another export.",
    "payload_invalid": "The staged inventory, checksum, identity, role or database did not pass restore validation.",
    "storage_error": "Temporary storage could not be read, written or cleaned up. Check the chosen workspace.",
    "password_prompt_unavailable": "Run from an interactive Linux terminal; do not put recovery passwords on the command line.",
}
MAX_INNER_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 32_768


def result(arch, *, issue=None, **counts):
    value = dict(schema_version=1,kind="portable_recovery_check",scope=SCOPE,
        target_architecture=arch if arch in SUPPORTED_ARCHITECTURES else None,
        state="not_verified" if issue else "validated", service_activation_tested=False)
    if issue:
        value.update(reason=issue,next_check=GUIDANCE[issue])
    else:
        value.update(counts)
    return value


def checked_result(value):
    if (type(value) is not dict or type(value.get("schema_version")) is not int or value["schema_version"]!=1 or
            value.get("kind")!="portable_recovery_check" or value.get("scope")!=SCOPE or
            value.get("service_activation_tested") is not False):
        raise ValueError("Invalid archive check")
    arch = value.get("target_architecture")
    if arch is not None and arch not in SUPPORTED_ARCHITECTURES:
        raise ValueError("Invalid target")
    if value.get("state")=="not_verified":
        reason = value.get("reason")
        if type(reason) is not str or reason not in GUIDANCE or (
                arch is None and reason not in ("linux_required","target_not_supported")):
            raise ValueError("Unknown check result")
        # Never copy externally supplied instructions, even when the code is known.
        return result(arch,issue=reason)
    n,size = value.get("entry_count"),value.get("payload_size_bytes")
    if (arch is None or value.get("state")!="validated" or type(n) is not int or not 1<=n<=MAX_ENTRIES or
            type(size) is not int or not 0<size<=MAX_INNER_BYTES):
        raise ValueError("Invalid archive check counts")
    return result(arch,entry_count=n,payload_size_bytes=size)
