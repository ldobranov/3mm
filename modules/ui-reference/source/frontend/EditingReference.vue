<script setup>
import { computed, ref, useId } from 'vue'
import { UiButton, UiCollectionEditor, UiEditorForm, UiField, UiRecordPicker } from '@3mm/ui/v1'

// Two ordinary editing patterns, with in-memory drafts only. No platform/business operations.
const props = defineProps({ locale: { type: String, default: 'en' } })
const prefix = useId()
let serial = 2
const copy = {
  en: { title: 'Shared editing workspace', note: 'Search and choose records, then arrange panels. Save changes only this local example.', records: 'Available records', selected: 'Selected records', search: 'Search by name', toggle: 'Show records', remove: 'Remove', empty: 'No matching records', unavailable: 'Unavailable record', collection: 'Ordered panels', panel: 'Panel', name: 'Panel title', add: 'Add panel', up: 'Move up', down: 'Move down', noItems: 'No panels', invalidKeys: 'Panel keys must be unique.', save: 'Save local draft', cancel: 'Discard local draft', dirty: 'Unsaved changes', saved: 'Local draft matches the saved example', unconfirmed: 'Example outcome is unconfirmed. Read the original result before another change.', conflict: 'Example record changed. Resolve the draft before saving.', state: 'Demonstrate editor state', idle: 'Editable', uncertain: 'Unconfirmed', changed: 'Conflict', resolve: 'Resolve example state', preview: 'Draft panel preview', one: 'First panel', two: 'Second panel', alpha: 'Article alpha', beta: 'Article beta', gamma: 'Unavailable article', invalid: 'Enter a title for every panel.' },
  bg: { title: 'Обща работна област за редактиране', note: 'Потърси и избери записи, след което подреди панелите. Записът променя само този локален пример.', records: 'Налични записи', selected: 'Избрани записи', search: 'Търсене по име', toggle: 'Покажи записите', remove: 'Премахни', empty: 'Няма съвпадащи записи', unavailable: 'Недостъпен запис', collection: 'Подредени панели', panel: 'Панел', name: 'Заглавие на панела', add: 'Добави панел', up: 'Премести нагоре', down: 'Премести надолу', noItems: 'Няма панели', invalidKeys: 'Ключовете на панелите трябва да са уникални.', save: 'Запази локалната чернова', cancel: 'Отхвърли локалната чернова', dirty: 'Незапазени промени', saved: 'Черновата съвпада със запазения локален пример', unconfirmed: 'Резултатът в примера е непотвърден. Прочети първоначалния резултат преди нова промяна.', conflict: 'Записът в примера е променен. Разреши конфликта преди запис.', state: 'Пробвай състояние на редактора', idle: 'Редактиране', uncertain: 'Непотвърден резултат', changed: 'Конфликт', resolve: 'Разреши състоянието в примера', preview: 'Преглед на черновата', one: 'Първи панел', two: 'Втори панел', alpha: 'Артикул алфа', beta: 'Артикул бета', gamma: 'Недостъпен артикул', invalid: 'Въведи заглавие за всеки панел.' },
}
const t = computed(() => copy[props.locale.toLowerCase().startsWith('bg') ? 'bg' : 'en'])
const options = computed(() => [
  { id: 'alpha', label: t.value.alpha }, { id: 'beta', label: t.value.beta },
  { id: 'gamma', label: t.value.gamma, disabled: true },
])
const draft = ref({ records: ['alpha'], panels: [{ id: 'panel-1', name: 'Panel A' }, { id: 'panel-2', name: 'Panel B' }] })
const saved = ref(JSON.stringify(draft.value))
const state = ref('idle')
const search = ref('')
const dirty = computed(() => JSON.stringify(draft.value) !== saved.value)
const valid = computed(() => draft.value.panels.every(panel => panel.name.trim().length > 0))
function save() { saved.value = JSON.stringify(draft.value) }
function cancel() { draft.value = JSON.parse(saved.value) }
function add() { draft.value.panels = [...draft.value.panels, { id: `panel-${++serial}`, name: `${t.value.panel} ${serial}` }] }
</script>

<template>
  <section class="ui-section ui-stack">
    <div class="ui-row" role="group" :aria-label="t.state">
      <UiButton v-for="choice in ['idle', 'unconfirmed', 'conflict']" :key="choice" :aria-pressed="state === choice" @click="state = choice">{{ choice === 'idle' ? t.idle : choice === 'unconfirmed' ? t.uncertain : t.changed }}</UiButton>
    </div>
    <UiEditorForm :title="t.title" :description="t.note" :dirty="dirty" :valid="valid" :state="state"
      :save-label="t.save" :cancel-label="t.cancel" :dirty-label="t.dirty" :saved-label="t.saved"
      :unconfirmed-label="t.unconfirmed" :conflict-label="t.conflict" @save="save" @cancel="cancel">
      <template #default="{ disabled }">
        <UiRecordPicker :id="`${prefix}-records`" v-model="draft.records" v-model:search="search" :label="t.records"
          :options="options" :selected-options="options" multiple :disabled="disabled" :placeholder="t.search"
          :selected-label="t.selected" :toggle-label="t.toggle" :empty-label="t.empty" :remove-label="t.remove" :unavailable-label="t.unavailable" />
        <UiCollectionEditor v-model="draft.panels" :title="t.collection" :item-key="item => item.id" :item-label="item => item.name"
          :disabled="disabled" :min-items="1" :max-items="8" :add-label="t.add" :remove-label="t.remove"
          :move-up-label="t.up" :move-down-label="t.down" :empty-label="t.noItems" :invalid-keys-label="t.invalidKeys" @add="add">
          <template #default="{ item, disabled: itemDisabled }">
            <UiField :id="`${prefix}-${item.id}`" v-model="item.name" :label="t.name" required :disabled="itemDisabled" :error="!item.name.trim() ? t.invalid : undefined" />
          </template>
        </UiCollectionEditor>
        <aside class="ui-section ui-stack" :aria-label="t.preview"><h3>{{ t.preview }}</h3><p v-for="panel in draft.panels" :key="panel.id">{{ panel.name }}</p></aside>
      </template>
      <template #recovery><UiButton @click="state = 'idle'">{{ t.resolve }}</UiButton></template>
    </UiEditorForm>
  </section>
</template>
