<template>
  <main class="view runtime-view">
    <div v-if="loading" class="runtime-state">{{ t('runtime.loading', 'Loading extension…') }}</div>
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>

    <template v-else-if="definition && page && entity">
      <div class="view-header runtime-header">
        <div>
          <p class="runtime-eyebrow">{{ localize(definition.name) }}</p>
          <h1 class="view-title">{{ localize(page.title) }}</h1>
          <p class="runtime-description">{{ localize(definition.description) }}</p>
        </div>
        <button v-if="can('create') && page.view !== 'form'" class="button button-primary" @click="startCreate">
          <i class="bi bi-plus-lg" aria-hidden="true"></i>
          {{ t('runtime.new', 'New') }} {{ localize(entity.label) }}
        </button>
      </div>

      <div v-if="success" class="alert alert-success">{{ success }}</div>

      <section v-if="showForm || page.view === 'form'" class="card runtime-form-card">
        <div class="runtime-section-header">
          <h2>{{ editingRecordId ? t('runtime.edit', 'Edit') : t('runtime.create', 'Create') }} {{ localize(entity.label) }}</h2>
          <button v-if="page.view !== 'form'" class="button button-secondary" type="button" @click="closeForm">{{ t('runtime.cancel', 'Cancel') }}</button>
        </div>
        <form class="runtime-form" @submit.prevent="saveRecord">
          <label v-for="field in editableFields" :key="field.field_id" class="runtime-field">
            <span>{{ localize(field.label) }}<b v-if="field.required" aria-hidden="true"> *</b></span>
            <textarea
              v-if="field.kind === 'multiline'"
              v-model="formData[field.field_id]"
              class="textarea"
              rows="4"
              :required="field.required"
            ></textarea>
            <input
              v-else-if="field.kind === 'boolean'"
              type="checkbox"
              :checked="Boolean(formData[field.field_id])"
              @change="formData[field.field_id] = ($event.target as HTMLInputElement).checked"
            />
            <input
              v-else
              v-model="formData[field.field_id]"
              class="input"
              :type="inputType(field.kind)"
              :step="field.kind === 'number' ? 'any' : undefined"
              :required="field.required"
            />
          </label>
          <div class="runtime-form-actions">
            <button class="button button-primary" type="submit" :disabled="saving">
              {{ saving ? t('runtime.saving', 'Saving…') : t('runtime.save', 'Save') }}
            </button>
          </div>
        </form>
      </section>

      <section v-if="page.view === 'table'" class="card runtime-table-card">
        <div v-if="records.length === 0" class="runtime-state">{{ t('runtime.empty', 'No records yet.') }}</div>
        <div v-else class="runtime-table-wrap">
          <table class="runtime-table">
            <thead><tr><th v-for="field in entity.fields" :key="field.field_id">{{ localize(field.label) }}</th><th v-if="can('update') || can('delete')">{{ t('runtime.actions', 'Actions') }}</th></tr></thead>
            <tbody>
              <tr v-for="record in records" :key="record.record_id">
                <td v-for="field in entity.fields" :key="field.field_id">{{ formatValue(record.data[field.field_id], field.kind) }}</td>
                <td v-if="can('update') || can('delete')" class="runtime-row-actions">
                  <button v-if="can('update')" class="button button-secondary button-sm" @click="startEdit(record)">{{ t('runtime.edit', 'Edit') }}</button>
                  <button v-if="can('delete')" class="button button-danger button-sm" @click="removeRecord(record)">{{ t('runtime.delete', 'Delete') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-else-if="page.view === 'detail'" class="runtime-detail-grid">
        <article v-for="record in records" :key="record.record_id" class="card runtime-detail-card">
          <dl>
            <template v-for="field in entity.fields" :key="field.field_id">
              <dt>{{ localize(field.label) }}</dt>
              <dd>{{ formatValue(record.data[field.field_id], field.kind) }}</dd>
            </template>
          </dl>
          <div class="runtime-row-actions">
            <button v-if="can('update')" class="button button-secondary button-sm" @click="startEdit(record)">{{ t('runtime.edit', 'Edit') }}</button>
            <button v-if="can('delete')" class="button button-danger button-sm" @click="removeRecord(record)">{{ t('runtime.delete', 'Delete') }}</button>
          </div>
        </article>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import {
  localizedText,
  type RuntimeDefinitionResponse,
  type RuntimeEntity,
  type RuntimeField,
  type RuntimePage,
  type RuntimeRecord,
} from '@/utils/runtime-extensions'

const props = defineProps<{ moduleId: string; pageId: string }>()
const { currentLanguage, t } = useI18n()
const definitionResponse = ref<RuntimeDefinitionResponse | null>(null)
const records = ref<RuntimeRecord[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const showForm = ref(false)
const editingRecordId = ref<string | null>(null)
const formData = ref<Record<string, any>>({})

const definition = computed(() => definitionResponse.value?.definition || null)
const page = computed<RuntimePage | null>(() => definition.value?.pages.find(item => item.page_id === props.pageId) || null)
const entity = computed<RuntimeEntity | null>(() => definition.value?.entities.find(item => item.entity_id === page.value?.entity_id) || null)
const editableFields = computed(() => entity.value?.fields.filter(field => !field.read_only) || [])
const recordsUrl = computed(() => `/api/v1/runtime-extensions/${props.moduleId}/entities/${page.value?.entity_id}/records`)

const localize = (text: { en: string; translations?: Record<string, string> }) => localizedText(text, currentLanguage.value)
const can = (action: RuntimePage['actions'][number]) => page.value?.actions.includes(action) === true

function inputType(kind: RuntimeField['kind']): string {
  return ({ integer: 'number', number: 'number', date: 'date', datetime: 'datetime-local' } as Record<string, string>)[kind] || 'text'
}

function formatValue(value: unknown, kind: RuntimeField['kind']): string {
  if (value === null || value === undefined || value === '') return '—'
  if (kind === 'boolean') return value ? t('runtime.yes', 'Yes') : t('runtime.no', 'No')
  return String(value)
}

function normalizedPayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of editableFields.value) {
    const value = formData.value[field.field_id]
    if (value === '' && !field.required) continue
    if (field.kind === 'integer' && value !== '') payload[field.field_id] = Number.parseInt(String(value), 10)
    else if (field.kind === 'number' && value !== '') payload[field.field_id] = Number(value)
    else payload[field.field_id] = value
  }
  return payload
}

function emptyForm(): Record<string, unknown> {
  return Object.fromEntries(editableFields.value.map(field => [field.field_id, field.kind === 'boolean' ? false : '']))
}

function startCreate() {
  editingRecordId.value = null
  formData.value = emptyForm()
  showForm.value = true
}

function startEdit(record: RuntimeRecord) {
  editingRecordId.value = record.record_id
  formData.value = { ...emptyForm(), ...record.data }
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingRecordId.value = null
  formData.value = emptyForm()
}

function errorMessage(reason: unknown): string {
  const response = (reason as any)?.response?.data
  return response?.detail || response?.error || (reason instanceof Error ? reason.message : t('runtime.requestFailed', 'Runtime extension request failed'))
}

async function loadRecords() {
  if (!page.value || !can('read')) {
    records.value = []
    return
  }
  const response = await http.get(recordsUrl.value)
  records.value = Array.isArray(response.data) ? response.data : []
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await http.get(`/api/v1/runtime-extensions/${props.moduleId}/definition`)
    definitionResponse.value = response.data
    if (!page.value || !entity.value) throw new Error(t('runtime.invalidDefinition', 'Runtime page definition is incomplete'))
    if (page.value.view === 'form') startCreate()
    await loadRecords()
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function saveRecord() {
  if (!page.value) return
  saving.value = true
  error.value = ''
  try {
    const payload = normalizedPayload()
    if (editingRecordId.value) await http.patch(`${recordsUrl.value}/${editingRecordId.value}`, payload)
    else await http.post(recordsUrl.value, payload)
    success.value = editingRecordId.value
      ? t('runtime.updated', 'Record updated.')
      : t('runtime.created', 'Record created.')
    closeForm()
    if (page.value.view === 'form') startCreate()
    await loadRecords()
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function removeRecord(record: RuntimeRecord) {
  if (!window.confirm(t('runtime.confirmDelete', 'Delete this record?'))) return
  error.value = ''
  try {
    await http.delete(`${recordsUrl.value}/${record.record_id}`)
    success.value = t('runtime.deleted', 'Record deleted.')
    await loadRecords()
  } catch (reason) {
    error.value = errorMessage(reason)
  }
}

onMounted(load)
watch(() => [props.moduleId, props.pageId], load)
</script>

<style scoped>
.runtime-view { display: grid; gap: 1rem; }
.runtime-header { margin-bottom: 0; }
.runtime-eyebrow { margin: 0 0 .35rem; color: var(--text-muted); font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.runtime-description { margin: .45rem 0 0; color: var(--text-secondary); }
.runtime-state { padding: 2.5rem 1rem; text-align: center; color: var(--text-secondary); }
.runtime-form-card, .runtime-table-card, .runtime-detail-card { padding: 1.25rem; }
.runtime-section-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.runtime-section-header h2 { margin: 0; font-size: 1.1rem; }
.runtime-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.runtime-field { display: grid; gap: .4rem; color: var(--text-primary); font-size: .85rem; font-weight: 600; }
.runtime-field:has(textarea), .runtime-form-actions { grid-column: 1 / -1; }
.runtime-form-actions { display: flex; justify-content: flex-end; }
.runtime-table-wrap { overflow-x: auto; }
.runtime-table { width: 100%; border-collapse: collapse; color: var(--text-primary); }
.runtime-table th, .runtime-table td { padding: .75rem; border-bottom: 1px solid var(--card-border); text-align: left; vertical-align: middle; }
.runtime-table th { color: var(--text-secondary); font-size: .75rem; letter-spacing: .04em; text-transform: uppercase; }
.runtime-row-actions { display: flex; gap: .45rem; justify-content: flex-end; }
.runtime-detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
.runtime-detail-card dl { display: grid; grid-template-columns: minmax(90px, .6fr) 1fr; gap: .5rem 1rem; margin: 0 0 1rem; }
.runtime-detail-card dt { color: var(--text-secondary); }
.runtime-detail-card dd { margin: 0; overflow-wrap: anywhere; }
@media (max-width: 700px) {
  .runtime-form { grid-template-columns: 1fr; }
  .runtime-row-actions { justify-content: flex-start; }
}
</style>
