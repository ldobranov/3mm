<template>
  <UiSurface class="output-button">
    <header><div><h1>{{ t('title') }}</h1><p>{{ t('intro') }}</p></div>
      <button :disabled="busy" @click="refresh()">{{ t('refresh') }}</button></header>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <section class="panel">
      <h2>{{ t('resource') }}</h2>
      <template v-if="observation?.access === 'granted'">
        <dl><dt>{{ t('device') }}</dt><dd><code>{{ observation.target_device_id }}</code></dd>
          <dt>{{ t('provider') }}</dt><dd><code>{{ observation.provider_id }}</code></dd></dl>
        <p role="status">{{ observation.readiness === 'ready' ? t('ready') : t('unavailable') }}</p>
      </template>
      <p v-else>{{ t('access') }}</p>
      <div class="controls"><button :disabled="!canSend" @click="send(true)">{{ t('on') }}</button>
        <button :disabled="!canSend" @click="send(false)">{{ t('off') }}</button></div>
    </section>
    <section v-if="pending || result" class="panel" aria-live="polite">
      <h2>{{ t('outcome') }}</h2>
      <p>{{ statusText }}</p>
      <p v-if="result?.confirmed_value !== null && result?.confirmed_value !== undefined">
        {{ t('lastConfirmed') }}: <strong>{{ result.confirmed_value ? t('onValue') : t('offValue') }}</strong>
      </p>
      <p v-if="result?.target_device_id">{{ t('originalDevice') }}: <code>{{ result.target_device_id }}</code></p>
      <p>{{ t('request') }}: <code>{{ pending?.request_id || result?.request_id }}</code></p>
      <template v-if="pending">
        <p>{{ t('noReplay') }}</p>
        <button :disabled="busy" @click="refresh()">{{ t('check') }}</button>
        <template v-if="!busy && !['queued', 'delivered'].includes(result?.status || '')">
          <label><input v-model="reviewed" type="checkbox" /> {{ t('review') }}</label>
          <button :disabled="!reviewed" @click="clearReviewed">{{ t('clear') }}</button>
        </template>
      </template>
    </section>
  </UiSurface>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { UiSurface } from '@3mm/ui/v1'
import { useApplicationHost, type ApplicationPayload } from '@3mm/application-ui/v1'

const host = useApplicationHost()
const messages = {
  en: { title: 'Output button', intro: 'Control the single output approved for this application.', refresh: 'Refresh',
    resource: 'Approved resource', device: 'Device', provider: 'Provider', ready: 'Ready', unavailable: 'Resource is unavailable.',
    access: 'An administrator must select and approve an output in Application access / Command resources.',
    on: 'Switch on', off: 'Switch off', outcome: 'Command outcome', lastConfirmed: 'Last confirmed command result',
    originalDevice: 'Original command device', request: 'Request ID', noReplay: 'This request is preserved. Only its status is read; it is never sent again.',
    check: 'Check status', review: 'I checked the outcome on the original device.', clear: 'Clear this request',
    failed: 'Command failed. Review the device outcome.', expired: 'Command expired.', invalidated: 'Command authority changed. Review the original device outcome.',
    queued: 'Queued — waiting for device confirmation.', delivered: 'Delivered — waiting for device confirmation.',
    succeeded: 'Confirmed by the device', unknown: 'Outcome unconfirmed. Check status before another command.',
    not_submitted: 'No command was submitted; resource access or readiness is missing.', onValue: 'On', offValue: 'Off',
    readError: 'Current access or status is unavailable.', storageError: 'The request cannot be saved in this browser. Sending is blocked.' },
  bg: { title: 'Управление на изход', intro: 'Управление само на изхода, одобрен за това приложение.', refresh: 'Обнови',
    resource: 'Одобрен ресурс', device: 'Устройство', provider: 'Доставчик', ready: 'В готовност', unavailable: 'Ресурсът е недостъпен.',
    access: 'Администратор трябва да избере и одобри изход в Application access / Command resources.',
    on: 'Включи', off: 'Изключи', outcome: 'Резултат от командата', lastConfirmed: 'Последен потвърден резултат от команда',
    originalDevice: 'Първоначално устройство на командата', request: 'Идентификатор на заявката',
    noReplay: 'Заявката е запазена. Проверява се само статусът ѝ; тя не се изпраща повторно.',
    check: 'Провери статуса', review: 'Проверих резултата на първоначалното устройство.', clear: 'Освободи тази заявка',
    failed: 'Командата е неуспешна. Проверете резултата на устройството.', expired: 'Срокът на командата изтече.',
    invalidated: 'Правото за командата е променено. Проверете първоначалното устройство.',
    queued: 'На опашка — изчаква потвърждение от устройството.', delivered: 'Доставена — изчаква потвърждение от устройството.',
    succeeded: 'Потвърдено от устройството', unknown: 'Резултатът не е потвърден. Проверете статуса преди друга команда.',
    not_submitted: 'Не е изпратена команда; липсва достъп или готовност на ресурса.', onValue: 'Включен', offValue: 'Изключен',
    readError: 'Текущият достъп или статус е недостъпен.', storageError: 'Заявката не може да се запази в този браузър. Изпращането е блокирано.' },
}
const language = ref('en')
const updateLanguage = () => { try { language.value = localStorage.getItem('preferredLanguage') || 'en' } catch { /* English remains available. */ } }
updateLanguage()
const t = (key: keyof typeof messages.en) => messages[language.value.startsWith('bg') ? 'bg' : 'en'][key]
const storageKey = '3mm.command-probe.pending.v1'
type Pending = { request_id: string; value: boolean }
type Outcome = { request_id: string; status: string; confirmed_value: boolean | null; target_device_id: string | null }
type Observation = { access: string; readiness: string; target_device_id: string | null; provider_id: string | null }
const pending = ref<Pending | null>(null), result = ref<Outcome | null>(null), observation = ref<Observation | null>(null)
const busy = ref(false), error = ref(''), reviewed = ref(false), storageOk = ref(true), allowed = ref(false)
let disposed = false, reading = false, observedAt = 0, timer: ReturnType<typeof setInterval> | undefined
const statuses = ['queued', 'delivered', 'succeeded', 'failed', 'expired', 'unknown', 'invalidated', 'not_found', 'not_submitted']
const statusText = computed(() => {
  const status = result.value?.status
  return t(status && statuses.includes(status) && status !== 'not_found' ? status as keyof typeof messages.en : 'unknown')
})
const canSend = computed(() => !busy.value && !pending.value && !error.value && storageOk.value && allowed.value
  && observation.value?.access === 'granted' && observation.value.readiness === 'ready' && Date.now() - observedAt < 15000)

function save(value: Pending | null) {
  try {
    if (value) localStorage.setItem(storageKey, JSON.stringify(value))
    else localStorage.removeItem(storageKey)
    pending.value = value
    return true
  } catch { storageOk.value = false; error.value = t('storageError'); return false }
}
function accept(value: ApplicationPayload, requestId: string) {
  if (value.request_id !== requestId || typeof value.status !== 'string' || !statuses.includes(value.status)
      || !(value.confirmed_value === null || typeof value.confirmed_value === 'boolean')
      || !(value.target_device_id === null || typeof value.target_device_id === 'string')) throw new Error('Invalid outcome')
  result.value = value as unknown as Outcome
  if ((value.status === 'succeeded' && typeof value.confirmed_value === 'boolean') || value.status === 'not_submitted') save(null)
}
async function refresh(background = false) {
  if (busy.value || reading || disposed) return
  const requestAtStart = pending.value?.request_id
  const lock = !background || !!requestAtStart
  reading = true
  if (lock) busy.value = true
  try {
    const info = await host.getInfo()
    if (info.module_id !== 'org.3mm.command-probe') throw new Error('Foreign application')
    const operations = new Set(info.operations.map(value => value.operation_id))
    allowed.value = ['observe', 'set_output', 'lookup'].every(value => operations.has(value))
    const value = await host.invoke('observe', {})
    if (disposed) return
    if (!['required', 'granted'].includes(String(value.access)) || !['ready', 'unavailable', 'unknown'].includes(String(value.readiness))
        || !(value.target_device_id === null || typeof value.target_device_id === 'string')
        || !(value.provider_id === null || typeof value.provider_id === 'string')) throw new Error('Invalid observation')
    observation.value = value as unknown as Observation
    observedAt = Date.now()
    if (requestAtStart && pending.value?.request_id === requestAtStart) {
      const id = requestAtStart
      const status = await host.invoke('lookup', { request_id: id })
      if (disposed) return
      accept(status, id)
    }
    if (storageOk.value) error.value = ''
  } catch {
    if (!disposed) { observation.value = null; result.value = null; allowed.value = false; error.value = t('readError') }
  } finally { reading = false; if (!disposed && lock) busy.value = false }
}
async function send(value: boolean) {
  if (!canSend.value) return
  const request_id = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
  if (!save({ request_id, value })) return
  reviewed.value = false; result.value = null; busy.value = true
  try {
    const reply = await host.invoke('set_output', { value }, { idempotencyKey: request_id })
    if (!disposed) accept(reply, request_id)
  } catch { if (!disposed) error.value = t('unknown') }
  finally { if (!disposed) busy.value = false }
}
function clearReviewed() {
  if (!busy.value && reviewed.value && pending.value) {
    if (save(null)) { result.value = null; reviewed.value = false; error.value = '' }
  }
}
onMounted(() => {
  try {
    const raw = localStorage.getItem(storageKey)
    if (raw) {
      const value = JSON.parse(raw)
      if (!value || typeof value.request_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.request_id) || typeof value.value !== 'boolean') throw new Error('Invalid pending request')
      pending.value = { request_id: value.request_id, value: value.value }
    }
    const probe = storageKey + '.check'; localStorage.setItem(probe, '1'); localStorage.removeItem(probe)
  } catch { storageOk.value = false; error.value = t('storageError') }
  window.addEventListener('language-changed', updateLanguage)
  void refresh()
  timer = setInterval(() => { void refresh(true) }, 3000)
})
onUnmounted(() => { disposed = true; clearInterval(timer); window.removeEventListener('language-changed', updateLanguage) })
</script>

<style scoped>
.output-button { max-width: 52rem; margin: 0 auto; padding: 1.5rem; color: var(--ui-text); }
header { display: flex; align-items: start; justify-content: space-between; gap: 1rem; margin-bottom: 1.5rem; }
h1 { margin: 0; font-size: 1.75rem; } h2 { margin: 0 0 1rem; font-size: 1.15rem; }
p { line-height: 1.5; } header p { color: var(--ui-text-secondary); }
.panel { padding: 1.5rem; margin: 1rem 0; border: 1px solid var(--ui-border); border-radius: .8rem; background: var(--ui-surface); }
dl { display: grid; gap: .5rem; } dt { color: var(--ui-text-secondary); } dd { margin: 0 0 .5rem; }
code { overflow-wrap: anywhere; } .controls { display: flex; gap: .75rem; margin-top: 1.5rem; }
button { font: inherit; min-height: 44px; padding: .65rem 1rem; border: 1px solid var(--ui-border); border-radius: .5rem; color: var(--ui-text); background: var(--ui-surface-alt); cursor: pointer; }
button:disabled { opacity: .5; cursor: default; } button:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 3px; }
label { display: flex; align-items: start; gap: .6rem; margin: 1rem 0; line-height: 1.5; } input { min-width: 1.1rem; min-height: 1.1rem; }
.error { color: var(--ui-danger); } strong { color: var(--ui-success); }
@media (max-width: 520px) { .output-button { padding: 1rem; } header { flex-direction: column; } .controls { flex-direction: column; } .panel { padding: 1rem; } }
</style>
