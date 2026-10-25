"""Explicit local role initialization without changing host networking.

Only an absent first-boot journal may be initialized. Interrupted provisioning,
explicit recovery and existing roles are never silently reset.
"""

import argparse
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import socket
import sqlite3

from three_mm_protocol import AgentRole
from three_mm_provisioning.persistence import (
    FileProvisioningStore,
    ProvisioningSnapshot,
)
from three_mm_provisioning.models import ProvisioningState
from three_mm_provisioning.network_recovery import FileNetworkRecoveryPolicyStore
from three_mm_runtime.install_profile import (
    InstallProfile, NetworkBackend, read_network_backend, validate_profile_role,
)


def prepare(
    profile: InstallProfile,
    *,
    data_dir: Path = Path("/var/lib/3mm/provisioning"),
    database: Path = Path("/var/lib/3mm/core/3mm.db"),
    policy_path: Path | None = None,
    network_root: Path = Path("/sys/class/net"),
    check_only: bool = False,
    role: AgentRole | None = None,
    hub_endpoint: str | None = None,
    network_backend: NetworkBackend = NetworkBackend.HOST,
) -> None:
    network_backend = NetworkBackend(network_backend)
    role = AgentRole(role) if role is not None else None
    store = FileProvisioningStore(data_dir)
    snapshot = store.load()
    validate_profile_role(profile, snapshot.role if snapshot else None)
    validate_profile_role(profile, role)
    if snapshot is not None and snapshot.role is not None and role is not None and role is not snapshot.role:
        raise RuntimeError("An existing device role cannot be replaced by installation bootstrap")
    from three_mm_provisioning import FileNetworkRecoveryMarker

    recovery = FileNetworkRecoveryMarker(data_dir / "network-recovery.json").is_active()
    provisioned = (
        snapshot is not None and snapshot.state is ProvisioningState.PROVISIONED
    )
    if provisioned or recovery:
        return  # Never rewrite role, Hub, identity, policy or recovery on upgrade.
    if snapshot is not None:
        if role is not None:
            raise RuntimeError("Interrupted setup must be recovered before initializing a role")
        return
    if role is None:
        return  # Local status/console setup; hardware never selects a role.
    if role is AgentRole.NODE:
        from agent.hub_connection import normalize_hub_endpoint
        try:
            hub_endpoint = normalize_hub_endpoint(hub_endpoint or "")
        except ValueError:
            raise RuntimeError("Node initialization requires a plain HTTP(S) Hub endpoint") from None
    elif hub_endpoint is not None:
        raise RuntimeError("A Hub endpoint applies only to the Node role")
    administrator = None
    if role in {AgentRole.HUB, AgentRole.STANDALONE} and database.is_file():
        with closing(sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro", uri=True
        )) as connection:
            administrator = connection.execute(
                "SELECT username FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
            ).fetchone()
        if administrator is None:
            raise RuntimeError(
                "A Core administrator is required before initializing a wired-only installation"
            )
    if role in {AgentRole.HUB, AgentRole.STANDALONE} and administrator is None:
        raise RuntimeError(
            "Core must have a migrated database and administrator before role initialization"
        )
    if check_only:
        return
    policy = FileNetworkRecoveryPolicyStore(
        policy_path
        or (
            data_dir / "network-recovery-policy.json"
            if profile is InstallProfile.NODE
            else database.parent / "network-recovery-policy.json"
        )
    )
    # Host-managed link state is not inferred from NetworkManager. Preserve any
    # existing administrator policy; this command never changes a connection.
    if not policy.path.exists():
        policy.save(replace(policy.load(), automatic_setup_enabled=False))
    store.save(
        ProvisioningSnapshot(
            state=ProvisioningState.PROVISIONED,
            role=role,
            locale="en-US",
            device_name=socket.gethostname(),
            administrator_name=(administrator[0] or "Administrator") if administrator else "Node operator",
            hub_endpoint=hub_endpoint,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", choices=[p.value for p in InstallProfile], required=True
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--role", choices=[role.value for role in AgentRole])
    parser.add_argument("--hub-endpoint")
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/3mm/provisioning"))
    parser.add_argument("--database", type=Path, default=Path("/var/lib/3mm/core/3mm.db"))
    arguments = parser.parse_args()
    prepare(InstallProfile(arguments.profile), check_only=arguments.check_only,
            role=AgentRole(arguments.role) if arguments.role else None,
            hub_endpoint=arguments.hub_endpoint, data_dir=arguments.data_dir,
            database=arguments.database, network_backend=read_network_backend())
