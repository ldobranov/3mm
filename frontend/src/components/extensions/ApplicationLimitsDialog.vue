<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { isAxiosError } from 'axios'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import PeerReportLookup from './PeerReportLookup.vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{ moduleId: string; name: string }>()
const emit = defineEmits<{ close: [] }>()
const { t, currentLanguage } = useI18n()
const label = (key: string) => t('applicationLimits.' + key)
const resources = ['memory', 'cpu', 'tasks'] as const
type Resource = typeof resources[number]
type Limit = {
  state: string; reason?: string; max_bytes?: number; max_tasks?: number
  quota_usec?: number; period_usec?: number
}
type Report = {
  state: string; reason?: string; limits?: Partial<Record<Resource, Limit>>
  hierarchy_limits?: Partial<Record<Resource, Limit & { source?: string; complete: boolean }>>
  usage?: { memory_bytes?: number | null; tasks?: number | null }
  supervision?: { state: string; result?: string | null; restart_count?: number | null }
  main_process_fds?: { state: string; soft?: number | 'unlimited'; hard?: number | 'unlimited' }
  service_policy?: { start_burst?: number | null; start_window?: string | null; restart_delay?: string | null;
    stop_timeout?: string | null; private_network?: boolean | null; unix_sockets_only?: boolean | null }
}
const serviceStates = new Set(['active', 'stopped', 'starting', 'stopping', 'restarting', 'failed'])
const serviceResults = new Set(['success', 'resources', 'protocol', 'timeout', 'exit-code', 'signal',
  'core-dump', 'watchdog', 'start-limit-hit', 'oom-kill', 'exit-condition', 'other'])
function serviceState(value: unknown) {
  return typeof value === 'string' && serviceStates.has(value) ? label('service.states.' + value) : label('unavailable')
}
function serviceResult(value: unknown) {
  return typeof value === 'string' && serviceResults.has(value) ? label('service.results.' + value) : label('unavailable')
}
function restartCount(value: unknown) {
  return integer(value) && value < 2 ** 32 ? value.toLocaleString(currentLanguage.value) : label('unavailable')
}
const report = ref<Report | null>(null)
const loading = ref(false)
const errorKey = ref('')
const exporting = ref(false)
const exportStatus = ref('')
const reference = ref('')
const workStatus = ref('')
const workDetail = ref('')
const startBoundaries = new Set(['no_dispatch_record','dispatch_recorded','start_permit_consumed','inconsistent'])
const validReference = computed(() => !reference.value.trim() || /^(task|cmd)_[0-9a-f]{32}$/.test(reference.value.trim()))
const sampledAt = ref<Date | null>(null)
const controller = new AbortController()

async function refresh() {
  if (loading.value || exporting.value) return
  loading.value = true
  exportStatus.value = ''
  report.value = null
  sampledAt.value = null
  errorKey.value = ''
  try {
    const { data } = await http.get(
      '/api/v1/application-extensions/' + encodeURIComponent(props.moduleId) + '/resource-limits',
      { signal: controller.signal, timeout: 15000 },
    )
    if (controller.signal.aborted) return
    if (!data || typeof data.state !== 'string') throw new Error('Invalid resource observation')
    report.value = data
    sampledAt.value = new Date()
  } catch (error) {
    if (controller.signal.aborted) return
    const status = isAxiosError(error) ? error.response?.status : undefined
    errorKey.value = status === 429 ? 'busy' : status === 404 ? 'notInstalled'
      : status === 409 ? 'changed' : status === 403 || status === 401 ? 'denied' : 'unavailable'
  } finally {
    loading.value = false
  }
}
onMounted(refresh)
onBeforeUnmount(() => controller.abort())

async function saveSupport() {
  if (loading.value || exporting.value || !validReference.value) return
  const refId = reference.value.trim()
  exporting.value = true
  exportStatus.value = ''
  workStatus.value = ''
  workDetail.value = ''
  try {
    const { data } = await http.get('/api/v1/application-extensions/' + encodeURIComponent(props.moduleId) + '/support-snapshot',
      { signal: controller.signal, timeout: 15000, ...(refId ? { params: { reference: refId } } : {}) })
    if (controller.signal.aborted) return
    if (data?.kind !== 'application_support' || data.schema_version !== 1 || data.application?.module_id !== props.moduleId
        || !['ready','partial'].includes(data.status) || !Array.isArray(data.cases) || data.cases.length > 100
        || (refId ? data.work?.reference !== refId : data.work !== undefined)) throw new Error()
    let workKey = '', detail = ''
    if (refId) {
      const work = data.work
      if (work.status === 'not_found_in_scope') workKey = 'notFound'
      else if (work.status === 'unavailable') workKey = 'unavailable'
      else if (work.status === 'found' && ['queued','running','succeeded','failed','expired','cancelled','unknown','resolved','delivered'].includes(work.recorded_state))
        workKey = work.recorded_state
      else throw new Error()
      if (work.status === 'found') {
        if (refId.startsWith('task_') && startBoundaries.has(work.start_boundary)) {
          detail = label('support.boundaries.' + work.start_boundary)
        } else if (refId.startsWith('cmd_') && work.delivery) {
          const { recorded_attempts: n, queue_to_latest_offer_seconds: s } = work.delivery
          if (integer(n) && n <= 2147483647 && (s === null || (n > 0 && integer(s) && s <= 31622400))) {
            detail = label('support.offers') + ' ' + n + '. ' +
              (s === null ? label('support.noQueueTime') : label('support.queueTime') + ' ' + s + ' s.') +
              ' ' + label('support.notDeviceTime')
            if (typeof work.delivery.permit_claimed === 'boolean') {
              detail += ' ' + label(work.delivery.permit_claimed ? 'support.permitClaimed' : 'support.permitUnclaimed')
            }
          }
        }
      }
    }
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    try {
      const link = document.createElement('a')
      link.href = url; link.download = 'application-support.json'; link.click()
    } finally { URL.revokeObjectURL(url) }
    exportStatus.value = data.status === 'partial' ? 'partial' : 'saved'
    workStatus.value = workKey
    workDetail.value = detail
  } catch {
    if (!controller.signal.aborted) exportStatus.value = 'failed'
  } finally { exporting.value = false }
}

function observationKey(value: Report | null) {
  if (value?.state === 'not_running') {
    return value.supervision?.state === 'restarting' ? 'restarting' : 'notRunning'
  }
  if (value?.state === 'not_found') return 'noUnit'
  if (value?.state === 'unsupported') return 'unsupported'
  if (value?.reason === 'unit_or_cgroup_changed') return 'changed'
  return 'unavailable'
}

function integer(n: unknown): n is number {
  return typeof n === 'number' && Number.isInteger(n) && n >= 0
}
function fdLimit(value: unknown) {
  if (value === 'unlimited') return label('policy.unlimited')
  return integer(value) ? value.toLocaleString(currentLanguage.value) : label('unavailable')
}
function bytesText(value: unknown) {
  if (!integer(value)) return label('unavailable')
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB']
  let size = value, index = 0
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index++ }
  return size.toLocaleString(currentLanguage.value, { maximumFractionDigits: 2 }) + ' ' + units[index]
}
function limitText(resource: Resource, limit?: Limit) {
  if (limit?.state === 'not_set_here') return label('notSet')
  if (limit?.state !== 'os_enforced') {
    return label(limit?.reason === 'controller_not_available_on_host' ? 'noController' : 'unavailable')
  }
  const locale = currentLanguage.value
  if (resource === 'tasks' && integer(limit.max_tasks)) {
    return (Number.isSafeInteger(limit.max_tasks) ? '' : '≈ ') + limit.max_tasks.toLocaleString(locale)
  }
  if (resource === 'cpu' && integer(limit.quota_usec) && integer(limit.period_usec) && limit.period_usec > 0) {
    return (limit.quota_usec / limit.period_usec).toLocaleString(locale, { style: 'percent', maximumSignificantDigits: 5 })
  }
  if (resource === 'memory') return bytesText(limit.max_bytes)
  return label('unavailable')
}
function hierarchyText(resource: Resource) {
  const limit = report.value?.hierarchy_limits?.[resource]
  if (!limit) return ''
  if (limit.state === 'no_visible_cap') return label('hierarchy.noCap')
  if (limit.state === 'unavailable') {
    return report.value?.limits?.[resource]?.reason === 'controller_not_available_on_host'
      ? '' : label('hierarchy.incomplete')
  }
  const parts = []
  if (limit.source === 'parent') parts.push(label('hierarchy.parent') + ': ' + limitText(resource, limit))
  if (!limit.complete) parts.push(label('hierarchy.incomplete'))
  return parts.join(' · ')
}
</script>

<template>
  <UiDialog open :title="label('title') + ' · ' + props.name" :close-label="label('close')"
    @update:open="!$event && emit('close')">
    <p class="ui-help">{{ label('scope') }}</p>
    <p v-if="loading" role="status">{{ label('reading') }}</p>
    <p v-else-if="errorKey" role="alert">{{ label(errorKey) }}</p>
    <dl v-else-if="report?.state === 'observed'" class="limit-list">
      <div v-for="resource in resources" :key="resource">
        <dt>{{ label(resource) }}</dt><dd>{{ limitText(resource, report.limits?.[resource]) }}
          <small v-if="hierarchyText(resource)" class="hierarchy-note">{{ hierarchyText(resource) }}</small>
        </dd>
      </div>
    </dl>
    <p v-else role="status">{{ label(observationKey(report)) }}</p>
    <section v-if="report?.state === 'observed' && report.usage" class="service-info">
      <h3>{{ label('usage.title') }}</h3>
      <dl class="limit-list">
        <div><dt>{{ label('usage.memory') }}</dt><dd>{{ bytesText(report.usage.memory_bytes) }}</dd></div>
        <div><dt>{{ label('usage.tasks') }}</dt><dd>{{ integer(report.usage.tasks) ? report.usage.tasks.toLocaleString(currentLanguage) : label('unavailable') }}</dd></div>
      </dl>
    </section>
    <section v-if="report?.supervision" class="service-info">
      <h3>{{ label('service.title') }}</h3>
      <dl class="limit-list">
        <div><dt>{{ label('service.state') }}</dt><dd>{{ serviceState(report.supervision.state) }}</dd></div>
        <div><dt>{{ label('service.result') }}</dt><dd>{{ serviceResult(report.supervision.result) }}</dd></div>
        <div><dt>{{ label('service.restarts') }}</dt><dd>{{ restartCount(report.supervision.restart_count) }}</dd></div>
      </dl>
      <p class="ui-help">{{ label('service.hint') }}</p>
    </section>
    <details v-if="report?.service_policy" class="service-info policy">
      <summary>{{ label('policy.title') }}</summary>
      <dl class="limit-list">
        <div><dt>{{ label('policy.fds') }}</dt><dd>{{ report.main_process_fds?.state === 'os_enforced' ? fdLimit(report.main_process_fds.soft) + ' / ' + fdLimit(report.main_process_fds.hard) : label('unavailable') }}</dd></div>
        <div><dt>{{ label('policy.starts') }}</dt><dd>{{ integer(report.service_policy.start_burst) && report.service_policy.start_window ? report.service_policy.start_burst + ' / ' + report.service_policy.start_window : label('unavailable') }}</dd></div>
        <div><dt>{{ label('policy.delay') }}</dt><dd>{{ report.service_policy.restart_delay ?? label('unavailable') }}</dd></div>
        <div><dt>{{ label('policy.stop') }}</dt><dd>{{ report.service_policy.stop_timeout ?? label('unavailable') }}</dd></div>
        <div><dt>{{ label('policy.network') }}</dt><dd>{{ report.service_policy.private_network === true && report.service_policy.unix_sockets_only === true ? label('policy.local') : label('policy.notVerified') }}</dd></div>
      </dl>
      <p class="ui-help">{{ label('policy.scope') }}</p>
    </details>
    <details class="service-info">
      <summary>{{ label('support.trace') }}</summary>
      <label>{{ label('support.reference') }}
        <input v-model="reference" type="text" autocomplete="off" :spellcheck="false" maxlength="37" :disabled="exporting"
          :aria-invalid="!validReference" @input="exportStatus = ''; workStatus = ''">
      </label>
      <p class="ui-help">{{ label(validReference ? 'support.refHelp' : 'support.invalid') }}</p>
    </details>
    <PeerReportLookup :module-id="moduleId" />
    <p v-if="sampledAt" class="ui-help">{{ label('checked') }}: {{ sampledAt.toLocaleTimeString(currentLanguage) }}</p>
    <p v-if="exportStatus" :role="exportStatus === 'failed' ? 'alert' : 'status'">{{ label('support.' + exportStatus) }}</p>
    <p v-if="exportStatus && workStatus" role="status">{{ label('support.record') }} {{ label('support.workStates.' + workStatus) }}</p>
    <p v-if="workStatus && workDetail">{{ workDetail }}</p>
    <template #actions>
      <UiButton @click="emit('close')">{{ label('close') }}</UiButton>
      <UiButton :disabled="loading || exporting || !validReference" @click="saveSupport">{{ label('support.save') }}</UiButton>
      <UiButton :disabled="loading || exporting" @click="refresh">{{ label('refresh') }}</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.limit-list { margin: 1rem 0; }
.limit-list > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: .25rem 1rem; padding: .55rem 0; border-bottom: 1px solid var(--ui-border); }
.limit-list dd { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }
.hierarchy-note { display: block; font-weight: normal; }
.service-info h3 { margin: 1rem 0 .25rem; font-size: 1rem; }
.service-info .limit-list { margin: 0; }
.policy { margin-top: 1rem; }
.policy summary { cursor: pointer; }
</style>
