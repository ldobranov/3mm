<template>
  <main class="view updates-view">
    <header class="updates-header">
      <div>
        <p class="eyebrow">{{ t('systemUpdates.eyebrow', 'System') }}</p>
        <h1 class="view-title">{{ t('systemUpdates.title', 'System updates') }}</h1>
        <p class="intro">
          {{ t('systemUpdates.subtitle', 'Review the installed release and check the trusted release catalog.') }}
        </p>
      </div>
      <div class="updates-actions">
        <button
          v-if="canStage"
          class="button button-secondary"
          :disabled="staging || operationBusy"
          @click="stageUpdate"
        >
          <i class="bi bi-cloud-arrow-down" :class="{ spinning: staging }" aria-hidden="true"></i>
          {{ staging ? t('systemUpdates.staging', 'Downloading and verifying…') : t('systemUpdates.stage', 'Download and verify') }}
        </button>
        <button class="button button-primary" :disabled="checking || loading || staging" @click="checkForUpdates">
          <i class="bi bi-arrow-repeat" :class="{ spinning: checking }" aria-hidden="true"></i>
          {{ checking ? t('systemUpdates.checking', 'Checking…') : t('systemUpdates.check', 'Check for updates') }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="notice notice-error" role="alert">
      <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
      {{ errorMessage }}
    </div>

    <section class="safety-banner" aria-labelledby="read-only-title">
      <i class="bi bi-shield-check" aria-hidden="true"></i>
      <div>
        <strong id="read-only-title">{{ t('systemUpdates.safeTitle', 'Verified manual updates') }}</strong>
        <p>{{ t('systemUpdates.safeText', 'Checking never changes the device. Downloading verifies the exact release first, and installation requires a separate administrator approval.') }}</p>
      </div>
    </section>

    <div v-if="loading" class="loading-state" aria-live="polite">
      <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
      {{ t('systemUpdates.loading', 'Loading update status…') }}
    </div>

    <template v-else-if="status">
      <section class="status-card card">
        <div class="status-summary">
          <span class="status-icon" :class="`status-icon-${status.status}`">
            <i :class="statusIcon" aria-hidden="true"></i>
          </span>
          <div>
            <span class="status-label" :class="`status-${status.status}`">{{ statusLabel }}</span>
            <p>{{ status.message }}</p>
          </div>
        </div>
        <time v-if="status.checked_at" :datetime="status.checked_at">
          {{ t('systemUpdates.checkedAt', 'Checked') }} {{ formatDate(status.checked_at) }}
        </time>
      </section>

      <div class="release-grid">
        <section class="release-card card">
          <div class="section-heading">
            <span class="section-icon"><i class="bi bi-hdd-stack" aria-hidden="true"></i></span>
            <div>
              <p class="eyebrow">{{ t('systemUpdates.deviceEyebrow', 'This device') }}</p>
              <h2>{{ t('systemUpdates.currentTitle', 'Installed release') }}</h2>
            </div>
          </div>
          <dl class="detail-list">
            <div>
              <dt>{{ t('systemUpdates.releaseId', 'Release') }}</dt>
              <dd>{{ status.current.release_id }}</dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.commit', 'Commit') }}</dt>
              <dd><code>{{ shortHash(status.current.commit) }}</code></dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.branch', 'Branch') }}</dt>
              <dd>{{ status.current.branch || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.architecture', 'Architecture') }}</dt>
              <dd>{{ status.architecture }}</dd>
            </div>
          </dl>
          <p v-if="!status.current.metadata_available" class="metadata-note">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
            {{ t('systemUpdates.metadataMissing', 'Release metadata is unavailable, so the installed version cannot be compared yet.') }}
          </p>
        </section>

        <section class="release-card card">
          <div class="section-heading">
            <span class="section-icon"><i class="bi bi-github" aria-hidden="true"></i></span>
            <div>
              <p class="eyebrow">{{ t('systemUpdates.catalogEyebrow', 'Trusted source') }}</p>
              <h2>{{ t('systemUpdates.catalogTitle', 'Release catalog') }}</h2>
            </div>
          </div>
          <dl class="detail-list">
            <div>
              <dt>{{ t('systemUpdates.repository', 'Repository') }}</dt>
              <dd>
                <a :href="status.repository_url" target="_blank" rel="noopener noreferrer">
                  {{ status.repository }} <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>
                </a>
              </dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.latestVersion', 'Latest version') }}</dt>
              <dd>{{ status.latest?.version || status.latest?.tag || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.channel', 'Channel') }}</dt>
              <dd>{{ status.latest?.channel || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('systemUpdates.published', 'Published') }}</dt>
              <dd>{{ status.latest?.published_at ? formatDate(status.latest.published_at) : '—' }}</dd>
            </div>
          </dl>
          <p v-if="status.latest?.manifest_validated" class="manifest-valid">
            <i class="bi bi-patch-check-fill" aria-hidden="true"></i>
            {{ t('systemUpdates.manifestValidated', 'The release manifest matches the published assets.') }}
          </p>
        </section>
      </div>

      <section v-if="status.latest?.manifest_validated" class="requirements-card card">
        <div class="requirements-column">
          <h2>{{ t('systemUpdates.dependenciesTitle', 'System dependencies') }}</h2>
          <p>{{ t('systemUpdates.dependenciesText', 'Packages declared by this release. Nothing is installed during a check.') }}</p>
          <ul v-if="status.latest.dependencies.apt_packages.length" class="tag-list">
            <li v-for="dependency in status.latest.dependencies.apt_packages" :key="dependency">
              <code>{{ dependency }}</code>
            </li>
          </ul>
          <span v-else class="empty-value">{{ t('systemUpdates.noDependencies', 'No additional packages declared') }}</span>
        </div>
        <div class="requirements-column">
          <h2>{{ t('systemUpdates.artifactsTitle', 'Release artifacts') }}</h2>
          <p>{{ t('systemUpdates.artifactsText', 'Architecture-specific files validated against the catalog manifest.') }}</p>
          <ul v-if="status.latest.artifacts.length" class="artifact-list">
            <li v-for="artifact in status.latest.artifacts" :key="artifact.architecture">
              <div>
                <strong>{{ artifact.architecture }}</strong>
                <span>{{ artifact.filename }}</span>
              </div>
              <span>{{ formatBytes(artifact.size_bytes) }}</span>
            </li>
          </ul>
          <span v-else class="empty-value">{{ t('systemUpdates.noArtifacts', 'No validated artifacts') }}</span>
        </div>
      </section>

      <section v-if="operation && operation.state !== 'idle'" class="operation-card card" aria-live="polite">
        <span class="status-icon" :class="`operation-${operation.state}`">
          <i :class="[operationIcon, { spinning: operationBusy }]" aria-hidden="true"></i>
        </span>
        <div>
          <p class="eyebrow">{{ t('systemUpdates.operationEyebrow', 'Installation status') }}</p>
          <h2>{{ operationLabel }}</h2>
          <p>{{ operation.message }}</p>
        </div>
      </section>

      <section v-if="staged" class="stage-card card">
        <div class="section-heading">
          <span class="section-icon"><i class="bi bi-shield-check" aria-hidden="true"></i></span>
          <div>
            <p class="eyebrow">{{ t('systemUpdates.reviewEyebrow', 'Ready for review') }}</p>
            <h2>{{ t('systemUpdates.reviewTitle', 'Verified update plan') }} {{ staged.version }}</h2>
          </div>
        </div>

        <div class="review-grid">
          <div>
            <h3>{{ t('systemUpdates.preflightTitle', 'Preflight checks') }}</h3>
            <ul class="check-list">
              <li v-for="check in staged.preflight" :key="check.name">
                <i class="bi bi-check-circle-fill" aria-hidden="true"></i>
                <span><strong>{{ preflightLabel(check.name) }}</strong><small>{{ check.detail }}</small></span>
              </li>
            </ul>
          </div>
          <div>
            <h3>{{ t('systemUpdates.dependencyPlanTitle', 'Dependency plan') }}</h3>
            <ul v-if="staged.dependency_plan.length" class="dependency-plan">
              <li v-for="dependency in staged.dependency_plan" :key="dependency.name">
                <code>{{ dependency.name }}</code>
                <span :class="`dependency-${dependency.action}`">
                  {{ dependency.action === 'install' ? t('systemUpdates.willInstall', 'Will install') : t('systemUpdates.alreadyInstalled', 'Already installed') }}
                </span>
              </li>
            </ul>
            <p v-else class="empty-value">{{ t('systemUpdates.noDependencies', 'No additional packages declared') }}</p>
          </div>
        </div>

        <div class="restart-warning">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
          <p>
            <strong>{{ t('systemUpdates.restartTitle', 'Services will restart') }}</strong>
            <span>{{ t('systemUpdates.restartText', 'The application may be unavailable briefly. A failed health check restores the previous release and database backup automatically.') }}</span>
          </p>
          <button class="button button-primary" :disabled="operationBusy" @click="showConfirmation = true">
            {{ t('systemUpdates.reviewInstall', 'Review and install') }}
          </button>
        </div>
      </section>
    </template>

    <div v-if="showConfirmation && staged" class="modal-backdrop" role="presentation" @click.self="closeConfirmation">
      <section class="confirm-dialog card" role="dialog" aria-modal="true" aria-labelledby="update-confirm-title">
        <button class="dialog-close" :aria-label="t('common.cancel', 'Cancel')" @click="closeConfirmation">
          <i class="bi bi-x-lg" aria-hidden="true"></i>
        </button>
        <span class="confirm-icon"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i></span>
        <h2 id="update-confirm-title">{{ t('systemUpdates.confirmTitle', 'Install system update?') }}</h2>
        <p>{{ t('systemUpdates.confirmText', '3mm will install the reviewed release and restart its services. Do not remove power during the update.') }}</p>
        <dl class="confirm-summary">
          <div><dt>{{ t('systemUpdates.releaseId', 'Release') }}</dt><dd>{{ staged.release_id }}</dd></div>
          <div><dt>{{ t('systemUpdates.latestVersion', 'Version') }}</dt><dd>{{ staged.version }}</dd></div>
          <div><dt>{{ t('systemUpdates.architecture', 'Architecture') }}</dt><dd>{{ staged.architecture }}</dd></div>
        </dl>
        <label class="confirm-check">
          <input v-model="restartAcknowledged" type="checkbox">
          <span>{{ t('systemUpdates.confirmRestart', 'I understand that the application will restart and may be briefly unavailable.') }}</span>
        </label>
        <div class="dialog-actions">
          <button class="button button-secondary" :disabled="applying" @click="closeConfirmation">{{ t('common.cancel', 'Cancel') }}</button>
          <button class="button button-primary" :disabled="!restartAcknowledged || applying" @click="applyUpdate">
            <i class="bi bi-arrow-up-circle" :class="{ spinning: applying }" aria-hidden="true"></i>
            {{ applying ? t('systemUpdates.startingInstall', 'Starting…') : t('systemUpdates.installNow', 'Install update') }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

type UpdateStatus =
  | 'not_checked'
  | 'no_release'
  | 'manifest_missing'
  | 'update_available'
  | 'up_to_date'
  | 'not_newer'
  | 'current_unknown'
  | 'unsupported_architecture'
  | 'error'

interface CurrentRelease {
  release_id: string
  commit: string | null
  branch: string | null
  version: string | null
  created_at: string | null
  includes_working_tree: boolean | null
  metadata_available: boolean
}

interface UpdateArtifact {
  architecture: string
  filename: string
  download_url: string
  sha256: string
  size_bytes: number
}

interface LatestRelease {
  tag: string
  name: string
  published_at: string | null
  html_url: string
  manifest_validated: boolean
  version: string | null
  release_id: string | null
  commit: string | null
  channel: string | null
  artifacts: UpdateArtifact[]
  dependencies: { apt_packages: string[] }
}

interface UpdateCheckResponse {
  status: UpdateStatus
  message: string
  repository: string
  repository_url: string
  architecture: string
  current: CurrentRelease
  latest: LatestRelease | null
  update_available: boolean | null
  checked_at: string | null
}

type OperationState = 'idle' | 'ready' | 'queued' | 'applying' | 'succeeded' | 'failed'

interface UpdateOperation {
  state: OperationState
  message: string
  release_id: string | null
  version: string | null
  commit: string | null
  requested_by_user_id: number | null
  started_at: string | null
  completed_at: string | null
  error_code: string | null
}

interface StagedUpdate {
  release_id: string
  version: string
  commit: string
  architecture: string
  artifact_filename: string
  artifact_sha256: string
  artifact_size_bytes: number
  dependencies: string[]
  dependency_plan: Array<{ name: string; installed: boolean; action: 'keep' | 'install' }>
  frontend_origin: string
  staged_at: string
  approval_expires_at: string
  approval_nonce: string
  preflight: Array<{ name: string; passed: boolean; detail: string }>
}

const { t } = useI18n()
const status = ref<UpdateCheckResponse | null>(null)
const loading = ref(true)
const checking = ref(false)
const staging = ref(false)
const applying = ref(false)
const errorMessage = ref('')
const staged = ref<StagedUpdate | null>(null)
const operation = ref<UpdateOperation | null>(null)
const showConfirmation = ref(false)
const restartAcknowledged = ref(false)
let operationTimer: ReturnType<typeof setInterval> | null = null

const operationBusy = computed(() => operation.value?.state === 'queued' || operation.value?.state === 'applying')
const canStage = computed(() => {
  const latest = status.value?.latest
  return Boolean(
    latest?.manifest_validated
    && latest.artifacts.some(artifact => artifact.architecture === status.value?.architecture)
    && status.value?.status === 'update_available'
    && !operationBusy.value,
  )
})

const statusLabel = computed(() => status.value ? {
  not_checked: t('systemUpdates.statusNotChecked', 'Not checked yet'),
  no_release: t('systemUpdates.statusNoRelease', 'No published release'),
  manifest_missing: t('systemUpdates.statusManifestMissing', 'Manifest missing'),
  update_available: t('systemUpdates.statusUpdateAvailable', 'Update available'),
  up_to_date: t('systemUpdates.statusUpToDate', 'Up to date'),
  not_newer: t('systemUpdates.statusNotNewer', 'No newer release'),
  current_unknown: t('systemUpdates.statusCurrentUnknown', 'Current version unknown'),
  unsupported_architecture: t('systemUpdates.statusUnsupported', 'Architecture not supported'),
  error: t('systemUpdates.statusError', 'Check failed'),
}[status.value.status] : '')

const statusIcon = computed(() => status.value ? {
  not_checked: 'bi bi-clock-history',
  no_release: 'bi bi-inbox',
  manifest_missing: 'bi bi-file-earmark-x',
  update_available: 'bi bi-cloud-arrow-down',
  up_to_date: 'bi bi-check2-circle',
  not_newer: 'bi bi-shield-check',
  current_unknown: 'bi bi-question-circle',
  unsupported_architecture: 'bi bi-cpu',
  error: 'bi bi-exclamation-triangle',
}[status.value.status] : 'bi bi-clock-history')

const operationLabel = computed(() => operation.value ? {
  idle: t('systemUpdates.operationIdle', 'No update is staged'),
  ready: t('systemUpdates.operationReady', 'Ready for approval'),
  queued: t('systemUpdates.operationQueued', 'Update queued'),
  applying: t('systemUpdates.operationApplying', 'Installing update'),
  succeeded: t('systemUpdates.operationSucceeded', 'Update completed'),
  failed: t('systemUpdates.operationFailed', 'Update failed and was stopped'),
}[operation.value.state] : '')

const operationIcon = computed(() => operation.value ? {
  idle: 'bi bi-clock-history',
  ready: 'bi bi-shield-check',
  queued: 'bi bi-hourglass-split',
  applying: 'bi bi-arrow-repeat',
  succeeded: 'bi bi-check-circle-fill',
  failed: 'bi bi-exclamation-triangle-fill',
}[operation.value.state] : 'bi bi-clock-history')

function errorText(error: any): string {
  return error?.response?.data?.detail || error?.message || t('systemUpdates.unknownError', 'The update status could not be loaded.')
}

function shortHash(value: string | null): string {
  return value ? value.slice(0, 12) : '—'
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(parsed)
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`
}

async function loadLocalStatus() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await http.get('/api/v1/system-updates/status')
    status.value = response.data
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    loading.value = false
  }
}

async function checkForUpdates() {
  checking.value = true
  errorMessage.value = ''
  try {
    const response = await http.post('/api/v1/system-updates/check')
    status.value = response.data
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    checking.value = false
  }
}

function preflightLabel(name: string): string {
  return {
    'archive.identity': t('systemUpdates.preflightArchive', 'Release file verified'),
    'storage.free': t('systemUpdates.preflightStorage', 'Storage ready'),
    'database.backup': t('systemUpdates.preflightDatabase', 'Database ready for backup'),
    'migration.entrypoint': t('systemUpdates.preflightMigration', 'Migration and rollback entrypoints present'),
    'dependencies.allowlist': t('systemUpdates.preflightDependencies', 'Dependencies approved'),
  }[name] || name
}

async function stageUpdate() {
  staging.value = true
  errorMessage.value = ''
  try {
    const response = await http.post('/api/v1/system-updates/stage')
    staged.value = response.data.staged
    operation.value = {
      state: 'ready',
      message: t('systemUpdates.readyMessage', 'The verified update is ready for administrator approval.'),
      release_id: staged.value!.release_id,
      version: staged.value!.version,
      commit: staged.value!.commit,
      requested_by_user_id: null,
      started_at: null,
      completed_at: null,
      error_code: null,
    }
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    staging.value = false
  }
}

function closeConfirmation() {
  if (applying.value) return
  showConfirmation.value = false
  restartAcknowledged.value = false
}

function startOperationPolling() {
  if (operationTimer) return
  operationTimer = setInterval(() => loadOperation(true), 2500)
}

function stopOperationPolling() {
  if (!operationTimer) return
  clearInterval(operationTimer)
  operationTimer = null
}

async function loadOperation(silent = false) {
  try {
    const response = await http.get('/api/v1/system-updates/operation')
    operation.value = response.data
    if (operationBusy.value) {
      startOperationPolling()
    } else {
      stopOperationPolling()
      if (operation.value?.state === 'succeeded') {
        staged.value = null
        await loadLocalStatus()
      }
    }
  } catch (error) {
    if (!silent) errorMessage.value = errorText(error)
  }
}

async function applyUpdate() {
  if (!staged.value || !restartAcknowledged.value) return
  applying.value = true
  errorMessage.value = ''
  const reviewed = staged.value
  let started = false
  try {
    const response = await http.post('/api/v1/system-updates/apply', {
      release_id: reviewed.release_id,
      approval_nonce: reviewed.approval_nonce,
      confirmation: `INSTALL ${reviewed.version}`,
    })
    operation.value = response.data
    started = true
  } catch (error: any) {
    if (error?.response) {
      errorMessage.value = errorText(error)
    } else {
      started = true
      operation.value = {
        state: 'queued',
        message: t('systemUpdates.reconnecting', 'The update started. Waiting for the application to return…'),
        release_id: reviewed.release_id,
        version: reviewed.version,
        commit: reviewed.commit,
        requested_by_user_id: null,
        started_at: new Date().toISOString(),
        completed_at: null,
        error_code: null,
      }
    }
  } finally {
    applying.value = false
    if (started) {
      showConfirmation.value = false
      restartAcknowledged.value = false
      staged.value = null
      startOperationPolling()
    }
  }
}

onMounted(async () => {
  await Promise.all([loadLocalStatus(), loadOperation()])
})
onUnmounted(stopOperationPolling)
</script>

<style scoped>
.updates-view {
  --updates-surface: var(--card-bg, #fff);
  --updates-soft: var(--color-background-soft, #f8fafc);
  --updates-border: var(--color-border, #e5e7eb);
  --updates-text: var(--text-primary, #222);
  --updates-muted: var(--text-secondary, #666);
  max-width: 1180px;
  margin: 0 auto;
  color: var(--updates-text);
}
:global(.dark-mode) .updates-view {
  --updates-surface: color-mix(in srgb, var(--body-bg, #0f172a) 88%, white);
  --updates-soft: color-mix(in srgb, var(--body-bg, #0f172a) 78%, white);
  --updates-border: color-mix(in srgb, var(--body-bg, #0f172a) 62%, white);
  --updates-text: color-mix(in srgb, var(--body-bg, #0f172a) 8%, white);
  --updates-muted: color-mix(in srgb, var(--body-bg, #0f172a) 34%, white);
}
.updates-view .card { border-color: var(--updates-border); background: var(--updates-surface); color: var(--updates-text); }
.updates-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }
.updates-header h1 { margin: 0; }
.updates-actions { display: flex; flex: 0 0 auto; gap: .6rem; }
.eyebrow { margin: 0 0 .3rem; color: var(--accent); font-size: .72rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.intro { max-width: 680px; margin: .45rem 0 0; color: var(--updates-muted); }
.safety-banner { display: flex; align-items: flex-start; gap: .8rem; margin-bottom: 1rem; padding: .9rem 1rem; border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--updates-border)); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--accent) 7%, var(--updates-surface)); }
.safety-banner > i { margin-top: .05rem; color: var(--accent); font-size: 1.2rem; }
.safety-banner p { margin: .2rem 0 0; color: var(--updates-muted); font-size: .82rem; }
.notice { display: flex; align-items: center; gap: .65rem; margin-bottom: 1rem; padding: .8rem 1rem; border: 1px solid var(--updates-border); border-radius: var(--radius-sm); }
.notice-error { border-color: color-mix(in srgb, var(--danger) 42%, var(--updates-border)); background: color-mix(in srgb, var(--danger) 8%, var(--updates-surface)); }
.loading-state { display: flex; align-items: center; justify-content: center; gap: .65rem; min-height: 220px; color: var(--updates-muted); }
.status-card { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; padding: 1rem 1.1rem; }
.status-card time { flex: 0 0 auto; color: var(--updates-muted); font-size: .76rem; }
.status-summary { display: flex; align-items: center; gap: .8rem; }
.status-summary p { margin: .28rem 0 0; color: var(--updates-muted); font-size: .82rem; }
.status-icon, .section-icon { display: grid; flex: 0 0 auto; place-items: center; border-radius: var(--radius-sm); background: var(--updates-soft); color: var(--updates-muted); }
.status-icon { width: 2.6rem; height: 2.6rem; font-size: 1.2rem; }
.section-icon { width: 2.35rem; height: 2.35rem; color: var(--accent); }
.status-icon-update_available { background: color-mix(in srgb, var(--color-link) 12%, var(--updates-surface)); color: var(--color-link); }
.status-icon-up_to_date, .status-icon-not_newer { background: color-mix(in srgb, var(--accent) 13%, var(--updates-surface)); color: var(--accent); }
.status-icon-error, .status-icon-manifest_missing { background: color-mix(in srgb, var(--danger) 10%, var(--updates-surface)); color: var(--danger); }
.status-label { font-size: .82rem; font-weight: 750; }
.status-update_available { color: var(--color-link); }
.status-up_to_date, .status-not_newer { color: var(--accent); }
.status-error, .status-manifest_missing { color: var(--danger); }
.release-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.release-card { padding: 1.1rem; }
.section-heading { display: flex; align-items: center; gap: .7rem; padding-bottom: .9rem; border-bottom: 1px solid var(--updates-border); }
.section-heading h2 { margin: 0; font-size: 1rem; }
.detail-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem; margin: 1rem 0 0; }
.detail-list div { min-width: 0; }
.detail-list dt { margin-bottom: .22rem; color: var(--updates-muted); font-size: .7rem; letter-spacing: .04em; text-transform: uppercase; }
.detail-list dd { margin: 0; overflow-wrap: anywhere; font-size: .86rem; font-weight: 650; }
.detail-list code { color: var(--updates-text); }
.detail-list a { color: var(--color-link); text-decoration: none; }
.detail-list a:hover { text-decoration: underline; }
.metadata-note, .manifest-valid { display: flex; align-items: flex-start; gap: .5rem; margin: 1rem 0 0; padding: .65rem .75rem; border-radius: var(--radius-sm); background: var(--updates-soft); color: var(--updates-muted); font-size: .76rem; }
.manifest-valid { color: var(--accent); }
.requirements-card { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0; margin-top: 1rem; padding: 0; overflow: hidden; }
.requirements-column { min-width: 0; padding: 1.1rem; }
.requirements-column + .requirements-column { border-left: 1px solid var(--updates-border); }
.requirements-column h2 { margin: 0; font-size: 1rem; }
.requirements-column > p { margin: .35rem 0 .85rem; color: var(--updates-muted); font-size: .78rem; }
.tag-list, .artifact-list { margin: 0; padding: 0; list-style: none; }
.tag-list { display: flex; flex-wrap: wrap; gap: .45rem; }
.tag-list li { padding: .28rem .5rem; border: 1px solid var(--updates-border); border-radius: var(--radius-sm); background: var(--updates-soft); }
.tag-list code { color: var(--updates-text); }
.artifact-list { display: grid; gap: .5rem; }
.artifact-list li { display: flex; align-items: center; justify-content: space-between; gap: .8rem; padding: .6rem .7rem; border: 1px solid var(--updates-border); border-radius: var(--radius-sm); }
.artifact-list li div { display: flex; min-width: 0; flex-direction: column; }
.artifact-list span { color: var(--updates-muted); font-size: .72rem; overflow-wrap: anywhere; }
.empty-value { color: var(--updates-muted); font-size: .78rem; }
.operation-card { display: flex; align-items: center; gap: .85rem; margin-top: 1rem; padding: 1rem 1.1rem; }
.operation-card h2 { margin: .1rem 0 .2rem; font-size: 1rem; }
.operation-card p:last-child { margin: 0; color: var(--updates-muted); font-size: .8rem; }
.operation-succeeded { background: color-mix(in srgb, var(--accent) 13%, var(--updates-surface)); color: var(--accent); }
.operation-failed { background: color-mix(in srgb, var(--danger) 10%, var(--updates-surface)); color: var(--danger); }
.operation-queued, .operation-applying { background: color-mix(in srgb, var(--color-link) 12%, var(--updates-surface)); color: var(--color-link); }
.stage-card { margin-top: 1rem; padding: 1.1rem; }
.review-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.2rem; padding: 1rem 0; }
.review-grid h3 { margin: 0 0 .7rem; font-size: .88rem; }
.check-list, .dependency-plan { display: grid; gap: .5rem; margin: 0; padding: 0; list-style: none; }
.check-list li { display: flex; align-items: flex-start; gap: .55rem; }
.check-list i { margin-top: .12rem; color: var(--accent); }
.check-list span { display: grid; gap: .08rem; }
.check-list strong { font-size: .78rem; }
.check-list small { color: var(--updates-muted); font-size: .7rem; }
.dependency-plan li { display: flex; align-items: center; justify-content: space-between; gap: .7rem; padding: .55rem .65rem; border: 1px solid var(--updates-border); border-radius: var(--radius-sm); }
.dependency-plan span { font-size: .7rem; font-weight: 700; }
.dependency-install { color: var(--color-link); }
.dependency-keep { color: var(--accent); }
.restart-warning { display: flex; align-items: center; gap: .8rem; padding: .85rem; border: 1px solid color-mix(in srgb, var(--color-link) 28%, var(--updates-border)); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--color-link) 6%, var(--updates-surface)); }
.restart-warning > i { color: var(--color-link); font-size: 1.2rem; }
.restart-warning p { display: grid; flex: 1; gap: .12rem; margin: 0; }
.restart-warning strong { font-size: .8rem; }
.restart-warning span { color: var(--updates-muted); font-size: .72rem; }
.modal-backdrop { position: fixed; z-index: 1200; inset: 0; display: grid; place-items: center; padding: 1rem; background: rgb(15 23 42 / 58%); backdrop-filter: blur(3px); }
.confirm-dialog { position: relative; width: min(500px, 100%); padding: 1.35rem; box-shadow: 0 24px 70px rgb(0 0 0 / 28%); }
.dialog-close { position: absolute; top: .8rem; right: .8rem; display: grid; width: 2rem; height: 2rem; border: 0; border-radius: var(--radius-sm); background: var(--updates-soft); color: var(--updates-text); place-items: center; }
.confirm-icon { display: grid; width: 2.7rem; height: 2.7rem; margin-bottom: .8rem; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--color-link) 11%, var(--updates-surface)); color: var(--color-link); font-size: 1.2rem; place-items: center; }
.confirm-dialog h2 { margin: 0; font-size: 1.15rem; }
.confirm-dialog > p { margin: .45rem 2rem 1rem 0; color: var(--updates-muted); font-size: .8rem; }
.confirm-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .7rem; margin: 0 0 1rem; padding: .8rem; border-radius: var(--radius-sm); background: var(--updates-soft); }
.confirm-summary dt { color: var(--updates-muted); font-size: .65rem; text-transform: uppercase; }
.confirm-summary dd { margin: .12rem 0 0; overflow-wrap: anywhere; font-size: .78rem; font-weight: 700; }
.confirm-check { display: flex; align-items: flex-start; gap: .6rem; padding: .8rem; border: 1px solid var(--updates-border); border-radius: var(--radius-sm); cursor: pointer; }
.confirm-check input { margin-top: .16rem; accent-color: var(--accent); }
.confirm-check span { font-size: .78rem; }
.dialog-actions { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1rem; }
.spinning { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .updates-header, .status-card { align-items: stretch; flex-direction: column; }
  .updates-actions { width: 100%; flex-direction: column; }
  .updates-header .button { width: 100%; justify-content: center; }
  .release-grid, .requirements-card, .review-grid { grid-template-columns: 1fr; }
  .requirements-column + .requirements-column { border-top: 1px solid var(--updates-border); border-left: 0; }
  .restart-warning { align-items: flex-start; flex-wrap: wrap; }
  .restart-warning .button { width: 100%; justify-content: center; }
}
@media (max-width: 440px) {
  .detail-list { grid-template-columns: 1fr; }
  .confirm-summary { grid-template-columns: 1fr; }
  .dialog-actions { flex-direction: column-reverse; }
  .dialog-actions .button { width: 100%; justify-content: center; }
}
@media (prefers-reduced-motion: reduce) {
  .spinning { animation: none; }
}
</style>
