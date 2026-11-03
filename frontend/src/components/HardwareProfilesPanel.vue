<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { UiButton, UiDialog, UiSurface } from '@/extension-ui/v1'
import { useI18n } from '@/utils/i18n'
import { hardwareProfilesClient, newHardwareRequestId, type HardwareProfileCatalog,
  type HardwareProfilePackage } from '@/utils/hardware-profiles'
const props = defineProps<{ deviceId: string; name: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const label = (key: string, fallback: string) => t('hardwareProfiles.' + key, fallback)
const client = hardwareProfilesClient(props.deviceId), storageKey = 'hardware-profile-request:' + props.deviceId
const catalog = ref<HardwareProfileCatalog | null>(null), busy = ref(false), uncertain = ref(false)
const requestId = ref(''), error = ref(''), selected = ref(''), acknowledged = ref(false)
const review = ref<{ action: 'install' | 'disable'; item: HardwareProfilePackage } | null>(null)
const item = computed(() => catalog.value?.items.find(i => i.sha256 === selected.value))
const running = (p: HardwareProfilePackage) => p.installed_exact && p.installation?.enabled && p.installation.status === 'succeeded'
const pending = (p: HardwareProfilePackage) => p.installation && ['queued', 'delivered'].includes(p.installation.status)
let generation = 0
onBeforeUnmount(() => { ++generation })
async function load() {
  if (busy.value) return
  const episode = ++generation
  busy.value = true; error.value = ''; review.value = null
  try {
    const current = await client.inspect()
    if (episode !== generation) return
    catalog.value = current
    if (!current.items.some(i => i.sha256 === selected.value)) selected.value = current.items[0]?.sha256 || ''
    uncertain.value = !!requestId.value && !current.items.some(i => i.request_id === requestId.value)
  } catch { if (episode === generation) { catalog.value = null; error.value = 'unavailable' } }
  finally { if (episode === generation) busy.value = false }
}
function open(action: 'install' | 'disable') {
  if (!item.value || busy.value || uncertain.value) return
  review.value = { action, item: item.value }; acknowledged.value = false
}
async function apply() {
  if (!review.value || !acknowledged.value || busy.value || uncertain.value) return
  const reviewed = review.value, episode = ++generation
  busy.value = true; error.value = ''; review.value = null
  try {
    requestId.value = newHardwareRequestId()
    sessionStorage.setItem(storageKey, requestId.value)
    await client.mutate(reviewed.action, reviewed.item, requestId.value)
    if (episode === generation) uncertain.value = true
  } catch { if (episode === generation) { uncertain.value = true; error.value = 'unconfirmed' } }
  finally { if (episode === generation) busy.value = false }
  if (episode === generation) await load()
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file || busy.value) return
  const episode = ++generation
  busy.value = true; error.value = ''; review.value = null
  try { await client.upload(file) }
  catch { if (episode === generation) error.value = 'uploadFailed' }
  finally { if (episode === generation) busy.value = false; input.value = '' }
  if (episode === generation && !error.value) await load()
}
onMounted(() => { requestId.value = sessionStorage.getItem(storageKey) || ''; void load() })
</script>

<template>
  <UiSurface class="hardware-profiles">
    <header><div><h3>{{ label('title', 'Hardware providers') }}</h3><p>{{ name }} · <code>{{ deviceId }}</code></p></div>
      <UiButton variant="quiet" :aria-label="label('close', 'Close')" @click="emit('close')">×</UiButton></header>
    <p>{{ label('help', 'Review the exact device, package and hardware profile before installation. This is not an application permission.') }}</p>
    <div class="actions"><UiButton class="refresh-profiles" :disabled="busy" @click="load">{{ label('refresh', 'Refresh status') }}</UiButton>
      <label>{{ label('upload', 'Upload provider ZIP') }} <input class="upload-provider" type="file" accept=".zip" :disabled="busy" @change="upload"></label></div>
    <p v-if="error || uncertain" role="alert">{{ label(error || 'unconfirmed', 'Outcome unavailable or unconfirmed. Refresh status; do not repeat the request.') }}</p>
    <p v-if="requestId">{{ label('preserve', 'Preserve request ID') }}: <code>{{ requestId }}</code></p>
    <template v-if="catalog">
      <p v-if="!catalog.approval_supported" role="status">{{ label('unsupported', 'The Agent has not advertised hardware-profile approval support. Update Agent before installation.') }}</p>
      <p v-if="!catalog.items.length">{{ label('empty', 'No hardware-profile package is uploaded. Upload its immutable ZIP first.') }}</p>
      <label v-else>{{ label('package', 'Provider package') }}
        <select v-model="selected" class="select-profile" :disabled="busy" @change="review = null">
          <option v-for="p in catalog.items" :key="p.sha256" :value="p.sha256">{{ p.name }} · {{ p.version }}</option>
        </select></label>
      <section v-if="item" class="profile-card">
        <p><code>{{ item.module_id }}</code></p>
        <p>{{ label('packageHash', 'Package SHA-256') }}: <code>{{ item.sha256 }}</code></p>
        <p>{{ label('profileHash', 'Profile SHA-256') }}: <code>{{ item.profile.profile_sha256 }}</code></p>
        <p>{{ item.profile.simulated ? label('mock', 'Simulated provider') : label('physical', 'Physical hardware profile') }}</p>
        <dl><template v-for="(value, key) in item.profile.configuration" :key="key"><dt>{{ key }}</dt><dd>{{ typeof value === 'object' ? JSON.stringify(value) : String(value) }}</dd></template></dl>
        <p v-if="item.installation" role="status">{{ label('installation', 'Reported installation status') }}: {{ item.installation.status }} · {{ item.installation.enabled ? label('enabled', 'Enabled') : label('disabled', 'Disabled') }}</p>
        <p v-if="item.installation?.error" role="alert">{{ item.installation.error }}</p>
        <p>{{ label('noIo', 'Installation does not scan the bus, send a display frame, grant application rights or reboot. Physical wiring is not verified by software.') }}</p>
        <div class="actions">
          <UiButton class="review-profile" :disabled="busy || uncertain || !catalog.approval_supported || !!pending(item) || !!running(item)" @click="open('install')">{{ label('review', 'Review profile and installation') }}</UiButton>
          <UiButton v-if="running(item)" class="disable-profile" :disabled="busy || uncertain" @click="open('disable')">{{ label('disable', 'Disable provider') }}</UiButton>
        </div>
      </section>
    </template>
    <UiDialog :open="review !== null" :title="label('review', 'Review profile and installation')" :close-label="label('close', 'Close')" @update:open="review = null">
      <template v-if="review"><p>{{ name }} · <code>{{ deviceId }}</code></p>
        <p>{{ review.item.name }} · {{ review.item.version }}</p>
        <p><code>{{ review.item.sha256 }}</code></p><p><code>{{ review.item.profile.profile_sha256 }}</code></p>
        <dl><template v-for="(value, key) in review.item.profile.configuration" :key="key"><dt>{{ key }}</dt><dd>{{ String(value) }}</dd></template></dl>
        <p>{{ review.action === 'disable' ? label('disableHelp', 'Disable this provider and prevent new capability execution. The physical display may retain its last contents.') : label('approveHelp', 'Approve this exact hardware profile and install/activate its provider on this device. No test frame is sent; application access still requires a separate M20 grant.') }}</p>
        <p>{{ label('noIo', 'Installation does not scan the bus, send a display frame, grant application rights or reboot. Physical wiring is not verified by software.') }}</p>
        <label class="acknowledge"><input v-model="acknowledged" type="checkbox">{{ label('acknowledge', 'I reviewed this exact device, package and hardware profile.') }}</label>
      </template>
      <template #actions><UiButton @click="review = null">{{ label('cancel', 'Cancel') }}</UiButton>
        <UiButton class="confirm-profile" :disabled="busy || !acknowledged" @click="apply">{{ label('confirm', 'Confirm') }}</UiButton></template>
    </UiDialog>
  </UiSurface>
</template>

<style scoped>
.hardware-profiles { margin-block: 1rem; padding: 1.25rem; color: var(--ui-text); background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); min-width: 0; }
header, .actions { display: flex; justify-content: space-between; align-items: start; flex-wrap: wrap; gap: .75rem; }
.actions { justify-content: flex-start; margin-block: 1rem; }
h3 { margin-block: 0 .5rem; }
p, code, dd, dt { overflow-wrap: anywhere; }
code { white-space: normal; }
.select-profile { display: block; width: 100%; font: inherit; color: var(--ui-text); background: var(--ui-surface-alt); padding: .75rem; border: 1px solid var(--ui-border); }
.profile-card { margin-top: 1rem; padding: 1rem; background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
dl { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .5rem 1rem; }
dd { margin: 0; }
.acknowledge { display: flex; gap: .5rem; }
[role="alert"] { color: var(--ui-danger); }
@media (max-width: 600px) { .hardware-profiles, .profile-card { padding: .75rem; } dl { grid-template-columns: 1fr; } input { max-width: 100%; } }
</style>
