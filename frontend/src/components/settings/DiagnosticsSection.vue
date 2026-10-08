<template>
  <SettingsSection :title="t('diagnostics.title', 'Support diagnostics')">
    <p class="section-intro">
      {{ t('diagnostics.description', 'Review safe device checks and download a redacted JSON bundle for troubleshooting.') }}
    </p>

    <div v-if="errorMessage" class="diagnostic-notice error" role="alert">{{ errorMessage }}</div>

    <div class="diagnostic-summary">
      <div class="summary-icon" aria-hidden="true"><i class="bi bi-file-earmark-medical"></i></div>
      <div class="summary-copy">
        <strong>{{ t('diagnostics.safeTitle', 'Safe by design') }}</strong>
        <span>{{ t('diagnostics.safeHelp', 'The bundle contains system metadata and health results, never passwords, keys, tokens, Wi-Fi profiles, database content or logs.') }}</span>
      </div>
      <button type="button" class="ui-button ui-button--primary" :disabled="downloading || loading" @click="downloadBundle">
        <i class="bi bi-download" aria-hidden="true"></i>
        {{ downloading ? t('diagnostics.downloading', 'Preparing…') : t('diagnostics.download', 'Download diagnostics') }}
      </button>
    </div>

    <div v-if="loading" class="loading-row" role="status">{{ t('diagnostics.loading', 'Checking device…') }}</div>
    <template v-else-if="preview">
      <div class="diagnostic-meta">
        <span>{{ preview.check_count }} {{ t('diagnostics.checks', 'checks') }}</span>
        <span>{{ preview.warning_count }} {{ t('diagnostics.warnings', 'warnings') }}</span>
        <span>{{ formatBytes(preview.estimated_size_bytes) }}</span>
      </div>
      <div class="check-list">
        <article v-for="check in preview.checks" :key="check.name" class="check-row">
          <span class="check-state ui-badge" :class="'check-state--' + check.status">{{ t('diagnostics.status.' + check.status, { ok: 'Ready', warning: 'Warning', error: 'Error' }[check.status]) }}</span>
          <div><strong>{{ check.name }}</strong><small>{{ check.summary }}</small></div>
        </article>
      </div>
    </template>
  </SettingsSection>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'

type DiagnosticCheck = { name: string; status: 'ok' | 'warning' | 'error'; summary: string }
type DiagnosticPreview = {
  estimated_size_bytes: number
  check_count: number
  warning_count: number
  checks: DiagnosticCheck[]
}

const { t } = useI18n()
const preview = ref<DiagnosticPreview | null>(null)
const loading = ref(false)
const downloading = ref(false)
const errorMessage = ref('')

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(1)} KB`
}

function detail(error: any) {
  return error?.response?.data?.detail || t('diagnostics.failed', 'Diagnostics could not be prepared.')
}

async function loadPreview() {
  loading.value = true
  errorMessage.value = ''
  try {
    preview.value = (await http.get('/api/v1/diagnostics/preview')).data
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    loading.value = false
  }
}

async function downloadBundle() {
  downloading.value = true
  errorMessage.value = ''
  try {
    const response = await http.get('/api/v1/diagnostics/bundle', { responseType: 'blob' })
    const disposition = response.headers?.['content-disposition'] || ''
    const match = disposition.match(/filename="?([^";]+)"?/i)
    const filename = match?.[1] || '3mm-diagnostics.json'
    const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    downloading.value = false
  }
}

onMounted(loadPreview)
</script>

<style scoped>
.section-intro { margin-bottom: calc(var(--ui-space) * 4); color: var(--ui-text-secondary); }
.diagnostic-summary { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-alt); }
.summary-icon { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: var(--ui-radius-sm); color: var(--ui-accent); background: var(--ui-surface); }
.summary-copy strong, .summary-copy span, .check-row small { display: block; }
.summary-copy span, .check-row small { color: var(--ui-text-secondary); }
.summary-copy, .check-row > div { min-width: 0; overflow-wrap: anywhere; }
.diagnostic-meta { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); margin: calc(var(--ui-space) * 4) 0; color: var(--ui-text-secondary); font-size: .9em; }
.diagnostic-meta span { padding: calc(var(--ui-space) * 2); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.check-list { display: grid; gap: calc(var(--ui-space) * 2); }
.check-row { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.check-state { flex-shrink: 0; }
.ui-v2 .check-state.check-state--ok { color: var(--ui-success); }
.ui-v2 .check-state.check-state--warning { color: var(--ui-warning); }
.ui-v2 .check-state.check-state--error { color: var(--ui-danger); }
.loading-row { padding: calc(var(--ui-space) * 4) 0; color: var(--ui-text-secondary); }
.diagnostic-notice { margin-bottom: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; }
.diagnostic-notice.error { color: var(--ui-danger); }
@media (max-width: 720px) {
  .diagnostic-summary { grid-template-columns: auto minmax(0, 1fr); }
  .diagnostic-summary .ui-button { grid-column: 1 / -1; width: 100%; }
  .check-row { flex-wrap: wrap; align-items: flex-start; }
}
</style>
