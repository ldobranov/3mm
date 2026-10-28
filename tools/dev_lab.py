"""Snapshot the working source and run bounded checks in an unprivileged Linux lab.

Pack on the development host; run in WSL/Linux. No installer, systemctl, live
configuration, network mutation, Git checkout or publication is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile
import time


SOURCE_ROOTS = frozenset({
    "backend", "agent", "setup_service", "three_mm_protocol",
    "three_mm_provisioning", "three_mm_runtime", "three_mm_web",
    "three_mm_public_web", "three_mm_application_sdk", "deployment",
    "examples", "modules", "config_templates", "tools",
    "three_mm_platform_wire", "three_mm_platform_runtime",
})
ROOT_FILES = frozenset({"alembic.ini", "frontend/compiler/compile-ui-extension.mjs", "VERSION", "pytest.ini", "pyproject.toml", "install.sh",
                        "deploy.ps1", ".github/workflows/release.yml"})
EXCLUDED_PARTS = frozenset({
    ".git", ".runtime", ".venv", "node_modules", "__pycache__", "data",
    ".pytest_cache", ".mypy_cache", "uploads",
})
EXCLUDED_SUFFIXES = frozenset({".env", ".key", ".pem", ".pfx", ".db", ".sqlite", ".sqlite3", ".log", ".pyc"})
MANIFEST = ".dev-lab-manifest.json"
MAX_SOURCE_BYTES = 128 * 1024 * 1024
PROFILES = {
    "p5-process": ("backend/tests/test_diagnostic_process.py",),
    "p5-packaging": ("backend/tests/test_release_builder.py", "deployment/tests/test_node_release.py", "deployment/tests/test_application_host_component.py::test_native_artifact_is_reproducible_minimal_and_core_free", "deployment/tests/test_service_component.py::test_native_service_is_reproducible_and_contains_no_core", "setup_service/tests/test_api.py::test_diagnostics_are_opt_in_bounded_metadata", "backend/tests/test_language_extensions.py"),
    "p5-core": ("three_mm_protocol/tests/test_diagnostics.py", "three_mm_protocol/tests/test_diagnostic_snapshot.py", "three_mm_application_sdk/tests/test_platform_diagnostics.py", "backend/tests/test_diagnostics.py", "backend/tests/test_diagnostic_workspace.py", "tools/tests/test_extension_dev.py"),
    "p5-boundaries": ("backend/tests/test_platform_transport_contract.py", "backend/tests/test_application_invocation_process.py", "backend/tests/test_application_ui_authority.py", "backend/tests/test_core_startup.py", "backend/tests/test_release_builder.py", "deployment/tests/test_node_release.py"),
    "p4-end-recovery-controls": ("deployment/tests/test_service_component.py::test_component_recovery_resets_only_its_systemd_failure_counter", "deployment/tests/test_service_component.py::test_core_is_favored_over_optional_workers_under_global_oom", "three_mm_runtime/tests/test_systemd_templates.py", "deployment/tests/test_session_worker_deployment.py"),
    "p4-end-transactions": ("deployment/tests/test_service_component.py::test_component_update_does_not_enable_a_service_stopped_during_staging", "deployment/tests/test_service_component.py::test_component_release_lock_conflicts_with_installer_and_rejects_symlinks", "deployment/tests/test_platform_runtime_component.py"),
    "p4-end-probes": ("deployment/tests/test_service_component.py::test_component_probe_trickle_cannot_hold_update_or_prevent_rollback", "deployment/tests/test_service_component.py::test_service_contract_versions_reject_boolean_and_float_aliases"),
    "p4-end-service-final": ("deployment/tests/test_service_component.py::test_independent_component_update_rollback_and_bad_candidate_preserve_core[agent]", "deployment/tests/test_service_component.py::test_independent_component_update_rollback_and_bad_candidate_preserve_core[public-web]"),
    "p4-end-role": ("agent/tests/test_role.py",),
    "p4-end-contract": ("deployment/tests/test_service_component.py::test_service_contract_versions_reject_boolean_and_float_aliases", "deployment/tests/test_service_component.py::test_foreign_contract_target_digest_and_modified_payload_cannot_stage"),
    "p4-end-boundaries": ("backend/tests/test_core_startup.py", "backend/tests/test_application_health_process.py", "backend/tests/test_application_response_process.py", "backend/tests/test_runtime_transport.py", "backend/tests/test_platform_runtime_process.py", "backend/tests/test_application_public_web_transport.py", "backend/tests/test_event_runtime_process.py", "backend/tests/test_connector_runtime_process.py"),
    "p4-end-env": ("deployment/tests/test_node_installer.py::test_agent_environment_filters_core_secrets_and_keeps_host_settings",),
    "p4-end-http-final": ("backend/tests/test_application_access.py", "backend/tests/test_application_ui_host.py", "backend/tests/test_application_ui_authority.py", "backend/tests/test_application_reference_scoped.py"),
    "p4-end-human-final": ("backend/tests/test_application_invocation_process.py::test_admin_operator_and_kiosk_contexts_use_original_signed_replies", "backend/tests/test_application_invocation_process.py::test_waiting_operator_result_is_not_disclosed_after_revocation"),
    "p4-end-agent-final": ("deployment/tests/test_service_component.py::test_independent_component_update_rollback_and_bad_candidate_preserve_core[agent]",),
    "p4-end-components": ("deployment/tests/test_service_component.py", "deployment/tests/test_platform_runtime_component.py", "deployment/tests/test_application_host_component.py"),
    "p4-end-packaging": ("backend/tests/test_release_builder.py", "deployment/tests/test_node_release.py", "deployment/tests/test_node_installer.py", "deployment/tests/test_session_worker_deployment.py", "three_mm_runtime/tests/test_systemd_templates.py", "tools/tests/test_dev_lab.py"),
    "p4-end-agent": ("agent/tests", "three_mm_public_web/tests", "three_mm_runtime/tests/test_session_worker.py"),
    "p4-end-peers": ("backend/tests/test_installation_peers.py", "backend/tests/test_installation_peer_approval_binding.py", "backend/tests/test_application_peer_binding_denial.py", "backend/tests/test_installation_peer_read_sources.py", "three_mm_runtime/tests/test_application_relational_session.py"),
    "p4-end-metadata": ("three_mm_runtime/tests/test_application_relational_session.py", "backend/tests/test_application_relational_runtime.py"),
    "p4-end-http": ("backend/tests/test_application_access.py", "backend/tests/test_application_ui_host.py", "backend/tests/test_application_ui_authority.py", "backend/tests/test_application_reference_scoped.py", "backend/tests/test_application_health_probe.py", "backend/tests/test_application_response_relay.py", "backend/tests/test_application_extensions.py"),
    "p4-end-process": ("backend/tests/test_application_invocation_process.py",),
    "p4d5-packaging": ("backend/tests/test_release_builder.py", "deployment/tests/test_node_release.py"),
    "p4d5-process": ("backend/tests/test_application_health_process.py",),
    "p4d5-core": ("backend/tests/test_application_health_probe.py", "backend/tests/test_application_extensions.py", "backend/tests/test_application_ui_authority.py", "backend/tests/test_application_authority_writers.py"),
    "p4d5-boundaries": ("backend/tests/test_application_response_relay.py", "backend/tests/test_application_response_process.py", "backend/tests/test_application_lifecycle_authority.py", "backend/tests/test_application_lifecycle_recovery.py", "backend/tests/test_application_operations.py", "backend/tests/test_core_startup.py", "backend/tests/test_release_builder.py", "deployment/tests/test_node_release.py", "tools/tests/test_dev_lab.py"),
    "p4d4-auth": ("backend/tests/test_application_response_process.py::test_non_admin_status_is_denied_before_reservation_or_app_io",),
    "p4d4-last": (
        "backend/tests/test_application_response_relay.py",
        "backend/tests/test_application_response_process.py::test_full_response_pool_rejects_before_dispatch_and_leaves_core_threads_free",
        "backend/tests/test_application_response_process.py::test_absent_runtime_returns_core_metadata_without_opening_application_socket"),
    "p4d4-core": ("backend/tests/test_application_response_relay.py", "backend/tests/test_application_operations.py", "backend/tests/test_application_authority_writers.py"),
    "p4d4-process": ("backend/tests/test_application_response_process.py",),
    "p4d4-boundaries": (
        "backend/tests/test_application_operations.py", "backend/tests/test_core_startup.py",
        "backend/tests/test_runtime_transport.py", "backend/tests/test_platform_runtime_process.py",
        "backend/tests/test_application_public_web_transport.py", "backend/tests/test_event_runtime_process.py",
        "backend/tests/test_connector_runtime_process.py", "deployment/tests/test_platform_runtime_component.py",
        "backend/tests/test_release_builder.py", "three_mm_runtime/tests/test_systemd_templates.py",
        "deployment/tests/test_node_installer.py", "deployment/tests/test_node_release.py", "tools/tests/test_dev_lab.py"),

    "p4d3-core": ("backend/tests/test_application_connector_transport.py", "backend/tests/test_application_connectors.py", "backend/tests/test_application_authority_management.py",
        "backend/tests/test_application_authority_writers.py", "backend/tests/test_migration_history.py"),
    "p4d3-boundaries": (
        "backend/tests/test_core_startup.py", "backend/tests/test_runtime_transport.py",
        "backend/tests/test_platform_runtime_process.py", "backend/tests/test_event_runtime_process.py",
        "backend/tests/test_application_public_web_transport.py", "backend/tests/test_application_platform.py",
        "deployment/tests/test_platform_runtime_component.py", "backend/tests/test_release_builder.py",
        "three_mm_runtime/tests/test_systemd_templates.py", "three_mm_runtime/tests/test_activate.py",
        "deployment/tests/test_node_installer.py", "deployment/tests/test_node_release.py", "tools/tests/test_dev_lab.py"),
    "p4d3-admin": ("backend/tests/test_connector_runtime_process.py::test_saturated_network_worker_leaves_short_core_admission_and_admin_available",),
    "p4d3-last": (
        "backend/tests/test_application_connector_transport.py::test_expired_duplicate_is_reconciled_even_behind_full_unexpired_status_batch",
        "backend/tests/test_application_connector_transport.py::test_network_executor_rejects_an_untrusted_tls_certificate_before_http",
        "backend/tests/test_connector_runtime_process.py::test_network_deadline_limit_and_redirect_never_replay[trickle-ambiguous]"),
    "p4d3-focus": (
        "backend/tests/test_runtime_transport.py::test_runtime_refuses_old_abi2_core_without_connector_feature",
        "backend/tests/test_connector_runtime_process.py::test_saturated_network_worker_leaves_short_core_admission_and_admin_available",
        "backend/tests/test_connector_runtime_process.py::test_dns_hang_is_killed_outside_core_at_absolute_deadline",
        "backend/tests/test_connector_runtime_process.py::test_bad_worker_candidate_rolls_back_only_network_process",
        "backend/tests/test_application_connector_transport.py",
        "three_mm_protocol/tests/test_application_extension.py"),
    "p4d3-process": ("backend/tests/test_connector_runtime_process.py",),

    "p4d2-process": ("backend/tests/test_event_runtime_process.py",),
    "p4d2-core": (
        "backend/tests/test_application_events.py",
        "backend/tests/test_application_event_authority.py",
        "backend/tests/test_application_event_routes.py",
        "backend/tests/test_application_event_publication.py",
        "backend/tests/test_migration_history.py",
    ),
    "p4d2-boundaries": (
        "backend/tests/test_core_startup.py",
        "backend/tests/test_runtime_transport.py",
        "backend/tests/test_platform_runtime_process.py",
        "backend/tests/test_application_public_web_transport.py",
        "deployment/tests/test_platform_runtime_component.py",
        "backend/tests/test_release_builder.py",
        "three_mm_runtime/tests/test_systemd_templates.py",
        "deployment/tests/test_node_installer.py",
        "deployment/tests/test_node_release.py",
        "tools/tests/test_dev_lab.py",
    ),
    "p4d-consumers": (
        "backend/tests/test_application_extensions.py",
        "backend/tests/test_application_access.py",
        "backend/tests/test_application_jobs.py",
        "backend/tests/test_application_peer_binding_denial.py",
        "backend/tests/test_installation_peer_read_sources.py",
        "backend/tests/test_installation_peer_approval_binding.py",
        "backend/tests/test_installation_peers.py",
        "backend/tests/test_application_relational_runtime.py",
        "backend/tests/test_wp4_relational_test_extension.py",
        "backend/tests/test_application_lifecycle_authority.py",
        "backend/tests/test_application_reference.py",
        "backend/tests/test_application_reference_scoped.py",
        "backend/tests/test_application_ui_authority.py",
        "backend/tests/test_routes.py",
        "deployment/tests/test_application_host_component.py",
    ),
    "p4d": (
        "backend/tests/test_application_public_web_transport.py",
        "backend/tests/test_application_public_web.py",
        "backend/tests/test_application_scoped_runtime_gates.py",
        "backend/tests/test_application_events.py",
        "backend/tests/test_application_event_authority.py",
        "three_mm_public_web/tests",
        "backend/tests/test_local_listener_lifecycle.py",
        "backend/tests/test_core_startup.py",
        "backend/tests/test_runtime_transport.py",
        "backend/tests/test_platform_runtime_process.py",
        "deployment/tests/test_platform_runtime_component.py",
        "three_mm_runtime/tests/test_systemd_templates.py",
        "backend/tests/test_release_builder.py",
        "backend/tests/test_first_boot_preflight.py",
        "deployment/tests/test_node_installer.py",
        "deployment/tests/test_node_release.py",
        "tools/tests/test_dev_lab.py",
    ),
    "p4c": (
        "deployment/tests/test_application_host_component.py",
        "three_mm_runtime/tests/test_application_host.py",
        "three_mm_runtime/tests/test_application_activation.py",
        "three_mm_runtime/tests/test_application_file_host.py",
        "three_mm_runtime/tests/test_application_lifecycle.py",
        "three_mm_runtime/tests/test_application_relational_session.py",
        "three_mm_runtime/tests/test_systemd_templates.py",
        "three_mm_runtime/tests/test_services.py",
        "backend/tests/test_release_builder.py",
        "deployment/tests/test_node_installer.py",
        "deployment/tests/test_node_release.py",
        "tools/tests/test_dev_lab.py",
    ),
    "p4b": (
        "backend/tests/test_runtime_transport.py",
        "backend/tests/test_platform_runtime_process.py::test_real_checkpoint_mutation_replay_and_revocation_share_the_only_runtime_path",
        "three_mm_runtime/tests/test_application_activation.py",
        "three_mm_runtime/tests/test_application_host.py",
        "three_mm_runtime/tests/test_application_transport.py",
        "three_mm_runtime/tests/test_application_lifecycle.py",
        "three_mm_runtime/tests/test_application_relational_session.py",
    ),
    "p4": (
        "deployment/tests/test_platform_runtime_component.py",
        "backend/tests/test_platform_runtime_process.py::test_independent_update_rollback_kill_and_hang_preserve_real_core",
        "backend/tests/test_platform_runtime_process.py::test_revoke_recovery_and_authority_loss_cannot_fall_back_or_cache_rights",
        "backend/tests/test_platform_runtime_process.py::test_runtime_identity_never_uses_compatibility_identity_initialization",
        "backend/tests/test_core_startup.py",
        "three_mm_runtime/tests/test_activate.py",
        "three_mm_runtime/tests/test_services.py",
        "three_mm_runtime/tests/test_systemd_templates.py",
        "three_mm_runtime/tests/test_application_file_host.py",
        "backend/tests/test_release_builder.py",
        "deployment/tests/test_node_installer.py",
        "deployment/tests/test_node_release.py",
        "three_mm_protocol/tests/test_platform_transport.py",
        "tools/tests/test_dev_lab.py",
    ),
    "p3": (
        "backend/tests/test_language_extensions.py",
        "backend/tests/test_module_packages.py",
        "backend/tests/test_crud_extraction.py",
        "backend/tests/test_compiled_ui.py",
        "backend/tests/test_ai_extension_generator.py",
        "backend/tests/test_extension_intent_planner.py",
        "backend/tests/test_ai_extension_widget_spec.py",
        "backend/tests/test_extension_projects.py",
        "backend/tests/test_theme_extension_lifecycle.py",
        "backend/tests/test_theme_extension_packages.py",
        "backend/tests/test_theme_extension_selection.py",
        "backend/tests/test_theme_extension_preview.py",
        "backend/tests/test_theme_extension_v2.py",
        "backend/tests/test_module_inspection.py",
        "backend/tests/test_migration_history.py",
        "backend/tests/test_dashboard_grant_access.py",
        "backend/tests/test_core_startup.py",
        "backend/tests/test_routes.py",
        "backend/tests/test_interactive_session_release_gate.py",
        "backend/tests/test_local_listener_lifecycle.py",
        "backend/tests/test_diagnostics.py",
        "backend/tests/test_application_platform.py",
        "backend/tests/test_application_platform_authority.py",
        "backend/tests/test_application_identity_read.py",
        "backend/tests/test_application_public_web_transport.py",
        "backend/tests/test_application_commands.py",
        "backend/tests/test_application_command_recovery.py",
        "backend/tests/test_application_checkpoints.py",
        "backend/tests/test_application_checkpoint_authority.py",
        "backend/tests/test_application_event_publication.py",
        "backend/tests/test_application_file_execution.py",
        "backend/tests/test_application_peer_read.py",
        "backend/tests/test_application_peer_read_authority.py",
        "backend/tests/test_application_scoped_platform_refusals.py",
        "backend/tests/test_application_status_read.py",
        "backend/tests/test_installation_identity_platform.py",
        "backend/tests/test_application_jobs.py",
        "backend/tests/test_platform_transport_contract.py",
        "backend/tests/test_application_scoped_runtime_gates.py",
        "backend/tests/test_application_access.py",
        "backend/tests/test_application_reference.py",
        "backend/tests/test_application_reference_scoped.py",
        "backend/tests/test_application_lifecycle_recovery.py",
        "backend/tests/test_application_lifecycle_authority.py",
        "three_mm_protocol/tests/test_platform_transport.py",
        "three_mm_application_sdk/tests",
        "three_mm_runtime/tests/test_application_dispatch.py",
        "backend/tests/test_update_policy.py",
    ),
    "p2": (
        "three_mm_runtime/tests/test_services.py",
        "three_mm_runtime/tests/test_activate.py",
        "three_mm_runtime/tests/test_install_profile.py",
        "three_mm_runtime/tests/test_install_bootstrap.py",
        "three_mm_runtime/tests/test_node_recovery.py",
        "three_mm_runtime/tests/test_network_recovery.py",
        "three_mm_runtime/tests/test_systemd_templates.py",
        "three_mm_runtime/tests/test_update_helper.py",
        "setup_service/tests",
        "three_mm_provisioning/tests",
        "three_mm_protocol/tests/test_diagnostics.py",
        "three_mm_application_sdk/tests/test_platform_diagnostics.py",
        "backend/tests/test_first_boot_preflight.py",
        "backend/tests/test_network_recovery_routes.py",
        "backend/tests/test_initial_setup.py",
        "backend/tests/test_release_builder.py",
        "deployment/tests/test_node_preflight.py",
        "deployment/tests/test_node_installer.py",
        "deployment/tests/test_node_release.py",
        "agent/tests/test_hub_connection.py",
    ),
    "sdk": ("three_mm_application_sdk/tests",),
    "p1": (
        "three_mm_protocol/tests/test_diagnostics.py",
        "three_mm_application_sdk/tests/test_identity_and_compatibility.py",
        "three_mm_application_sdk/tests/test_platform_diagnostics.py",
        "backend/tests/test_application_identity_read.py",
        "backend/tests/test_application_platform_authority.py",
        "backend/tests/test_diagnostics.py",
    ),
    "smoke": (
        "backend/tests/test_application_identity_read.py::test_real_signed_sdk_read_has_no_private_key_dependency_or_implicit_retry",
        "three_mm_runtime/tests/test_services.py",
        "backend/tests/test_diagnostics.py",
    ),
    "p0": (
        "backend/tests/test_application_identity_read.py",
        "backend/tests/test_application_platform_authority.py",
        "backend/tests/test_diagnostics.py",
        "setup_service/tests/test_api.py",
        "three_mm_runtime/tests/test_services.py",
        "three_mm_runtime/tests/test_install_bootstrap.py",
    ),
}


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def source_path(name: str) -> bool:
    path = PurePosixPath(name)
    parts = path.parts
    if (not parts or path.is_absolute() or ".." in parts or "\\" in name
            or ":" in name or name != path.as_posix()):
        return False
    if name not in ROOT_FILES and parts[0] not in SOURCE_ROOTS:
        return False
    return not (
        set(parts) & EXCLUDED_PARTS
        or any(part.lower().startswith(".env") for part in parts)
        or path.suffix.lower() in EXCLUDED_SUFFIXES
    )


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo)


def pack(repo: Path) -> Path:
    repo = repo.resolve()
    names = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    files = {}
    total = 0
    for raw in sorted(set(names.split(b"\0")) - {b""}):
        name = os.fsdecode(raw)
        if not source_path(name):
            continue
        path = repo / name
        if not path.exists() and not path.is_symlink():
            continue  # A tracked deletion must not reappear from HEAD.
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repo):
            raise ValueError(f"Source must be a regular in-repository file: {name}")
        blob = path.read_bytes()
        total += len(blob)
        if total > MAX_SOURCE_BYTES:
            raise ValueError("Source snapshot exceeds the lab size budget")
        files[name] = blob
    hashes = {name: digest(blob) for name, blob in files.items()}
    identity = digest(json.dumps(hashes, sort_keys=True).encode())
    manifest = {
        "schema_version": 1,
        "head": git(repo, "rev-parse", "HEAD").decode().strip(),
        "source_sha256": identity,
        "files": hashes,
    }
    target = repo / ".runtime" / "dev-lab"
    target.mkdir(parents=True, exist_ok=True)
    archive = target / f"source-{identity}.tar"
    with tempfile.NamedTemporaryFile(dir=target, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        with tarfile.open(fileobj=stream, mode="w") as bundle:
            contents = {**files, MANIFEST: json.dumps(manifest, sort_keys=True).encode()}
            for name, blob in contents.items():
                info = tarfile.TarInfo(name)
                info.size = len(blob)
                info.mode = 0o644
                bundle.addfile(info, io.BytesIO(blob))
    temporary.replace(archive)
    print(json.dumps({"archive": str(archive), "head": manifest["head"],
                      "source_sha256": identity, "files": len(files), "bytes": total}))
    return archive


def unpack(archive: Path, destination: Path) -> dict:
    """Verify every member before writing into a newly created directory."""
    with tarfile.open(archive, "r:") as bundle:
        members = bundle.getmembers()
        names = [member.name for member in members]
        if len(names) > 10_000 or len(names) != len(set(names)):
            raise ValueError("Duplicate or excessive snapshot members")
        if sum(member.size for member in members) > MAX_SOURCE_BYTES + 2 * 1024 * 1024:
            raise ValueError("Snapshot exceeds the lab size budget")
        for member in members:
            if not member.isfile() or (member.name != MANIFEST and not source_path(member.name)):
                raise ValueError("Snapshot contains an unsafe or non-source member")
        manifest = json.load(bundle.extractfile(MANIFEST))
        hashes = manifest["files"]
        if manifest.get("schema_version") != 1 or set(names) != set(hashes) | {MANIFEST}:
            raise ValueError("Snapshot manifest/member mismatch")
        if digest(json.dumps(hashes, sort_keys=True).encode()) != manifest["source_sha256"]:
            raise ValueError("Snapshot identity mismatch")
        contents = {}
        for name, expected in hashes.items():
            blob = bundle.extractfile(name).read()
            if digest(blob) != expected:
                raise ValueError(f"Snapshot file digest mismatch: {name}")
            contents[name] = blob
    destination.mkdir()  # Existing directories are never merged or overwritten.
    for name, blob in contents.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return manifest


def lab_environment(run: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL") if key in os.environ}
    (run / "tmp").mkdir(exist_ok=True)
    (run / "state").mkdir(exist_ok=True)
    env.update({
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "TMPDIR": str(run / "tmp"), "XDG_DATA_HOME": str(run / "state"),
        "THREE_MM_TEST_DATABASE_PATH": str(run / "state" / "test.db"),
        "DATABASE_URL": f"sqlite:///{run / 'state' / 'test.db'}",
        "THREE_MM_PLATFORM_RUNTIME_SOCKET": str(run / "runtime.sock"),
        "THREE_MM_CORE_AUTHORITY_SOCKET": str(run / "authority.sock"),
        "THREE_MM_PUBLIC_WEB_GATEWAY_SOCKET": str(run / "public.sock"),
    })
    return env


def environment(source: Path, run: Path, env: dict, fresh: bool) -> tuple[Path, bool, str]:
    requirements = b"".join((source / "backend" / name).read_bytes()
                            for name in ("requirements.txt", "requirements-dev.txt"))
    key = digest(requirements + sys.version.encode() + platform.machine().encode())
    cache = Path.home() / ".cache" / "3mm-dev-lab" / "envs"
    cache.mkdir(parents=True, exist_ok=True)
    location = cache / key
    if fresh:
        location = Path(tempfile.mkdtemp(prefix=key[:12] + "-", dir=cache))
    ready = location / "ready.json"
    python = location / "bin" / "python"
    reused = ready.is_file()
    if reused:
        expected = json.loads(ready.read_text())
        frozen = subprocess.check_output([str(python), "-m", "pip", "freeze", "--all"], env=env)
        if expected != {"key": key, "freeze_sha256": digest(frozen)}:
            raise ValueError("Lab environment changed; repeat with --fresh-env")
    else:
        if location.exists() and not fresh:
            raise ValueError("Incomplete lab environment; repeat with --fresh-env")
        if not fresh:
            location.mkdir()  # Claim the cache slot before a second runner can.
        with (run / "prepare.log").open("w") as log:
            subprocess.run([sys.executable, "-m", "venv", str(location)],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            subprocess.run([str(python), "-m", "pip", "install", "-r",
                            str(source / "backend" / "requirements-dev.txt")],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
            subprocess.run([str(python), "-m", "pip", "check"], env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        frozen = subprocess.check_output([str(python), "-m", "pip", "freeze", "--all"], env=env)
        ready.write_text(json.dumps({"key": key, "freeze_sha256": digest(frozen)}))
    return python, reused, digest(frozen)


def run_lab(archive: Path, profile: str, fresh: bool = False) -> int:
    if sys.platform != "linux" or os.geteuid() == 0:
        raise ValueError("Run the lab as an unprivileged Linux user")
    started = time.monotonic()
    run = Path(tempfile.mkdtemp(prefix="3mm-lab-", dir="/tmp"))
    print(f"Lab: {run}", flush=True)
    source = run / "src"
    manifest = unpack(archive, source)
    env = lab_environment(run)
    env["PYTHONPATH"] = str(source)
    print("Preparing/verifying the isolated dependency environment...", flush=True)
    python, reused, freeze = environment(source, run, env, fresh)
    preparation = time.monotonic() - started
    command = [str(python), "-m", "pytest", "-q", "--tb=short", "--disable-warnings",
               "-p", "pytest_asyncio.plugin", *PROFILES[profile],
               "--basetemp", str(run / "tests"), "--junitxml", str(run / "results.xml")]
    test_start = time.monotonic()
    with (run / "tests.log").open("w") as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=300)
    evidence = {
        "profile": profile, "head": manifest["head"],
        "source_sha256": manifest["source_sha256"], "python": str(python),
        "python_version": sys.version, "dependencies_sha256": freeze,
        "environment_reused": reused, "prepare_seconds": round(preparation, 2),
        "test_seconds": round(time.monotonic() - test_start, 2),
        "command": command, "exit_code": result.returncode,
    }
    (run / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print("\n".join((run / "tests.log").read_text().splitlines()[-22:]))
    print(json.dumps(evidence, indent=2))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pack")
    run = commands.add_parser("run")
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--profile", choices=PROFILES, default="p0")
    run.add_argument("--fresh-env", action="store_true")
    args = parser.parse_args()
    if args.command == "pack":
        pack(Path(__file__).resolve().parents[1])
        return 0
    return run_lab(args.archive, args.profile, args.fresh_env)


if __name__ == "__main__":
    raise SystemExit(main())
