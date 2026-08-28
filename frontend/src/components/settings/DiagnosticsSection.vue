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
      <button type="button" class="button button-primary" :disabled="downloading || loading" @click="downloadBundle">
        <i class="bi bi-download" aria-hidden="true"></i>
        {{ downloading ? t('diagnostics.downloading', 'Preparing…') : t('diagnostics.download', 'Download diagnostics') }}
      </button>
    </div>

    <div v-if="loading" class="loading-row">{{ t('diagnostics.loading', 'Checking device…') }}</div>
    <template v-else-if="preview">
      <div class="diagnostic-meta">
        <span>{{ preview.check_count }} {{ t('diagnostics.checks', 'checks') }}</span>
        <span>{{ preview.warning_count }} {{ t('diagnostics.warnings', 'warnings') }}</span>
        <span>{{ formatBytes(preview.estimated_size_bytes) }}</span>
      </div>
      <div class="check-list">
        <article v-for="check in preview.checks" :key="check.name" class="check-row">
          <span class="check-dot" :class="check.status"></span>
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
.section-intro { margin: 0 0 1rem; color: var(--text-secondary); }

.diagnostic-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.9rem;
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--panel-bg);
}

.summary-icon {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--border-radius-sm);
  color: var(--button-primary-bg);
  background: color-mix(in srgb, var(--button-primary-bg) 12%, transparent);
}

.summary-copy strong,
.summary-copy span,
.check-row small { display: block; }
.summary-copy span,
.check-row small { color: var(--text-secondary); }

.diagnostic-meta { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0 0.65rem; }
.diagnostic-meta span { padding: 0.3rem 0.55rem; border: 1px solid var(--card-border); border-radius: 999px; color: var(--text-secondary); font-size: 0.8rem; }
.check-list { display: grid; gap: 0.5rem; }
.check-row { display: flex; align-items: center; gap: 0.7rem; padding: 0.7rem; border: 1px solid var(--card-border); border-radius: var(--border-radius-sm); }
.check-dot { width: 0.65rem; height: 0.65rem; border-radius: 50%; background: var(--button-danger-bg); }
.check-dot.ok { background: #22a06b; }
.check-dot.warning { background: #d97706; }
.loading-row { padding: 1rem 0; color: var(--text-secondary); }
.diagnostic-notice { margin-bottom: 0.85rem; padding: 0.75rem; border: 1px solid var(--card-border); border-radius: var(--border-radius-sm); }
.diagnostic-notice.error { border-color: color-mix(in srgb, var(--button-danger-bg) 42%, var(--card-border)); }

@media (max-width: 640px) {
  .diagnostic-summary { grid-template-columns: auto minmax(0, 1fr); }
  .diagnostic-summary .button { grid-column: 1 / -1; width: 100%; }
}
</style>
