import { useI18n } from '@/utils/i18n'

export const deviceCapabilityEnglish = {
  title: 'Device capabilities', open: 'Capabilities', close: 'Close capabilities', refresh: 'Refresh sources',
  help: 'Choose the capabilities this device may provide. Applications require separate approval in Application access.',
  loading: 'Loading device providers…', empty: 'No capability providers have been reported by this device.',
  denied: 'A current administrator login is required.', unavailable: 'Sources could not be loaded. Refresh to try again.',
  conflict: 'The provider changed or its capabilities conflict with another source. Refresh and review the current selection.',
  unconfirmed: 'The change could not be confirmed. Refresh sources before making another change.',
  saved: 'Change confirmed. Review and approve the required resources in Application access.',
  savedStatusMissing: 'Change confirmed, but current availability could not be loaded. Refresh sources.',
  enabled: 'Provider enabled', disabled: 'Provider disabled', enable: 'Enable provider', disable: 'Disable provider',
  save: 'Save selection', saving: 'Saving…', reset: 'Reset selection', selected: 'Selected', notSelected: 'Not selected',
  noOffers: 'This provider currently offers no capabilities.',
  withdrawn: 'Previously selected, no longer offered. Clear this choice before saving a new selection.',
  otherSources: 'Other reported sources', installationManaged: 'Managed by the module or platform installation.',
  providerManaged: 'This provider supports enable/disable only; individual capability selection is unavailable.',
  ready: 'Ready', unknown: 'Readiness unknown', not_configured: 'Not configured',
  device_offline: 'Device offline', health_stale: 'Readiness report expired', health_missing: 'No readiness report',
  provider_changed: 'Waiting for readiness for the current provider', provider_unhealthy: 'Provider unhealthy',
  provider_conflict_or_inactive: 'Provider conflict or inactive source', authority_inactive: 'Device access inactive',
  provider_inactive: 'Provider inactive', inventory_only: 'Inventory only; no provider declaration',
  session_runtime_unavailable: 'Session runtime unavailable', unavailableStatus: 'Unavailable',
} as const

export type DeviceCapabilityLabel = keyof typeof deviceCapabilityEnglish
export function useDeviceCapabilityLabels() {
  const { t } = useI18n()
  return (key: DeviceCapabilityLabel) => t(`deviceCapabilities.${key}`, deviceCapabilityEnglish[key])
}
