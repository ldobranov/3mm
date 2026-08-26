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
      <button class="button button-primary" :disabled="checking || loading" @click="checkForUpdates">
        <i class="bi bi-arrow-repeat" :class="{ spinning: checking }" aria-hidden="true"></i>
        {{ checking ? t('systemUpdates.checking', 'Checking…') : t('systemUpdates.check', 'Check for updates') }}
      </button>
    </header>

    <div v-if="errorMessage" class="notice notice-error" role="alert">
      <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
      {{ errorMessage }}
    </div>

    <section class="safety-banner" aria-labelledby="read-only-title">
      <i class="bi bi-shield-check" aria-hidden="true"></i>
      <div>
        <strong id="read-only-title">{{ t('systemUpdates.readOnlyTitle', 'Safe catalog check') }}</strong>
        <p>{{ t('systemUpdates.readOnlyText', 'Checking reads release metadata only. Installation, downloads and restarts are disabled in this stage.') }}</p>
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
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

type UpdateStatus =
  | 'not_checked'
  | 'no_release'
  | 'manifest_missing'
  | 'update_available'
  | 'up_to_date'
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

const { t } = useI18n()
const status = ref<UpdateCheckResponse | null>(null)
const loading = ref(true)
const checking = ref(false)
const errorMessage = ref('')

const statusLabel = computed(() => status.value ? {
  not_checked: t('systemUpdates.statusNotChecked', 'Not checked yet'),
  no_release: t('systemUpdates.statusNoRelease', 'No published release'),
  manifest_missing: t('systemUpdates.statusManifestMissing', 'Manifest missing'),
  update_available: t('systemUpdates.statusUpdateAvailable', 'Update available'),
  up_to_date: t('systemUpdates.statusUpToDate', 'Up to date'),
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
  current_unknown: 'bi bi-question-circle',
  unsupported_architecture: 'bi bi-cpu',
  error: 'bi bi-exclamation-triangle',
}[status.value.status] : 'bi bi-clock-history')

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

onMounted(loadLocalStatus)
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
.status-icon-up_to_date { background: color-mix(in srgb, var(--accent) 13%, var(--updates-surface)); color: var(--accent); }
.status-icon-error, .status-icon-manifest_missing { background: color-mix(in srgb, var(--danger) 10%, var(--updates-surface)); color: var(--danger); }
.status-label { font-size: .82rem; font-weight: 750; }
.status-update_available { color: var(--color-link); }
.status-up_to_date { color: var(--accent); }
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
.spinning { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .updates-header, .status-card { align-items: stretch; flex-direction: column; }
  .updates-header .button { width: 100%; justify-content: center; }
  .release-grid, .requirements-card { grid-template-columns: 1fr; }
  .requirements-column + .requirements-column { border-top: 1px solid var(--updates-border); border-left: 0; }
}
@media (max-width: 440px) {
  .detail-list { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .spinning { animation: none; }
}
</style>
