<template>
  <div class="translation-manager">
    <!-- Header -->
    <div class="manager-header">
      <h2>🌍 Translation Manager</h2>
      <div class="header-actions">
        <select v-model="selectedExtension" @change="loadTables">
          <option value="">All Extensions</option>
          <option v-for="ext in extensions" :key="ext.id" :value="ext.id">
            {{ ext.name }} ({{ ext.type }})
          </option>
        </select>
        <button @click="refreshData" :disabled="loading">
          🔄 Refresh
        </button>
      </div>
    </div>

    <!-- Language Selector -->
    <div class="language-section">
      <h3>Available Languages</h3>
      <div class="language-tabs">
        <button
          v-for="lang in availableLanguages"
          :key="lang"
          :class="{ active: selectedLanguage === lang }"
          @click="selectedLanguage = lang; loadTables()"
        >
          {{ lang }}
        </button>
        <button class="add-language" @click="showAddLanguage = true">
          ➕ Add Language
        </button>
      </div>
    </div>

    <!-- Tables Overview -->
    <div class="tables-section">
      <h3>Multilingual Tables</h3>
      <div class="tables-grid">
        <div
          v-for="table in multilingualTables"
          :key="table.table_name"
          class="table-card"
          :class="{ selected: selectedTable?.table_name === table.table_name }"
          @click="selectTable(table)"
        >
          <div class="table-header">
            <h4>{{ table.table_name }}</h4>
            <span class="table-badge">{{ table.translatable_fields.length }} fields</span>
          </div>
          <div class="table-info">
            <p><strong>Primary Key:</strong> {{ table.primary_key }}</p>
            <p><strong>Multilingual:</strong> {{ table.is_multilingual ? 'Yes' : 'No' }}</p>
            <p><strong>Translatable Fields:</strong> {{ table.translatable_fields.join(', ') }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Translation Editor -->
    <div v-if="selectedTable" class="translation-editor">
      <div class="editor-header">
        <h3>Edit Translations: {{ selectedTable.table_name }}</h3>
        <div class="editor-actions">
          <span class="language-indicator">Editing: {{ selectedLanguage }}</span>
          <button @click="saveTranslations" :disabled="!hasUnsavedChanges || saving">
            💾 {{ saving ? 'Saving...' : 'Save All' }}
          </button>
        </div>
      </div>

      <!-- Content Table -->
      <div class="content-table">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th v-for="field in selectedTable.translatable_fields" :key="field">
                {{ field }}
                <span class="field-type">(translatable)</span>
              </th>
              <th>Coverage</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in tableRecords" :key="record.id">
              <td class="record-id">{{ record.id }}</td>
              <td v-for="field in selectedTable.translatable_fields" :key="field">
                <div class="translation-cell">
                  <!-- Original text (readonly) -->
                  <div class="original-text">{{ record[field] || '—' }}</div>
                  
                  <!-- Translation input -->
                  <input
                    v-model="record.translations[field]"
                    :placeholder="record[field] || 'Enter translation...'"
                    class="translation-input"
                    @input="markRecordChanged(record.id)"
                  />
                </div>
              </td>
              <td>
                <div class="coverage-badge" :class="getCoverageClass(record.coverage)">
                  {{ record.coverage }}%
                </div>
              </td>
              <td>
                <button
                  @click="saveSingleRecord(record)"
                  :disabled="!record.changed || saving"
                  class="save-btn"
                >
                  💾
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Coverage Overview -->
    <div v-if="selectedTable" class="coverage-section">
      <h3>Translation Coverage</h3>
      <div class="coverage-stats">
        <div
          v-for="(stats, lang) in translationCoverage"
          :key="lang"
          class="coverage-card"
        >
          <h4>{{ lang }}</h4>
          <div class="coverage-bar">
            <div
              class="coverage-fill"
              :style="{ width: stats.average_coverage + '%' }"
              :class="getCoverageClass(stats.average_coverage)"
            ></div>
          </div>
          <p>{{ stats.records_translated }} records translated</p>
        </div>
      </div>
    </div>

    <!-- Add Language Modal -->
    <div v-if="showAddLanguage" class="modal-overlay" @click="showAddLanguage = false">
      <div class="modal" @click.stop>
        <h3>Add New Language</h3>
        <form @submit.prevent="addLanguage">
          <div class="form-group">
            <label>Language Code (e.g., en, bg, es):</label>
            <input v-model="newLanguage.code" placeholder="Language code" required />
          </div>
          <div class="form-group">
            <label>Language Name:</label>
            <input v-model="newLanguage.name" placeholder="English" required />
          </div>
          <div class="form-group">
            <label>Native Name:</label>
            <input v-model="newLanguage.nativeName" placeholder="English" required />
          </div>
          <div class="modal-actions">
            <button type="button" @click="showAddLanguage = false">Cancel</button>
            <button type="submit">Add Language</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p>Loading translation data...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import http from '@/utils/dynamic-http'

interface Extension {
  id: number
  name: string
  type: string
}

interface TableInfo {
  table_name: string
  translatable_fields: string[]
  is_multilingual: boolean
  primary_key: string
  schema: any
}

interface TableRecord {
  id: number
  [key: string]: any
  translations: Record<string, string>
  coverage: number
  changed?: boolean
}

const extensions = ref<Extension[]>([])
const selectedExtension = ref('')
const availableLanguages = ref<string[]>(['en', 'bg', 'es', 'fr'])
const selectedLanguage = ref('en')
const multilingualTables = ref<TableInfo[]>([])
const selectedTable = ref<TableInfo | null>(null)
const tableRecords = ref<TableRecord[]>([])
const translationCoverage = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)
const showAddLanguage = ref(false)
const hasUnsavedChanges = ref(false)

const newLanguage = reactive({
  code: '',
  name: '',
  nativeName: ''
})

// Computed properties
const extensionsWithTables = computed(() => {
  if (!selectedExtension.value) return extensions.value
  return extensions.value.filter(ext => ext.id.toString() === selectedExtension.value)
})

// Methods
const refreshData = async () => {
  await loadExtensions()
  await loadLanguages()
  if (selectedExtension.value || multilingualTables.value.length > 0) {
    await loadTables()
  }
}

const loadExtensions = async () => {
  try {
    loading.value = true
    const response = await http.get('/api/extensions')
    extensions.value = response.data
  } catch (error) {
    console.error('Failed to load extensions:', error)
  } finally {
    loading.value = false
  }
}

const loadLanguages = async () => {
  try {
    const response = await http.get('/api/translations/languages')
    if (response.data.languages) {
      availableLanguages.value = response.data.languages
    }
  } catch (error) {
    console.error('Failed to load languages:', error)
  }
}

const loadTables = async () => {
  if (!selectedExtension.value) return
  
  try {
    loading.value = true
    const response = await http.get(`/api/translations/extensions/${selectedExtension.value}/tables?multilingual_only=true`)
    multilingualTables.value = response.data.tables || []
    
    if (multilingualTables.value.length > 0 && !selectedTable.value) {
      selectTable(multilingualTables.value[0])
    }
  } catch (error) {
    console.error('Failed to load tables:', error)
  } finally {
    loading.value = false
  }
}

const selectTable = async (table: TableInfo) => {
  selectedTable.value = table
  await loadTableRecords()
  await loadTranslationCoverage()
}

const loadTableRecords = async () => {
  if (!selectedTable.value || !selectedExtension.value) return
  
  try {
    loading.value = true
    // This would need a new API endpoint to get table records
    // For now, simulate the data
    tableRecords.value = [
      {
        id: 1,
        name: 'Home',
        description: 'Home page',
        translations: {},
        coverage: 0
      },
      {
        id: 2,
        name: 'Dashboard', 
        description: 'Main dashboard',
        translations: {},
        coverage: 0
      }
    ]
  } catch (error) {
    console.error('Failed to load table records:', error)
  } finally {
    loading.value = false
  }
}

const loadTranslationCoverage = async () => {
  if (!selectedTable.value || !selectedExtension.value) return
  
  try {
    const response = await http.get(`/api/translations/extensions/${selectedExtension.value}/tables/${selectedTable.value.table_name}/translations/coverage`)
    translationCoverage.value = response.data.languages || {}
  } catch (error) {
    console.error('Failed to load translation coverage:', error)
  }
}

const markRecordChanged = (recordId: number) => {
  const record = tableRecords.value.find(r => r.id === recordId)
  if (record) {
    record.changed = true
    hasUnsavedChanges.value = true
  }
}

const saveTranslations = async () => {
  if (!selectedTable.value || !selectedExtension.value) return
  
  try {
    saving.value = true
    
    const changedRecords = tableRecords.value.filter(r => r.changed)
    
    for (const record of changedRecords) {
      await saveSingleRecord(record)
    }
    
    hasUnsavedChanges.value = false
    await loadTranslationCoverage()
    
  } catch (error) {
    console.error('Failed to save translations:', error)
  } finally {
    saving.value = false
  }
}

const saveSingleRecord = async (record: TableRecord) => {
  if (!selectedTable.value || !selectedExtension.value) return
  
  try {
    const translations = record.translations
    
    await http.put(
      `/api/translations/extensions/${selectedExtension.value}/tables/${selectedTable.value.table_name}/records/${record.id}/translations/${selectedLanguage.value}`,
      translations
    )
    
    record.changed = false
    
    // Update coverage
    const totalFields = selectedTable.value.translatable_fields.length
    const translatedFields = Object.keys(translations).length
    record.coverage = Math.round((translatedFields / totalFields) * 100)
    
  } catch (error) {
    console.error('Failed to save record translations:', error)
    throw error
  }
}

const addLanguage = async () => {
  // This would create a new language pack
  try {
    // Simulate adding language
    availableLanguages.value.push(newLanguage.code)
    selectedLanguage.value = newLanguage.code
    
    showAddLanguage.value = false
    newLanguage.code = ''
    newLanguage.name = ''
    newLanguage.nativeName = ''
    
  } catch (error) {
    console.error('Failed to add language:', error)
  }
}

const getCoverageClass = (coverage: number) => {
  if (coverage >= 90) return 'excellent'
  if (coverage >= 70) return 'good'
  if (coverage >= 50) return 'partial'
  return 'poor'
}

// Initialize data
onMounted(() => {
  refreshData()
})
</script>

<style scoped>
.translation-manager {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  padding-bottom: 20px;
  border-bottom: 2px solid #e0e0e0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.language-section {
  margin-bottom: 30px;
}

.language-tabs {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.language-tabs button {
  padding: 8px 16px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.language-tabs button.active {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.language-tabs button.add-language {
  background: #28a745;
  color: white;
  border-color: #28a745;
}

.tables-section {
  margin-bottom: 30px;
}

.tables-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.table-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
}

.table-card:hover {
  border-color: #007bff;
  box-shadow: 0 2px 8px rgba(0,123,255,0.1);
}

.table-card.selected {
  border-color: #007bff;
  background: #f8f9ff;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.table-badge {
  background: #007bff;
  color: white;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.translation-editor {
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  background: white;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #ddd;
}

.editor-actions {
  display: flex;
  gap: 15px;
  align-items: center;
}

.language-indicator {
  color: #666;
  font-weight: 500;
}

.content-table {
  overflow-x: auto;
}

.content-table table {
  width: 100%;
  border-collapse: collapse;
}

.content-table th,
.content-table td {
  padding: 15px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.content-table th {
  background: #f8f9fa;
  font-weight: 600;
}

.field-type {
  font-size: 12px;
  color: #666;
  font-weight: normal;
}

.translation-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.original-text {
  font-size: 12px;
  color: #666;
  font-style: italic;
}

.translation-input {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.translation-input:focus {
  border-color: #007bff;
  outline: none;
}

.record-id {
  font-weight: 600;
  color: #007bff;
}

.coverage-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}

.coverage-badge.excellent {
  background: #d4edda;
  color: #155724;
}

.coverage-badge.good {
  background: #cce5ff;
  color: #004085;
}

.coverage-badge.partial {
  background: #fff3cd;
  color: #856404;
}

.coverage-badge.poor {
  background: #f8d7da;
  color: #721c24;
}

.save-btn {
  padding: 6px 12px;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.save-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.coverage-section {
  margin-top: 30px;
}

.coverage-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
}

.coverage-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  background: white;
}

.coverage-bar {
  height: 20px;
  background: #e9ecef;
  border-radius: 10px;
  overflow: hidden;
  margin: 10px 0;
}

.coverage-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.coverage-fill.excellent {
  background: #28a745;
}

.coverage-fill.good {
  background: #17a2b8;
}

.coverage-fill.partial {
  background: #ffc107;
}

.coverage-fill.poor {
  background: #dc3545;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 8px;
  padding: 30px;
  max-width: 400px;
  width: 90%;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
  font-weight: 600;
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 30px;
}

.modal-actions button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.modal-actions button[type="button"] {
  background: #6c757d;
  color: white;
}

.modal-actions button[type="submit"] {
  background: #007bff;
  color: white;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 999;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #007bff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>