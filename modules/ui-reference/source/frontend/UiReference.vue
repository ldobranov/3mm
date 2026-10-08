<script setup>
import { computed, ref } from 'vue'
import { UiSurface, UiButton, UiDialog, UI_CONTRACT_VERSION } from '@3mm/ui/v1'

// This reference deliberately has no API client, business operations or Core imports.
const language = ref('en')
const name = ref('')
const enabled = ref(true)
const open = ref(false)
const saved = ref('')
const attempted = ref(false)
const invalid = computed(() => attempted.value && !name.value.trim())
const copy = {
  en: { title: 'Extension UI reference', note: 'Public UI contract · local demonstration only. Nothing is saved to the installation.', language: 'Example language', form: 'Shared form controls', name: 'Name', placeholder: 'A clear, descriptive name', error: 'Enter a name.', enabled: 'Include this example', preview: 'Preview local draft', disabled: 'Unavailable', table: 'Shared status and table', item: 'Item', status: 'Status', ready: 'Ready', waiting: 'Waiting for confirmation', dialog: 'Review local draft', close: 'Close', cancel: 'Cancel', confirm: 'Confirm locally', result: 'Local preview confirmed' },
  bg: { title: 'Примерен интерфейс на разширение', note: 'Публичен UI договор · само локална демонстрация. Нищо не се записва в инсталацията.', language: 'Език на примера', form: 'Общи контроли на формата', name: 'Име', placeholder: 'Ясно и описателно име', error: 'Въведете име.', enabled: 'Включи този пример', preview: 'Преглед на локалната чернова', disabled: 'Недостъпно', table: 'Общи статуси и таблица', item: 'Елемент', status: 'Статус', ready: 'Готово', waiting: 'Очаква потвърждение', dialog: 'Преглед на локалната чернова', close: 'Затвори', cancel: 'Отказ', confirm: 'Потвърди локално', result: 'Локалният преглед е потвърден' },
}
const text = computed(() => copy[language.value])
function preview() {
  attempted.value = true
  if (name.value.trim()) open.value = true
}
function confirm() {
  saved.value = name.value.trim()
  open.value = false
}
</script>

<template>
  <UiSurface class="reference-ui ui-stack">
    <div class="ui-stack">
      <h1>{{ text.title }}</h1>
      <p class="ui-muted">{{ text.note }} (v{{ UI_CONTRACT_VERSION }})</p>
      <label class="ui-field reference-language"><span>{{ text.language }}</span>
        <select v-model="language" class="ui-control"><option value="en">English</option><option value="bg">Български</option></select>
      </label>
    </div>
    <div class="reference-columns">
      <section class="ui-section ui-stack">
        <h2>{{ text.form }}</h2>
        <form class="ui-stack" @submit.prevent="preview" novalidate>
          <label class="ui-field"><span>{{ text.name }}</span>
            <input v-model="name" class="ui-control" :placeholder="text.placeholder" :aria-invalid="invalid || undefined"
              :aria-describedby="invalid ? 'reference-name-error' : undefined" required />
          </label>
          <p v-if="invalid" id="reference-name-error" class="ui-error" role="alert">{{ text.error }}</p>
          <label class="ui-check"><input v-model="enabled" type="checkbox" />{{ text.enabled }}</label>
          <div class="ui-row">
            <UiButton type="submit" variant="primary">{{ text.preview }}</UiButton>
            <UiButton disabled>{{ text.disabled }}</UiButton>
          </div>
          <p v-if="saved" role="status">{{ text.result }}: {{ saved }}</p>
        </form>
      </section>
      <section class="ui-section ui-stack">
        <h2>{{ text.table }}</h2>
        <div class="ui-table-wrap">
          <table class="ui-table"><caption class="ui-help">{{ text.table }}</caption>
            <thead><tr><th scope="col">{{ text.item }}</th><th scope="col">{{ text.status }}</th></tr></thead>
            <tbody><tr><td>Reference A</td><td><span class="ui-badge ui-badge--success">✓ {{ text.ready }}</span></td></tr>
              <tr><td>Reference B</td><td><span class="ui-badge ui-badge--warning">◷ {{ text.waiting }}</span></td></tr></tbody>
          </table>
        </div>
      </section>
    </div>
    <UiDialog v-model:open="open" :title="text.dialog" :close-label="text.close">
      <p>{{ name }}</p>
      <template #actions>
        <UiButton autofocus @click="open = false">{{ text.cancel }}</UiButton>
        <UiButton variant="primary" @click="confirm">{{ text.confirm }}</UiButton>
      </template>
    </UiDialog>
  </UiSurface>
</template>

<style scoped>
.reference-ui { text-align: left; overflow-wrap: anywhere; }
.reference-language { max-width: 240px; }
.reference-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 4); }
@media (max-width: 760px) { .reference-columns { grid-template-columns: minmax(0, 1fr); } }
</style>
