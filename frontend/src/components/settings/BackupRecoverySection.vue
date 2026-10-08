<template>
  <SettingsSection :title="t('backups.title', 'Backup and recovery')">
    <div class="backup-heading">
      <p>{{ t('backups.description', 'Create encrypted local backups and restore this Standalone device to an earlier state.') }}</p>
      <button type="button" class="ui-button" :disabled="loading" @click="refreshAll">
        <i class="bi bi-arrow-repeat" aria-hidden="true"></i>
        {{ loading ? t('backups.refreshing', 'Refreshing…') : t('backups.refresh', 'Refresh') }}
      </button>
    </div>

    <div v-if="errorMessage" class="backup-notice error" role="alert">{{ errorMessage }}</div>
    <div v-if="message" class="backup-notice" role="status">{{ message }}</div>

    <article class="preview-card">
      <div class="preview-status">
        <span class="status-dot" aria-hidden="true" :class="preview?.ready ? 'ready' : 'blocked'"></span>
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
      <button type="button" class="ui-button ui-button--primary" :disabled="!preview?.ready || controlsBusy" @click="createBackup">
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
      <button type="button" class="ui-button" :disabled="controlsBusy" @click="chooseRestoreFile">
        <i class="bi bi-upload" aria-hidden="true"></i>
        {{ actionBusy === 'restore-file' ? t('backups.importing', 'Checking file…') : t('backups.restoreFile', 'Restore from file') }}
      </button>
    </article>

    <div class="catalog-heading">
      <div>
        <h4>{{ t('backups.savedTitle', 'Saved backups') }}</h4>
        <p>{{ t('backups.retention', 'The five newest backups are kept automatically on this device.') }}</p>
      </div>
      <span class="count-badge ui-badge">{{ catalog.length }} / {{ retentionCount }}</span>
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
          <button type="button" class="ui-button" :disabled="controlsBusy" @click="downloadBackup(item)">
            <i class="bi bi-download" aria-hidden="true"></i>
            {{ actionBusy === `export:${item.backup_id}` ? t('backups.preparingDownload', 'Preparing…') : t('backups.download', 'Download') }}
          </button>
          <button type="button" class="ui-button" :disabled="controlsBusy" @click="restoreBackup(item)">
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
.backup-heading, .catalog-heading, .preview-status, .backup-row { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); min-width: 0; }
.backup-heading, .catalog-heading { justify-content: space-between; }
.backup-heading p, .catalog-heading p, .portable-copy p, .preview-status small, .backup-copy span, .backup-copy small { color: var(--ui-text-secondary); }
.preview-card, .portable-card { margin-top: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); min-width: 0; }
.preview-card { background: var(--ui-surface-alt); }
.portable-card { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--ui-space) * 4); }
.portable-copy { display: flex; align-items: flex-start; gap: calc(var(--ui-space) * 3); min-width: 0; }
.portable-copy > i, .backup-icon { color: var(--ui-accent); font-size: 1.25rem; }
.portable-copy p { margin-top: var(--ui-space); }
.preview-status small, .backup-copy span, .backup-copy small { display: block; }
.status-dot { flex: 0 0 .7rem; height: .7rem; border-radius: 50%; background: var(--ui-danger); }
.status-dot.ready { background: var(--ui-success); }
.backup-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: calc(var(--ui-space) * 3); margin: calc(var(--ui-space) * 4) 0; }
.backup-metrics div { padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface); }
.backup-metrics dt { color: var(--ui-text-secondary); font-size: .85em; }
.backup-metrics dd { margin: var(--ui-space) 0 0; color: var(--ui-text); font-weight: 650; }
.issue-list { margin: calc(var(--ui-space) * 3) 0; color: var(--ui-warning); overflow-wrap: anywhere; }
.catalog-heading { margin: calc(var(--ui-space) * 5) 0 calc(var(--ui-space) * 3); }
.catalog-heading h4 { margin: 0; font-size: 1rem; }
.count-badge { flex: 0 0 auto; }
.backup-list { display: grid; gap: calc(var(--ui-space) * 3); }
.backup-row { padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.backup-copy { min-width: 0; flex: 1; overflow-wrap: anywhere; }
.backup-actions { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
.backup-copy small { font-size: .8em; }
.empty-state { padding: calc(var(--ui-space) * 4); border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-sm); color: var(--ui-text-secondary); }
.backup-notice { margin-top: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); color: var(--ui-text); overflow-wrap: anywhere; }
.backup-notice.error { color: var(--ui-danger); }
@media (max-width: 720px) {
  .backup-heading, .catalog-heading { align-items: flex-start; flex-wrap: wrap; }
  .backup-metrics { grid-template-columns: minmax(0, 1fr); }
  .backup-row { align-items: flex-start; flex-wrap: wrap; }
  .backup-actions { width: 100%; }
  .backup-actions .ui-button { flex: 1; }
  .portable-card { align-items: stretch; flex-direction: column; }
}
</style>
