<script setup lang="ts">
import { computed, onMounted, ref, onBeforeUnmount } from 'vue'
import { UiSurface, UiButton, UiDialog } from '@/extension-ui/v1'
import { useI18n } from '@/utils/i18n'
import { hardwareClient, newHardwareRequestId, type HardwareStatus } from '@/utils/hardware-interfaces'

const props = defineProps<{ deviceId: string; name: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const label = (key: string, fallback: string) => t(`hardwareInterfaces.${key}`, fallback)
const client = hardwareClient(props.deviceId)
const snapshot = ref<HardwareStatus | null>(null), busy = ref(false), uncertain = ref(false)
const error = ref(''), requestId = ref(''), confirmation = ref<'enable' | 'restart' | null>(null)
const acknowledged = ref(false)
let generation = 0
onBeforeUnmount(() => { ++generation })
const restartable = computed(() => snapshot.value?.supported && snapshot.value?.configured
  && snapshot.value.operation?.state === 'pending_reboot' && !snapshot.value.operation.restart_request_id)
const state = computed(() => snapshot.value?.operation?.state || (snapshot.value?.ready ? 'verified' : 'not_configured'))
const stateText = computed(() => {
  const labels: Record<string, string> = {
  queued: label('queued', 'Preparation queued'), applying: label('applying', 'Preparing configuration'),
  pending_reboot: label('pending', 'Configured — restart required'), verified: label('ready', 'I²C ready'),
  verification_failed: label('verificationFailed', 'Restart detected, but live I²C or Agent access was not verified'),
  recovery_required: label('recovery', 'Outcome requires inspection; do not repeat the change'),
  failed: label('failed', 'Preparation failed; inspect the result before a new review'),
  not_configured: label('notConfigured', 'Not configured'),
  }
  return labels[state.value] || label('unknown', 'Current readiness is unknown')
})
async function load() {
  if (busy.value) return
  busy.value = true; error.value = ''; confirmation.value = null
  const episode = ++generation
  try {
    const current = await client.inspect()
    if (episode !== generation) return
    snapshot.value = current
    // A missing receipt is not evidence that a lost mutation never executed.
    uncertain.value = !!requestId.value && current.operation?.request_id !== requestId.value
      && current.operation?.restart_request_id !== requestId.value
  } catch { if (episode === generation) { snapshot.value = null; error.value = 'unavailable' } }
  finally { if (episode === generation) busy.value = false }
}
function review(kind: 'enable' | 'restart') {
  if (busy.value || uncertain.value) return
  acknowledged.value = false; confirmation.value = kind
}
async function apply() {
  if (!snapshot.value || !confirmation.value || !acknowledged.value || busy.value || uncertain.value) return
  const kind = confirmation.value, current = snapshot.value, episode = ++generation
  busy.value = true; confirmation.value = null; error.value = ''
  try {
    requestId.value = newHardwareRequestId()
    // Remember before dispatch, including across a tab reload or a lost response.
    sessionStorage.setItem(`hardware-request:${props.deviceId}`, requestId.value)
    await client.mutate(kind, current, requestId.value)
    if (episode !== generation) return
    uncertain.value = true
  } catch { if (episode === generation) { error.value = 'unconfirmed'; uncertain.value = true } }
  finally { if (episode === generation) busy.value = false }
  if (episode === generation) await load()
}
onMounted(() => {
  requestId.value = sessionStorage.getItem(`hardware-request:${props.deviceId}`) || ''
  void load()
})
</script>

<template>
  <UiSurface class="hardware-panel">
    <header>
      <div><h3>{{ label('title', 'Hardware interfaces') }}</h3><p>{{ name }} · <code>{{ deviceId }}</code></p></div>
      <UiButton variant="quiet" :aria-label="label('close', 'Close')" @click="emit('close')">×</UiButton>
    </header>
    <p>{{ label('help', 'Enable the host interface first. Providers and application permissions are separate approvals.') }}</p>
    <UiButton class="refresh-hardware" :disabled="busy" @click="load">{{ label('refresh', 'Refresh status') }}</UiButton>
    <p v-if="error || uncertain" role="alert">{{ label(error || 'unconfirmed', error === 'unavailable'
      ? 'Current status is unavailable. No readiness is confirmed.' : 'Outcome unconfirmed. Preserve the request ID; do not resubmit.') }}</p>
    <p v-if="requestId">{{ label('preserve', 'Preserve request ID') }}: <code>{{ requestId }}</code></p>
    <p v-if="snapshot?.operation && snapshot.operation.request_id !== requestId">{{ label('preserve', 'Preserve request ID') }}: <code>{{ snapshot.operation.request_id }}</code></p>
    <template v-if="snapshot">
      <p v-if="!snapshot.supported" role="status">{{ label('unsupported', 'This device or its host configuration is not supported by this I²C profile. No change was made.') }} <code>{{ snapshot.reason }}</code></p>
      <section v-else class="i2c-card">
        <h4>I²C-1 · 100 kHz</h4>
        <p>SDA: GPIO2 / pin 3 · SCL: GPIO3 / pin 5</p>
        <strong role="status">{{ stateText }}</strong>
        <p v-if="snapshot.operation?.reason"><code>{{ snapshot.operation.reason }}</code></p>
        <dl>
          <dt>{{ label('adapter', 'Live adapter') }}</dt><dd>{{ snapshot.live?.adapter_present ? label('present', 'Present') : label('absent', 'Absent') }}</dd>
          <dt>{{ label('node', 'Device node') }}</dt><dd>{{ snapshot.live?.device_node_present ? label('present', 'Present') : label('absent', 'Absent') }}</dd>
          <dt>{{ label('access', 'Running Agent access') }}</dt><dd>{{ snapshot.live?.agent_access ? label('verified', 'Verified') : label('notVerified', 'Not verified') }}</dd>
        </dl>
        <p v-if="!snapshot.live?.agent_running">{{ label('agentUnavailable', 'The local Agent is not running; configuration is unavailable.') }}</p>
        <p>{{ label('noIo', 'This does not scan the bus, write to the display or approve an application.') }}</p>
        <UiButton class="enable-i2c" :disabled="busy || uncertain || !snapshot.can_enable" @click="review('enable')">{{ label('reviewEnable', 'Review I²C enablement') }}</UiButton>
        <UiButton v-if="restartable" class="restart-i2c" :disabled="busy || uncertain" @click="review('restart')">{{ label('reviewRestart', 'Review device restart') }}</UiButton>
        <p v-if="snapshot.operation?.restart_request_id">{{ label('restartRequested', 'Restart requested. Reconnect after the device starts and refresh status; do not repeat the request.') }}</p>
      </section>
    </template>
    <UiDialog :open="confirmation !== null" :title="confirmation === 'restart' ? label('reviewRestart', 'Review device restart') : label('reviewEnable', 'Review I²C enablement')"
      :close-label="label('close', 'Close')" @update:open="confirmation = null">
      <p><strong>{{ name }}</strong> · <code>{{ deviceId }}</code></p>
      <template v-if="confirmation === 'enable'">
        <p>I²C-1 · 100 kHz · GPIO2 / pin 3 · GPIO3 / pin 5</p>
        <p>{{ label('enableHelp', 'Prepare boot configuration, i2c-dev loading and an i2c supplementary group for the Agent service only. Applying does not restart the device.') }}</p>
        <ul><li v-for="path in snapshot?.changes" :key="path"><code>{{ path }}</code></li></ul>
        <p>{{ label('electrical', 'Software does not verify wiring or signal voltage. Use electrically compatible hardware.') }}</p>
      </template>
      <p v-else>{{ label('restartHelp', 'Restart this exact device now? Core and its local workloads will briefly be unavailable. This does not reset data, role or network configuration.') }}</p>
      <label class="acknowledgment"><input v-model="acknowledged" type="checkbox">{{ label('acknowledge', 'I have reviewed this exact device and change.') }}</label>
      <template #actions>
        <UiButton @click="confirmation = null">{{ label('cancel', 'Cancel') }}</UiButton>
        <UiButton class="confirm-hardware" :disabled="!acknowledged || busy" @click="apply">{{ label('confirm', 'Confirm') }}</UiButton>
      </template>
    </UiDialog>
  </UiSurface>
</template>

<style scoped>
.hardware-panel { margin-block: 1rem; padding: 1.25rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface); color: var(--ui-text); }
header { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
h3, h4 { margin-block: 0 .5rem; }
p { margin-block: .75rem; }
.i2c-card { margin-top: 1rem; padding: 1rem; background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .5rem 1rem; margin-block: 1rem; }
dd { margin: 0; }
code { overflow-wrap: anywhere; }
[role="alert"] { color: var(--ui-danger); }
.acknowledgment { display: flex; align-items: start; gap: .5rem; margin-block: 1rem; }
@media (max-width: 600px) { .hardware-panel { padding: .75rem; } dl { grid-template-columns: 1fr; } .i2c-card :deep(.ui-button) { margin-block: .25rem; width: 100%; } }
</style>
