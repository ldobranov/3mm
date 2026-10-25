"""Host networking is preserved. It must never simulate a Wi-Fi mutation."""

from three_mm_provisioning.network import NetworkAdapterError


class HostNetworkAdapter:
    def enter_setup_mode(self):
        pass

    def leave_setup_mode(self):
        pass

    def rollback(self):
        pass

    def stage_configuration(self, credentials):
        raise NetworkAdapterError("Managed Wi-Fi is unavailable")

    def activate_staged(self):
        raise NetworkAdapterError("Managed Wi-Fi is unavailable")

    def verify_connectivity(self):
        return False

    def commit(self):
        raise NetworkAdapterError("Managed Wi-Fi is unavailable")
