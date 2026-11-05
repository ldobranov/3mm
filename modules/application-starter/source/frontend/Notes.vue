<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { UiButton, UiField, UiForm, UiSurface } from '@3mm/ui/v1'
import { ApplicationHostError, useApplicationHost, type ApplicationPayload } from '@3mm/application-ui/v1'
import { createApplicationClient } from './client.generated'

const host = useApplicationHost()
const client = createApplicationClient(host)
const labels = {
  en: { title: 'Starter note', intro: 'Application-owned data. The optional resource is observed, never operated.',
    note: 'Shared demonstration note', help: 'Up to 200 characters. Do not enter personal data in this example.',
    save: 'Save note', reload: 'Reload saved note (discard draft)', resource: 'Selected resource',
    ready: 'Reviewed resource is ready.', access_required: 'Select a device and approve resource access in administration.',
    unavailable: 'Provider is unavailable. Your note remains editable.', unknown: 'Resource status is not confirmed.',
    saved: 'Saved.', readError: 'Current note or permission is unavailable.',
    saveDenied: 'Save was refused: editing access is unavailable. The draft is retained. Reload current permissions and the saved note.',
    saveError: 'Save was not confirmed. The draft is retained. Reload the saved revision before another edit.',
    readOnly: 'Editing requires the note_write application permission.' },
  bg: { title: 'Примерна бележка', intro: 'Собствени данни на приложението. Ресурсът само се наблюдава, не се управлява.',
    note: 'Споделена демонстрационна бележка', help: 'До 200 знака. Не въвеждайте лични данни в този пример.',
    save: 'Запази бележката', reload: 'Зареди запазената бележка (отхвърли черновата)', resource: 'Избран ресурс',
    ready: 'Одобреният ресурс е готов.', access_required: 'Изберете устройство и одобрете достъпа до ресурса в администрацията.',
    unavailable: 'Доставчикът е недостъпен. Бележката остава достъпна за редактиране.', unknown: 'Статусът на ресурса не е потвърден.',
    saved: 'Запазено.', readError: 'Бележката или текущите права са недостъпни.',
    saveDenied: 'Записът е отказан: нямате текущ достъп за редактиране. Черновата е запазена. Заредете текущите права и запазената бележка.',
    saveError: 'Записът не е потвърден. Черновата е запазена. Заредете запазената ревизия преди ново редактиране.',
    readOnly: 'Редактирането изисква право note_write за приложението.' },
}
const locale = ref(host.presentation.getInfo().locale)
const unsubscribe = host.presentation.subscribe(info => { locale.value = info.locale })
const t = (key: keyof typeof labels.en) => labels[locale.value.startsWith('bg') ? 'bg' : 'en'][key]
const text = ref(''), revision = ref<number | null>(null), savedText = ref('')
const busy = ref(false), allowed = ref(false), uncertain = ref(false), error = ref(''), notice = ref('')
const resource = ref<'ready' | 'access_required' | 'unavailable' | 'unknown'>('unknown')
const canSave = computed(() => allowed.value && revision.value !== null && !busy.value && !uncertain.value
  && text.value !== savedText.value && text.value.length <= 200)
let disposed = false
function note(value: ApplicationPayload) {
  if (typeof value.text !== 'string' || value.text.length > 200 || typeof value.revision !== 'number'
      || !Number.isSafeInteger(value.revision) || value.revision < 0) throw new Error('Invalid note')
  text.value = savedText.value = value.text
  revision.value = value.revision
}
async function reload() {
  if (busy.value) return
  busy.value = true; allowed.value = false; notice.value = ''; error.value = ''
  try {
    const info = await host.getInfo()
    const value = await client.read_note({})
    if (disposed) return
    note(value); uncertain.value = false
    allowed.value = info.operations.some(item => item.operation_id === 'save_note')
    // Optional resource failure is independent of application-owned data.
    try {
      const observed = await client.observe_resource({})
      if (!disposed) resource.value = ['ready', 'access_required', 'unavailable'].includes(String(observed.state))
        ? observed.state as typeof resource.value : 'unknown'
    } catch { if (!disposed) resource.value = 'unknown' }
  } catch { if (!disposed) { error.value = t('readError'); revision.value = null; resource.value = 'unknown' } }
  finally { if (!disposed) busy.value = false }
}
async function save() {
  if (!canSave.value || revision.value === null) return
  const payload = { text: text.value, revision: revision.value }
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('')
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const value = await client.save_note(payload, { idempotencyKey: id })
    if (!disposed) { note(value); notice.value = t('saved') }
  } catch (failure) {
    if (!disposed) {
      if (failure instanceof ApplicationHostError && failure.code === 'access_denied') {
        allowed.value = false
        error.value = t('saveDenied')
      } else {
        uncertain.value = true
        error.value = t('saveError')
      }
    }
  }
  finally { if (!disposed) busy.value = false }
}
onMounted(() => { void reload() })
onUnmounted(() => { disposed = true; unsubscribe() })
</script>

<template>
  <UiSurface class="starter-note">
    <h1>{{ t('title') }}</h1><p>{{ t('intro') }}</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <UiForm :busy="busy" @submit="save">
      <UiField id="starter-note-text" v-model="text" type="textarea" :label="t('note')" :description="t('help')"
        :maxlength="200" :readonly="!allowed || uncertain" />
      <p v-if="!allowed && revision !== null">{{ t('readOnly') }}</p>
      <div class="actions"><UiButton type="submit" variant="primary" :disabled="!canSave">{{ t('save') }}</UiButton>
        <UiButton :disabled="busy" @click="reload">{{ t('reload') }}</UiButton></div>
    </UiForm>
    <section aria-live="polite"><h2>{{ t('resource') }}</h2><p>{{ t(resource) }}</p></section>
  </UiSurface>
</template>

<style scoped>
.starter-note { max-width: 46rem; margin: 0 auto; padding: 1.5rem; color: var(--ui-text); }
h1 { font-size: 1.7rem; margin-top: 0; } h2 { font-size: 1.15rem; }
p { line-height: 1.6; } section { border-top: 1px solid var(--ui-border); margin-top: 1.5rem; padding-top: 1rem; }
.actions { display: flex; flex-wrap: wrap; gap: .75rem; } [role=alert] { color: var(--ui-danger); }
@media (max-width: 520px) { .starter-note { padding: 1rem; } .actions { flex-direction: column; } }
</style>
