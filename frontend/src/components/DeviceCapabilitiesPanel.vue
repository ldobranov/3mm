<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { UiButton, UiState, UiSurface } from '@/extension-ui/v1'
import { getToken } from '@/utils/auth'
import { CapabilityAdminError, createDeviceCapabilitiesClient, providerKey, sameIds,
  type DeviceProvider, type DeviceCapabilityOffer } from '@/utils/device-capabilities'
import { useDeviceCapabilityLabels, deviceCapabilityEnglish, type DeviceCapabilityLabel } from './device-capability-labels'

const props = defineProps<{ deviceId: string; name: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const label = useDeviceCapabilityLabels(), client = createDeviceCapabilitiesClient(props.deviceId)
const isAdmin = () => !!getToken() && localStorage.getItem('role') === 'admin'
const providers = ref<DeviceProvider[]>([]), offers = ref<DeviceCapabilityOffer[]>([])
const drafts = ref<Record<string, string[]>>({})
const busy = ref(false), loaded = ref(false), needsRefresh = ref(false)
const error = ref<DeviceCapabilityLabel | null>(null), notice = ref<DeviceCapabilityLabel | null>(null)
let generation = 0
onBeforeUnmount(() => { ++generation })
const readOnlyOffers = computed(() => offers.value.filter(o => !providers.value.some(p =>
  o.provider_type === p.provider_type && o.provider_id === p.provider_id)))
const selected = (p: DeviceProvider) => p.configured_capability_ids ?? p.capabilities.map(c => c.capability_id)
const dirty = (p: DeviceProvider) => !sameIds(drafts.value[providerKey(p)] ?? [], selected(p))
const offeredIds = (p: DeviceProvider) => p.capabilities.map(c => c.capability_id)
const allIds = (p: DeviceProvider) => [...new Set([...offeredIds(p), ...selected(p)])]
const validSelection = (p: DeviceProvider) => (drafts.value[providerKey(p)] ?? []).every(id => offeredIds(p).includes(id))
const reset = (p: DeviceProvider) => { drafts.value[providerKey(p)] = [...selected(p)] }
function status(offer: DeviceCapabilityOffer | undefined): string {
  if (offer?.available === true) return label('ready')
  if (!offer || offer.available === null) return label('unknown')
  const reason = offer.unavailable_reason
  return reason && Object.prototype.hasOwnProperty.call(deviceCapabilityEnglish, reason) ? label(reason as DeviceCapabilityLabel)
    : `${label('unavailableStatus')}${reason ? ` (${reason})` : ''}`
}
const offerFor = (p: DeviceProvider, id: string) => offers.value.find(o =>
  o.provider_type === p.provider_type && o.provider_id === p.provider_id && o.capability_id === id)
async function load() {
  if (busy.value) return
  if (!isAdmin()) { error.value = 'denied'; loaded.value = false; return }
  const episode = ++generation
  busy.value = true; error.value = null; notice.value = null; loaded.value = false
  try {
    const current = await client.inspect()
    if (episode !== generation) return
    providers.value = current.providers; offers.value = current.offers
    drafts.value = Object.fromEntries(providers.value.map(p => [providerKey(p), [...selected(p)]]))
    needsRefresh.value = false; loaded.value = true
  } catch (e) {
    if (episode === generation) error.value = e instanceof CapabilityAdminError ? e.code : 'unavailable'
  } finally { if (episode === generation) busy.value = false }
}
async function save(p: DeviceProvider, enabled?: boolean) {
  if (busy.value || needsRefresh.value || !loaded.value) return
  if (!isAdmin()) { error.value = 'denied'; needsRefresh.value = true; return }
  const episode = ++generation
  busy.value = true; error.value = null; notice.value = null
  try {
    const next = typeof enabled === 'boolean' ? await client.enable(p, enabled)
      : await client.configure(p, [...drafts.value[providerKey(p)]!])
    if (episode !== generation) return
    providers.value = providers.value.map(item => providerKey(item) === providerKey(next) ? next : item)
    reset(next); notice.value = 'saved'; emit('changed')
    try {
      const current = await client.offers()
      if (episode === generation) offers.value = current
    } catch { if (episode === generation) { notice.value = 'savedStatusMissing'; needsRefresh.value = true } }
  } catch (e) {
    if (episode === generation) {
      error.value = e instanceof CapabilityAdminError ? e.code : 'unconfirmed'
      needsRefresh.value = true
    }
  } finally { if (episode === generation) busy.value = false }
}
onMounted(load)
</script>

<template>
  <UiSurface class="capability-panel">
    <div class="panel-heading">
      <div><h3>{{ label('title') }}</h3><p class="device-name">{{ name }}</p></div>
      <div class="panel-actions">
        <UiButton class="refresh-sources" :disabled="busy" @click="load">{{ label('refresh') }}</UiButton>
        <UiButton variant="quiet" :disabled="busy" :aria-label="label('close')" @click="emit('close')">×</UiButton>
      </div>
    </div>
    <p>{{ label('help') }}</p>
    <UiState v-if="busy && !loaded" kind="loading" :message="label('loading')" />
    <UiState v-if="error" kind="error" :message="label(error)" />
    <p v-if="notice" class="notice" role="status">{{ label(notice) }}</p>
    <template v-if="loaded">
      <UiState v-if="!providers.length && !offers.length" kind="empty" :message="label('empty')" />
      <div class="provider-list">
        <section v-for="p in providers" :key="providerKey(p)" class="provider-card" :aria-label="p.provider_id">
          <div class="panel-heading">
            <div><h4>{{ p.provider_id }}</h4><p class="provider-meta">{{ p.provider_type }} · {{ p.provider_version }}</p>
              <p>{{ label(p.enabled ? 'enabled' : 'disabled') }}</p></div>
            <UiButton class="toggle-provider" :disabled="busy || needsRefresh" @click="save(p, !p.enabled)">
              {{ label(p.enabled ? 'disable' : 'enable') }}
            </UiButton>
          </div>
          <p v-if="!p.capabilities.length">{{ label('noOffers') }}</p>
          <fieldset :disabled="busy || needsRefresh || p.schema_version !== 2">
            <legend class="visually-hidden">{{ p.provider_id }}</legend>
            <label v-for="id in allIds(p)" :key="id" class="capability-choice">
              <input v-model="drafts[providerKey(p)]" type="checkbox" :value="id" :aria-label="`${p.provider_id}: ${id}`" />
              <span><code>{{ id }}</code>
                <small v-if="!offeredIds(p).includes(id)">{{ label('withdrawn') }}</small>
                <small v-else>{{ label(selected(p).includes(id) ? 'selected' : 'notSelected') }} · {{ status(offerFor(p, id)) }}</small>
              </span>
            </label>
          </fieldset>
          <p v-if="p.schema_version !== 2" class="provider-meta">{{ label('providerManaged') }}</p>
          <div v-else class="panel-actions">
            <UiButton class="save-selection" variant="primary" :disabled="busy || needsRefresh || !dirty(p) || !validSelection(p)" @click="save(p)">
              {{ label('save') }}
            </UiButton>
            <UiButton :disabled="busy || needsRefresh || !dirty(p)" @click="reset(p)">{{ label('reset') }}</UiButton>
          </div>
        </section>
        <section v-if="readOnlyOffers.length" class="provider-card">
          <h4>{{ label('otherSources') }}</h4>
          <div v-for="(offer, i) in readOnlyOffers" :key="i" class="managed-offer">
            <code>{{ offer.capability_id }}</code><span>{{ offer.provider_id || '—' }} · {{ status(offer) }}</span>
            <small v-if="offer.provider_id">{{ label('installationManaged') }}</small>
          </div>
        </section>
      </div>
    </template>
  </UiSurface>
</template>

<style scoped>
.capability-panel { margin-top: 1.5rem; padding: calc(var(--ui-space) * 5); color: var(--ui-text); background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); min-width: 0; box-shadow: var(--ui-card-shadow); }
.panel-heading, .panel-actions { display: flex; align-items: flex-start; justify-content: space-between; gap: .75rem; flex-wrap: wrap; }
.panel-heading > div { min-width: 0; }
.panel-actions { justify-content: flex-start; }
.provider-list { display: grid; gap: 1rem; margin-top: 1rem; }
.provider-card { padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-surface-alt); min-width: 0; box-shadow: var(--ui-card-shadow); }
h3, h4, p { margin: 0 0 .6rem; }
h4, code, .device-name, .provider-meta, small, .managed-offer { overflow-wrap: anywhere; }
code { color: var(--ui-text); white-space: normal; }
.provider-meta, small, .managed-offer > span { color: var(--ui-text-muted); }
fieldset { border: 0; padding: 0; margin: .5rem 0 1rem; min-width: 0; }
.capability-choice { display: flex; align-items: flex-start; gap: .65rem; padding: .65rem 0; cursor: pointer; }
.capability-choice input { margin-top: .25rem; accent-color: var(--ui-accent); flex-shrink: 0; }
.capability-choice span { min-width: 0; }
small, .managed-offer > span { display: block; margin-top: .25rem; }
.managed-offer { padding: .6rem 0; }
.notice { color: var(--ui-text); border-inline-start: 3px solid var(--ui-accent); padding: .75rem; background: var(--ui-surface-alt); }
@media (max-width: 600px) { .capability-panel, .provider-card { padding: .85rem; } .panel-actions > button { max-width: 100%; white-space: normal; } }
</style>
