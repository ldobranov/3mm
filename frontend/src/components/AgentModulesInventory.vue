<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { UiButton, UiDialog } from '@/extension-ui/v1'
import http from '@/utils/dynamic-http'
import axios from 'axios'
import { newHardwareRequestId } from '@/utils/hardware-interfaces'
import { useI18n } from '@/utils/i18n'

interface Installation {
  device_id: string
  display_name: string
  status: string
  enabled: boolean
  command_id: string | null
  error: string | null
  uninstall_supported: boolean
  installed_version: string | null
  desired_version: string
  data_retained: boolean
}
interface Package {
  module_id: string
  name: string
  version: string
  sha256: string | null
  kind: string
  installations: Installation[]
}
const { t } = useI18n()
const label = (key: string, fallback: string) => t('agentModules.' + key, fallback)
const items = ref<Package[]>([]),
  busy = ref(false),
  error = ref(''),
  loaded = ref(false)
const review = ref<{ item: Package; installation?: Installation } | null>(null)
const acknowledged = ref(false)
const requestId = ref(sessionStorage.getItem('agent-module-removal-request') || '')
const unresolved = ref(sessionStorage.getItem('agent-module-removal-lookup') || '')
const pending = (i: Installation) => ['queued', 'delivered'].includes(i.status)
const hasModuleInstallation = (item: Package) =>
  items.value.some(
    (p) =>
      p.module_id === item.module_id &&
      p.installations.some((i) => i.status !== 'uninstalled' || i.data_retained),
  )
async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = (await http.get('/api/v1/modules/agent-catalog')).data
    if (!Array.isArray(result.items)) throw new Error('Invalid catalog')
    items.value = result.items
    loaded.value = true
  } catch {
    error.value = label(
      'unavailable',
      'Agent inventory is unavailable. Previously loaded rows may be stale.',
    )
  } finally {
    busy.value = false
  }
}
function open(item: Package, installation?: Installation) {
  if (unresolved.value) return
  review.value = { item, installation }
  acknowledged.value = false
}
async function lookup() {
  if (busy.value || !unresolved.value.startsWith('/api/v1/modules/')) return
  busy.value = true
  error.value = ''
  try {
    const result = (await http.get(unresolved.value)).data
    if (['succeeded', 'failed'].includes(result.status)) {
      unresolved.value = ''
      sessionStorage.removeItem('agent-module-removal-lookup')
    } else
      error.value = label(
        'pending',
        'Removal is pending or unconfirmed. Keep the original request; do not replace it.',
      )
  } catch {
    error.value = label(
      'unconfirmed',
      'Removal was refused or is unconfirmed. Refresh status; do not submit a replacement request.',
    )
  } finally {
    busy.value = false
  }
  const previousError = error.value
  await load()
  error.value = previousError || error.value
}
async function apply() {
  if (!review.value || !acknowledged.value || busy.value) return
  const { item, installation } = review.value
  if (!item.sha256 && !installation) return
  busy.value = true
  error.value = ''
  review.value = null
  try {
    if (installation) {
      requestId.value = newHardwareRequestId()
      sessionStorage.setItem('agent-module-removal-request', requestId.value)
      const originalPath = `/api/v1/modules/${encodeURIComponent(item.module_id)}/devices/${installation.device_id}/uninstall`
      const originalBody = {
        package_sha256: item.sha256,
        expected_command_id: installation.command_id,
        request_id: requestId.value,
        confirmation: item.module_id,
      }
      unresolved.value = originalPath + '-requests/' + requestId.value
      sessionStorage.setItem('agent-module-removal-lookup', unresolved.value)
      await http.post(originalPath, originalBody)
    } else {
      await http.delete('/api/v1/modules/agent-packages/' + item.sha256)
    }
  } catch (failure) {
    // A definitive rejection from this endpoint did not commit a new command.
    // Timeouts, lost responses and server failures keep the original identity.
    if (
      axios.isAxiosError(failure) &&
      [400, 401, 403, 404, 409, 422].includes(failure.response?.status || 0)
    ) {
      unresolved.value = ''
      sessionStorage.removeItem('agent-module-removal-lookup')
    }
    error.value = label(
      'unconfirmed',
      'Removal was refused or is unconfirmed. Refresh status; do not submit a replacement request.',
    )
  } finally {
    busy.value = false
  }
  // Refresh is read-only. Never repeat the removal after an uncertain response.
  const previousError = error.value
  await load()
  error.value = previousError || error.value
}
onMounted(load)
defineExpose({ refresh: load })
</script>

<template>
  <section class="ui-section agent-modules-inventory" aria-labelledby="agent-modules-title">
    <details class="inventory-disclosure" :open="!!unresolved || !!error">
      <summary class="inventory-summary">
        <span class="disclosure-arrow" aria-hidden="true">›</span>
        <h2 id="agent-modules-title">
          {{ label('title', 'Agent modules and hardware providers') }}
        </h2>
        <span v-if="loaded" class="ui-badge inventory-count">{{ items.length }}</span>
      </summary>
      <div class="inventory-content">
        <header>
          <div>
            <p>
              {{
                label(
                  'help',
                  'Uploaded packages and installations on devices. Disabled is not uninstalled. Package deletion is separate from device removal.',
                )
              }}
            </p>
            <a href="/devices">{{
              label('manage', 'Configure and install hardware providers in Devices')
            }}</a>
          </div>
          <UiButton :disabled="busy" @click="load">{{
            label('refresh', 'Refresh status')
          }}</UiButton>
        </header>
        <p v-if="error" role="alert">{{ error }}</p>
        <p v-if="requestId">
          {{ label('request', 'Preserve removal request ID') }}: <code>{{ requestId }}</code>
        </p>
        <UiButton v-if="unresolved" :disabled="busy" @click="lookup">{{
          label('readOutcome', 'Read original removal outcome')
        }}</UiButton>
        <p v-if="loaded && !items.length">
          {{ label('empty', 'No Agent packages or recorded installations.') }}
        </p>
        <details
          v-for="item in items"
          :key="item.sha256 || item.module_id + ':' + item.version"
          class="agent-package"
        >
          <summary class="package-summary">
            <span class="package-name"
              ><strong>{{ item.name }}</strong
              ><small
                >{{ item.version }} ·
                {{
                  item.kind === 'hardware_provider'
                    ? label('provider', 'Hardware provider')
                    : label('module', 'Agent module')
                }}</small
              ></span
            >
            <span v-if="item.installations.length" class="installation-summaries">
              <span
                v-for="installation in item.installations"
                :key="installation.device_id"
                class="installation-summary"
              >
                <span class="device-name">{{ installation.display_name }}</span>
                <span class="installation-status"
                  >{{ installation.status }} ·
                  {{
                    installation.enabled
                      ? label('enabled', 'Enabled')
                      : label('disabled', 'Disabled')
                  }}</span
                >
              </span>
            </span>
            <span v-else class="installation-status">{{
              label('uploaded', 'No current device installation references this package version')
            }}</span>
            <span class="package-details-label"
              >{{ label('details', 'Details') }}
              <span class="disclosure-arrow" aria-hidden="true">›</span></span
            >
          </summary>
          <div class="package-content">
            <p>
              <code>{{ item.module_id }}</code>
            </p>
            <p v-if="!item.sha256" role="alert">
              {{
                label(
                  'missing',
                  'Package missing. The recorded installation remains visible and can still be removed from its device.',
                )
              }}
            </p>
            <p v-if="!item.installations.length">
              {{
                label('uploaded', 'No current device installation references this package version')
              }}
            </p>
            <div
              v-for="installation in item.installations"
              :key="installation.device_id"
              class="agent-installation"
            >
              <strong>{{ installation.display_name }}</strong> ·
              <code>{{ installation.device_id }}</code>
              <p>
                {{ label('status', 'Reported status') }}: {{ installation.status }} ·
                {{
                  installation.enabled ? label('enabled', 'Enabled') : label('disabled', 'Disabled')
                }}
              </p>
              <p>
                {{ label('installedVersion', 'Installed version') }}:
                {{ installation.installed_version || '—' }} ·
                {{ label('requestedVersion', 'Requested version') }}:
                {{ installation.desired_version }}
              </p>
              <p v-if="installation.command_id">
                {{ label('command', 'Latest command') }}: <code>{{ installation.command_id }}</code>
              </p>
              <p v-if="installation.error" role="alert">{{ installation.error }}</p>
              <p v-if="!installation.uninstall_supported">
                {{ label('upgrade', 'Update this Agent to support confirmed full removal.') }}
              </p>
              <UiButton
                v-if="installation.status !== 'uninstalled'"
                variant="danger"
                :disabled="
                  busy || !!unresolved || pending(installation) || !installation.uninstall_supported
                "
                @click="open(item, installation)"
                >{{ label('remove', 'Remove completely from device') }}</UiButton
              >
            </div>
            <UiButton
              v-if="item.sha256"
              variant="danger"
              :disabled="busy || !!unresolved || hasModuleInstallation(item)"
              @click="open(item)"
              >{{ label('delete', 'Delete uploaded package') }}</UiButton
            >
          </div>
        </details>
      </div>
    </details>
    <UiDialog
      :open="review !== null"
      :title="label('confirmTitle', 'Confirm removal')"
      :close-label="label('cancel', 'Cancel')"
      @update:open="review = null"
    >
      <template v-if="review">
        <p>{{ review.item.name }} · {{ review.item.version }}</p>
        <p>
          <code>{{ review.item.module_id }}</code>
        </p>
        <p>
          <code>{{ review.item.sha256 }}</code>
        </p>
        <template v-if="review.installation">
          <p>
            {{ review.installation.display_name }} ·
            <code>{{ review.installation.device_id }}</code>
          </p>
          <p>
            {{
              label(
                'removeHelp',
                'Stops this provider and permanently removes all its versions, saved profile and local module data from this device. It does not erase other modules, command receipts, the I²C host configuration or application data. The LCD may retain its last frame.',
              )
            }}
          </p>
          <p>
            {{
              label(
                'offline',
                'An offline or unconfirmed device stays listed until its Agent confirms removal. Dependent applications lose this provider; they are not silently rebound.',
              )
            }}
          </p>
        </template>
        <p v-else>
          {{
            label(
              'deleteHelp',
              'Permanently delete this uploaded package only after all devices have confirmed full removal. Other versions are not deleted.',
            )
          }}
        </p>
        <label
          ><input v-model="acknowledged" type="checkbox" />{{
            label('acknowledge', 'I reviewed the exact package, device and data to remove.')
          }}</label
        >
      </template>
      <template #actions
        ><UiButton @click="review = null">{{ label('cancel', 'Cancel') }}</UiButton>
        <UiButton variant="danger" :disabled="busy || !acknowledged" @click="apply">{{
          label('confirm', 'Confirm removal')
        }}</UiButton></template
      >
    </UiDialog>
  </section>
</template>

<style scoped>
section.agent-modules-inventory {
  padding: 0;
  margin-top: calc(var(--ui-space) * 6);
}
summary {
  cursor: pointer;
  list-style: none;
}
summary::-webkit-details-marker {
  display: none;
}
.inventory-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: var(--ui-control-height, 44px);
  padding: 0.875rem 1rem;
}
.inventory-summary h2 {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.inventory-count {
  flex: none;
}
.disclosure-arrow {
  display: inline-block;
  font-size: 1.3em;
  line-height: 1;
  transition: transform 0.15s;
}
.inventory-disclosure[open] > summary > .disclosure-arrow,
.agent-package[open] > summary .disclosure-arrow {
  transform: rotate(90deg);
}
.inventory-content {
  padding: 0 1rem 1rem;
}
header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
}
header > div {
  flex: 1 1 24rem;
  min-width: 0;
}
header p,
.package-name small,
.installation-status {
  color: var(--ui-text-secondary);
}
.agent-package {
  border-top: 1px solid var(--ui-border);
}
.package-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) auto;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 0;
}
.package-name,
.installation-summaries {
  display: grid;
  gap: 0.25rem;
  min-width: 0;
}
.package-name small {
  font-size: 0.85em;
}
.installation-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  align-items: baseline;
  gap: 0.5rem;
}
.package-details-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9em;
  color: var(--ui-accent);
}
.package-content {
  padding: 0 0 1rem;
}
.agent-installation {
  margin-block: 0.75rem;
  padding: 0.75rem;
  background: var(--ui-surface-alt);
  border-radius: var(--ui-radius-sm);
}
.agent-modules-inventory p {
  margin-block: 0.5rem;
}
p,
code,
.package-summary span {
  overflow-wrap: anywhere;
}
[role='alert'] {
  color: var(--ui-danger);
}
@media (max-width: 640px) {
  .package-summary {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.5rem 0.75rem;
  }
  .package-name {
    grid-column: 1;
  }
  .installation-summaries,
  .package-summary > .installation-status {
    grid-column: 1 / -1;
    grid-row: 2;
  }
  .package-details-label {
    grid-column: 2;
    grid-row: 1;
  }
}
</style>
