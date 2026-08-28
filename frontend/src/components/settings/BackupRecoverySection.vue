<template>
  <SettingsSection :title="t('backups.title', 'Backup and recovery')">
    <div class="backup-heading">
      <p>{{ t('backups.description', 'Create encrypted local backups and restore this Standalone device to an earlier state.') }}</p>
      <button type="button" class="button button-secondary button-sm" :disabled="loading" @click="refreshAll">
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>
        {{ loading ? t('backups.refreshing', 'Refreshing…') : t('backups.refresh', 'Refresh') }}
      </button>
    </div>

    <div v-if="errorMessage" class="backup-notice error" role="alert">{{ errorMessage }}</div>
    <div v-if="message" class="backup-notice" role="status">{{ message }}</div>

    <article class="preview-card">
      <div class="preview-status">
        <span class="status-dot" :class="preview?.ready ? 'ready' : 'blocked'"></span>
        <div>
          <strong>{{ preview?.ready ? t('backups.ready', 'Ready to back up') : t('backups.notReady', 'Backup is not ready') }}</strong>
          <small v-if="operation">{{ operationLabel }}</small>
        </div>
      </div>
      <dl class="backup-metrics">
        <div><dt>{{ t('backups.estimatedSize', 'Estimated size') }}</dt><dd>{{ formatBytes(preview?.estimated_backup_bytes) }}</dd></div>
        <div><dt>{{ t('backups.availableSpace', 'Free space') }}</dt><dd>{{ formatBytes(preview?.available_bytes) }}</dd></div>
        <div><dt>{{ t('backups.files', 'Files') }}</dt><dd>{{ preview?.entry_count ?? '—' }}</dd></div>
      </dl>
      <ul v-if="preview?.issues.length" class="issue-list">
        <li v-for="issue in preview.issues" :key="`${issue.code}-${issue.message}`">{{ issue.message }}</li>
      </ul>
      <button type="button" class="button button-primary" :disabled="!preview?.ready || controlsBusy" @click="createBackup">
        {{ actionBusy === 'create' ? t('backups.starting', 'Starting…') : t('backups.create', 'Create backup') }}
      </button>
    </article>

    <article class="portable-card">
      <div class="portable-copy">
        <i class="bi bi-device-ssd" aria-hidden="true"></i>
        <div>
          <strong>{{ t('backups.disasterTitle', 'Disaster recovery file') }}</strong>
          <p>{{ t('backups.disasterHelp', 'Download a password-protected recovery file and keep it away from this device. Use it after a new installation if the SD card fails.') }}</p>
        </div>
      </div>
      <input
        ref="restoreFileInput"
        class="visually-hidden"
        type="file"
        accept=".3mmrecovery,application/octet-stream"
        @change="restoreFromFile"
      />
      <button type="button" class="button button-secondary" :disabled="controlsBusy" @click="chooseRestoreFile">
        <i class="bi bi-upload" aria-hidden="true"></i>
        {{ actionBusy === 'restore-file' ? t('backups.importing', 'Checking file…') : t('backups.restoreFile', 'Restore from file') }}
      </button>
    </article>

    <div class="catalog-heading">
      <div>
        <h4>{{ t('backups.savedTitle', 'Saved backups') }}</h4>
        <p>{{ t('backups.retention', 'The five newest backups are kept automatically on this device.') }}</p>
      </div>
      <span class="count-badge">{{ catalog.length }} / {{ retentionCount }}</span>
    </div>
    <ul v-if="catalogIssues.length" class="issue-list">
      <li v-for="issue in catalogIssues" :key="`${issue.code}-${issue.message}`">{{ issue.message }}</li>
    </ul>

    <div v-if="!catalog.length" class="empty-state">
      <i class="bi bi-archive" aria-hidden="true"></i>
      {{ t('backups.empty', 'No local backups yet.') }}
    </div>
    <div v-else class="backup-list">
      <article v-for="item in catalog" :key="item.backup_id" class="backup-row">
        <div class="backup-icon"><i class="bi bi-shield-lock" aria-hidden="true"></i></div>
        <div class="backup-copy">
          <strong>{{ formatDate(item.created_at) }}</strong>
          <span>{{ item.application_version }} · {{ item.architecture }} · {{ formatBytes(item.archive_size_bytes) }}</span>
          <small>{{ item.backup_id }}</small>
        </div>
        <div class="backup-actions">
          <button type="button" class="button button-secondary button-sm" :disabled="controlsBusy" @click="downloadBackup(item)">
            <i class="bi bi-download" aria-hidden="true"></i>
            {{ actionBusy === `export:${item.backup_id}` ? t('backups.preparingDownload', 'Preparing…') : t('backups.download', 'Download') }}
          </button>
          <button type="button" class="button button-secondary button-sm" :disabled="controlsBusy" @click="restoreBackup(item)">
            {{ actionBusy === item.backup_id ? t('backups.starting', 'Starting…') : t('backups.restore', 'Restore') }}
          </button>
        </div>
      </article>
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'

type PreviewIssue = { severity: 'warning' | 'error'; code: string; message: string }
type BackupPreview = {
  ready: boolean
  entry_count: number
  estimated_backup_bytes: number
  available_bytes: number
  issues: PreviewIssue[]
}
type CatalogItem = {
  backup_id: string
  created_at: string
  application_version: string
  architecture: string
  archive_size_bytes: number
}
type Operation = { state: string; message: string; backup_id?: string | null }

const { t } = useI18n()
const loading = ref(false)
const preview = ref<BackupPreview | null>(null)
const catalog = ref<CatalogItem[]>([])
const catalogIssues = ref<PreviewIssue[]>([])
const retentionCount = ref(5)
const operation = ref<Operation | null>(null)
const actionBusy = ref<string | null>(null)
const message = ref('')
const errorMessage = ref('')
const restoreFileInput = ref<HTMLInputElement | null>(null)
const controlsBusy = computed(() => !!actionBusy.value || ['creating', 'restoring'].includes(operation.value?.state || ''))

const operationLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: t('backups.operationIdle', 'No backup operation has run'),
    creating: t('backups.operationCreating', 'Creating encrypted backup…'),
    restoring: t('backups.operationRestoring', 'Restoring backup…'),
    completed: t('backups.operationCompleted', 'Last operation completed'),
    rolled_back: t('backups.operationRolledBack', 'Restore failed and previous state was recovered'),
    failed: t('backups.operationFailed', 'Last operation failed'),
  }
  return labels[operation.value?.state || 'idle'] || operation.value?.message || ''
})

function formatBytes(value?: number) {
  if (value === undefined || value === null) return '—'
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let unit = units[0]
  for (let index = 1; size >= 1024 && index < units.length; index += 1) {
    size /= 1024
    unit = units[index]
  }
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${unit}`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function detail(error: any) {
  return error?.response?.data?.detail || t('backups.loadFailed', 'Backup information could not be loaded.')
}

async function refreshAll() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [previewResponse, catalogResponse, operationResponse] = await Promise.all([
      http.get('/api/v1/backups/preview'),
      http.get('/api/v1/backups'),
      http.get('/api/v1/backups/operation'),
    ])
    preview.value = previewResponse.data
    catalog.value = catalogResponse.data.items || []
    catalogIssues.value = catalogResponse.data.issues || []
    retentionCount.value = catalogResponse.data.retention_count || 5
    operation.value = operationResponse.data
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    loading.value = false
  }
}

async function createBackup() {
  const phrase = 'CREATE BACKUP'
  const entered = prompt(t('backups.createConfirm', 'Type CREATE BACKUP to create an encrypted local backup.'), '')
  if (entered !== phrase) return
  actionBusy.value = 'create'
  message.value = ''
  errorMessage.value = ''
  try {
    await http.post('/api/v1/backups', { confirmation: phrase })
    message.value = t('backups.createQueued', 'Backup started. The application may be unavailable briefly; refresh after it returns.')
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    actionBusy.value = null
  }
}

async function restoreBackup(item: CatalogItem) {
  const phrase = `RESTORE ${item.backup_id}`
  const entered = prompt(t('backups.restoreConfirm', 'Type the shown RESTORE phrase to replace the current device data with this backup.') + `\n${phrase}`, '')
  if (entered !== phrase) return
  actionBusy.value = item.backup_id
  message.value = ''
  errorMessage.value = ''
  try {
    await http.post('/api/v1/backups/restore', { backup_id: item.backup_id, confirmation: phrase })
    message.value = t('backups.restoreQueued', 'Restore started. The application may restart; reconnect and refresh after it returns.')
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    actionBusy.value = null
  }
}

function recoveryPassword(confirmPassword = false) {
  const password = prompt(t('backups.passwordPrompt', 'Enter a recovery password with at least 8 characters.'), '')
  if (!password || new TextEncoder().encode(password).length < 8) {
    if (password !== null) errorMessage.value = t('backups.passwordTooShort', 'The recovery password must contain at least 8 characters.')
    return null
  }
  if (confirmPassword) {
    const repeated = prompt(t('backups.passwordRepeat', 'Enter the recovery password again.'), '')
    if (repeated !== password) {
      errorMessage.value = t('backups.passwordMismatch', 'The recovery passwords do not match.')
      return null
    }
  }
  return password
}

async function downloadBackup(item: CatalogItem) {
  errorMessage.value = ''
  message.value = ''
  const password = recoveryPassword(true)
  if (!password || !confirm(t('backups.downloadConfirm', 'Create and download a portable recovery file? Keep both the file and its password safe.'))) return
  actionBusy.value = `export:${item.backup_id}`
  try {
    const prepared = await http.post(`/api/v1/backups/${item.backup_id}/export`, {
      passphrase: password,
      confirmation: `DOWNLOAD ${item.backup_id}`,
    })
    const response = await http.get(`/api/v1/backups/exports/${prepared.data.export_id}`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${item.backup_id}.3mmrecovery`
    anchor.click()
    URL.revokeObjectURL(url)
    message.value = t('backups.downloadReady', 'Recovery file downloaded. Store it and its password away from this device.')
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    actionBusy.value = null
  }
}

function chooseRestoreFile() {
  restoreFileInput.value?.click()
}

async function restoreFromFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  errorMessage.value = ''
  message.value = ''
  const password = recoveryPassword()
  if (!password || !confirm(t('backups.restoreFileConfirm', 'Restore all application data from this file? The device will restart its services.'))) {
    input.value = ''
    return
  }
  actionBusy.value = 'restore-file'
  const form = new FormData()
  form.append('file', file)
  form.append('passphrase', password)
  form.append('confirmation', 'RESTORE FILE')
  try {
    await http.post('/api/v1/backups/restore-file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    })
    message.value = t('backups.restoreQueued', 'Restore started. The application may restart; reconnect and refresh after it returns.')
  } catch (error: any) {
    errorMessage.value = detail(error)
  } finally {
    actionBusy.value = null
    input.value = ''
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.backup-heading,
.catalog-heading,
.preview-status,
.backup-row {
  display: flex;
  align-items: center;
  gap: 0.85rem;
}

.backup-heading,
.catalog-heading {
  justify-content: space-between;
}

.backup-heading p,
.catalog-heading p {
  margin: 0;
  color: var(--text-secondary);
}

.preview-card {
  margin-top: 1rem;
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--panel-bg);
}

.portable-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.75rem;
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--card-bg);
}

.portable-copy { display: flex; align-items: flex-start; gap: 0.8rem; }
.portable-copy > i { color: var(--button-primary-bg); font-size: 1.35rem; }
.portable-copy strong { color: var(--text-primary); }
.portable-copy p { margin: 0.2rem 0 0; color: var(--text-secondary); }

.preview-status small,
.backup-copy span,
.backup-copy small {
  display: block;
  color: var(--text-secondary);
}

.status-dot {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
  background: var(--button-danger-bg);
}

.status-dot.ready { background: #22a06b; }

.backup-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 1rem 0;
}

.backup-metrics div {
  padding: 0.75rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-sm);
  background: var(--card-bg);
}

.backup-metrics dt { color: var(--text-secondary); font-size: 0.78rem; }
.backup-metrics dd { margin: 0.2rem 0 0; color: var(--text-primary); font-weight: 650; }

.issue-list { margin: 0 0 1rem; color: var(--text-secondary); }
.catalog-heading { margin: 1.25rem 0 0.75rem; }
.catalog-heading h4 { margin: 0 0 0.2rem; color: var(--text-primary); font-size: 1rem; }

.count-badge {
  flex: 0 0 auto;
  padding: 0.25rem 0.55rem;
  border-radius: 999px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  border: 1px solid var(--card-border);
  font-size: 0.8rem;
}

.backup-list { display: grid; gap: 0.65rem; }
.backup-row { padding: 0.8rem; border: 1px solid var(--card-border); border-radius: var(--border-radius-md); }
.backup-icon { color: var(--button-primary-bg); font-size: 1.2rem; }
.backup-copy { min-width: 0; flex: 1; }
.backup-actions { display: flex; gap: 0.5rem; }
.backup-copy small { overflow-wrap: anywhere; font-size: 0.72rem; }
.empty-state { padding: 1rem; border: 1px dashed var(--card-border); border-radius: var(--border-radius-md); color: var(--text-secondary); }

.backup-notice {
  margin-top: 0.85rem;
  padding: 0.75rem;
  border: 1px solid color-mix(in srgb, var(--button-primary-bg) 35%, var(--card-border));
  border-radius: var(--border-radius-sm);
  color: var(--text-primary);
  background: color-mix(in srgb, var(--button-primary-bg) 8%, var(--card-bg));
}

.backup-notice.error { border-color: color-mix(in srgb, var(--button-danger-bg) 42%, var(--card-border)); }

@media (max-width: 640px) {
  .backup-heading,
  .catalog-heading { align-items: flex-start; }
  .backup-metrics { grid-template-columns: 1fr; }
  .backup-row { align-items: flex-start; flex-wrap: wrap; }
  .backup-actions { width: 100%; }
  .backup-actions .button { flex: 1; }
  .portable-card { align-items: stretch; flex-direction: column; }
  .portable-card > .button { width: 100%; }
}
</style>
