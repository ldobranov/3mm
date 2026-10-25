"""Setup coordination. Device identity and provisional network ownership are separate."""

from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from three_mm_protocol import AgentRole
from three_mm_protocol.diagnostics import DiagnosticSession, DiagnosticSpan
from three_mm_provisioning.models import NetworkMode, NetworkCredentials, ProvisioningRequest, ProvisioningState
from three_mm_provisioning.persistence import ProvisioningSnapshot
from three_mm_provisioning.setup_access import FileSetupAccessStore
from three_mm_provisioning.setup_journal import SetupJournal, SetupActivationJournal
from three_mm_provisioning.network_helper_client import NetworkHelperClientAdapter


class SetupFailure(ValueError):
    pass


@dataclass
class SetupCoordinator:
    network: object
    store: object
    marker: object
    settings: object
    version: str
    lock: Lock = field(default_factory=Lock)

    def __post_init__(self):
        self.journal = SetupJournal(self.settings.data_dir)
        self.activation = SetupActivationJournal(self.settings.data_dir)
        self.access = FileSetupAccessStore(self.settings.data_dir)
        self.diagnostics = DiagnosticSession("setup", self.version)
        if self.settings.diagnostics:
            self.diagnostics.start()
        self.pending = False
        self.completed_attempt = False
        self.reconciled_recovery = False
        activation = self.activation.load()
        if activation is not None:
            self.completed_attempt = True
            self.reconciled_recovery = bool(activation['previous'] and activation['previous'].get('role'))
        self.trace_id = None
        if not self.settings.read_only:
            with self.journal.locked():
                self.reconcile()
        self.previous = self.store.load()
        if self.pending:
            attempt = self.journal.load()
            self.previous = ProvisioningSnapshot.from_dict(attempt["previous"]) if attempt["previous"] else None
        self.recovery = self.reconciled_recovery or bool(self.previous and self.previous.role and self.marker.is_active())
        self.state = (ProvisioningState.SETUP if not self.completed_attempt and (self.recovery or not self.previous or not self.previous.role)
                      else ProvisioningState.PROVISIONED)

    @property
    def role(self):
        if self.completed_attempt:
            snapshot = self.store.load()
            return snapshot.role if snapshot else None
        return self.previous.role if self.previous else None

    @property
    def access_snapshot(self):
        attempt = self.journal.load()
        if attempt is not None:
            return ProvisioningSnapshot.from_dict(attempt["previous"]) if attempt["previous"] else None
        return self.store.load() if self.completed_attempt else self.previous

    def _restore(self, previous):
        if previous is None:
            self.store.clear()
        else:
            self.store.save(ProvisioningSnapshot.from_dict(previous))

    def reconcile(self):
        attempt = self.journal.load()
        if attempt is None:
            return
        committed = attempt["committed"]
        if attempt["wifi"]:
            try:
                phase = self.network.transaction_phase(attempt["id"])
                if phase in {"applying", "verified"}:
                    phase = self.network.rollback_attempt(attempt["id"])
                if phase not in {"committed", "rolled_back", "missing"}:
                    raise SetupFailure("setup_pending")
                committed = phase == "committed"
            except Exception:
                self.pending = True
                return
        if committed:
            self.journal.commit()  # A recovered Wi-Fi commit is durable before handoff.
            self.marker.clear()
            self.completed_attempt = True
            self.reconciled_recovery = bool(attempt["previous"] and attempt["previous"].get("role"))
        else:
            self._restore(attempt["previous"])
            self.journal.clear()

    def apply(self, configuration, *, interfaces):
        if self.pending:
            raise SetupFailure("setup_pending")
        if self.state is not ProvisioningState.SETUP:
            raise SetupFailure("setup_not_available")
        if self.store.load() != self.previous or self.journal.load() is not None:
            raise SetupFailure("setup_state_changed")
        if self.recovery and not self.marker.is_active():
            raise SetupFailure("setup_not_available")
        if self.recovery:
            for name in ("role", "locale", "device_name", "administrator_name", "hub_endpoint"):
                if getattr(configuration, name) != getattr(self.previous, name):
                    raise SetupFailure("recovery_identity_is_fixed")
            if configuration.administrator_password is not None or configuration.administrator_email is not None:
                raise SetupFailure("recovery_cannot_change_administrator")
        elif configuration.role is not AgentRole.NODE:
            if not configuration.administrator_email or not configuration.administrator_password:
                raise SetupFailure("administrator_credentials_required")
        elif not configuration.hub_endpoint:
            raise SetupFailure("hub_endpoint_required")

        wifi = configuration.network_mode is NetworkMode.WIFI
        if wifi and configuration.network_interface not in {item["name"] for item in interfaces}:
            raise SetupFailure("wifi_adapter_unavailable")
        request = ProvisioningRequest(
            network=NetworkCredentials(configuration.network_name, configuration.passphrase.get_secret_value()) if wifi else None,
            locale=configuration.locale, device_name=configuration.device_name,
            administrator_name=configuration.administrator_name, role=configuration.role,
            hub_endpoint=configuration.hub_endpoint, network_mode=configuration.network_mode,
            network_interface=configuration.network_interface)
        identifier = uuid4().hex
        self.trace_id = "setup_" + identifier
        candidate = ProvisioningSnapshot.provisioned(request)
        with DiagnosticSpan(self.diagnostics, self.trace_id, "setup.attempt"):
            self.journal.begin(identifier, self.previous, wifi=wifi)
            try:
                if wifi:
                    with DiagnosticSpan(self.diagnostics, self.trace_id, "setup.network"):
                        if isinstance(self.network, NetworkHelperClientAdapter):
                            self.network.begin_attempt(identifier, configuration.network_interface)
                        self.state = ProvisioningState.APPLYING_NETWORK
                        self.network.stage_configuration(request.network)
                        self.network.activate_staged()
                        self.state = ProvisioningState.VERIFYING_NETWORK
                        if not self.network.verify_connectivity():
                            raise SetupFailure("network_configuration_failed")
                with DiagnosticSpan(self.diagnostics, self.trace_id, "setup.persist"):
                    if not self.recovery and configuration.role is not AgentRole.NODE:
                        # Lazy import: minimal Node setup has no backend dependency.
                        from backend.services.initial_setup import establish_administrator
                        establish_administrator(self.settings.core_database_path, configuration.administrator_name,
                                                configuration.administrator_email,
                                                configuration.administrator_password.get_secret_value())
                    self.store.save(candidate)
                    if wifi:
                        self.network.commit()
                    self.journal.commit()
            except Exception:
                if wifi:
                    try:
                        # A lost commit reply must not restore old metadata after a
                        # durable network commit. Query the known attempt first.
                        if isinstance(self.network, NetworkHelperClientAdapter):
                            phase = self.network.transaction_phase(identifier)
                            if phase == "committed":
                                self.pending = True
                                raise SetupFailure("setup_pending")
                        self.network.rollback()
                    except Exception:
                        self.pending = True
                        raise SetupFailure("setup_pending") from None
                self._restore(self.previous.to_dict() if self.previous else None)
                self.journal.clear()
                self.state = ProvisioningState.SETUP
                raise
            self.state = ProvisioningState.PROVISIONED
            self.completed_attempt = True
            self.marker.clear()

    def finish(self):
        if self.pending:
            self.pending = False
            self.reconcile()
            if self.pending:
                raise SetupFailure("setup_pending")
            snapshot = self.store.load()
            self.state = ProvisioningState.PROVISIONED if snapshot and snapshot.role else ProvisioningState.SETUP
        if not self.completed_attempt and not (self.recovery and self.marker.is_active()):
            raise SetupFailure("setup_not_available")
        if self.state is not ProvisioningState.PROVISIONED and not self.recovery:
            raise SetupFailure("setup_not_complete")
        # Cancelling recovery preserves all saved settings; the marker is the
        # only thing cleared. Activation never pairs an existing device again.
        self.marker.clear()
        if isinstance(self.network, NetworkHelperClientAdapter):
            self.activation.handoff(self.journal)
            with DiagnosticSpan(self.diagnostics, self.trace_id or "setup_" + uuid4().hex, "setup.activation"):
                self.network.activate_runtime(recovery=self.recovery)
            # The actuator acknowledges this separate handoff after readiness.
            # Existing Agents see the committed role through the normal store.
        else:
            self.journal.clear()
        self.access.revoke()
        self.state = ProvisioningState.PROVISIONED
