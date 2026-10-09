<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import AuthorityReview from './AuthorityReview.vue'
import type { AuthorityInspection } from './authority-review'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{ file: File | null; disabled?: boolean }>()
const { t } = useI18n()
interface Inspection {
  inspection_version: 1
  module_id: string
  version: string
  sha256: string
  size_bytes: number
  package_kind: string
  manifest: {
    name: string
    runtimes: string[]
    permissions: string[]
    capabilities: { provides: string[]; consumes: string[] }
  }
  descriptors: Record<string, unknown>
  catalog: { status: 'new' | 'exact_artifact' | 'version_conflict'; existing_sha256: string | null }
  compatibility: { core: 'matched' | 'not_checked'; core_version: string }
  authority_review?: AuthorityInspection | null
}
const inspection = ref<Inspection | null>(null)
const busy = ref(false)
const error = ref('')
let generation = 0
let controller: AbortController | null = null
const reset = () => {
  ++generation
  controller?.abort()
  controller = null
  inspection.value = null
  error.value = ''
  busy.value = false
}
watch(() => props.file, reset, { flush: 'sync' })
onBeforeUnmount(reset)
const catalogLabel = computed(() => {
  switch (inspection.value?.catalog.status) {
    case 'new': return t('packageInspection.new', 'New package — not in the catalog')
    case 'exact_artifact': return t('packageInspection.exact', 'This exact package is already in the catalog')
    case 'version_conflict': return t('packageInspection.conflict', 'Version conflict — this ID/version has different contents in the catalog')
    default: return ''
  }
})
const inspect = async () => {
  const file = props.file
  if (!file || props.disabled || busy.value) return
  reset()
  if (!file.size || file.size > 10 * 1024 * 1024) {
    error.value = t('packageInspection.sizeLimit', 'Choose a non-empty ZIP no larger than 10 MiB.')
    return
  }
  const requestGeneration = generation
  controller = new AbortController()
  busy.value = true
  try {
    // Raw bytes bypass JSON transformation and multipart temporary-file spooling.
    const response = await http.post('/api/v1/modules/packages/inspect', file, {
      headers: { 'Content-Type': 'application/zip' },
      transformRequest: [(body: unknown) => body],
      signal: controller.signal,
      params: { include_authority_review: true },
    })
    if (requestGeneration !== generation) return
    if (response.data?.inspection_version !== 1) throw new Error('Unsupported inspection response')
    inspection.value = response.data as Inspection
  } catch (cause: unknown) {
    if (requestGeneration !== generation) return
    const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    error.value = typeof detail === 'string'
      ? detail : t('packageInspection.failed', 'The package could not be inspected. Nothing was installed.')
  } finally {
    if (requestGeneration === generation) {
      busy.value = false
      controller = null
    }
  }
}
</script>

<template>
  <section class="package-inspection ui-stack" :aria-label="t('packageInspection.title', 'Package inspection')">
    <div class="inspection-toolbar">
      <UiButton :disabled="!file || disabled" :loading="busy" @click="inspect">
        <i class="bi bi-search" aria-hidden="true"></i>
        {{ t('packageInspection.inspect', 'Inspect package') }}
      </UiButton>
      <small class="ui-help">{{ t('packageInspection.help', 'Read-only review of manifest-v2 ZIP packages. No installation or code execution; legacy packages are not supported here.') }}</small>
    </div>
    <p v-if="error" class="inspection-error" role="alert">{{ error }}</p>
    <div v-if="inspection" class="inspection-result ui-stack" aria-live="polite">
      <h3>{{ inspection.manifest.name }} · {{ inspection.version }}</h3>
      <p :class="{ 'inspection-error': inspection.catalog.status === 'version_conflict' }">{{ catalogLabel }}</p>
      <dl class="inspection-facts">
        <div><dt>{{ t('packageInspection.identity', 'Package ID') }}</dt><dd>{{ inspection.module_id }}</dd></div>
        <div><dt>{{ t('packageInspection.kind', 'Package type / runtimes') }}</dt><dd>{{ inspection.package_kind }} / {{ inspection.manifest.runtimes.join(', ') }}</dd></div>
        <div><dt>SHA-256</dt><dd class="inspection-digest">{{ inspection.sha256 }}</dd></div>
        <div><dt>{{ t('packageInspection.size', 'Size') }}</dt><dd>{{ (inspection.size_bytes / 1024).toFixed(1) }} KiB</dd></div>
        <div><dt>{{ t('packageInspection.core', 'Core compatibility') }}</dt><dd>{{ inspection.compatibility.core === 'matched'
          ? t('packageInspection.coreMatched', 'Requirement matches the running Core') + ' · ' + inspection.compatibility.core_version
          : t('packageInspection.notChecked', 'Not checked') }}</dd></div>
        <div><dt>{{ t('packageInspection.device', 'Device / Agent compatibility') }}</dt><dd>{{ t('packageInspection.notChecked', 'Not checked') }}</dd></div>
        <div><dt>{{ t('packageInspection.permissions', 'Declared permissions — not approved') }}</dt><dd>{{ inspection.manifest.permissions.join(', ') || '—' }}</dd></div>
        <div><dt>{{ t('packageInspection.provides', 'Provides capabilities') }}</dt><dd>{{ inspection.manifest.capabilities.provides.join(', ') || '—' }}</dd></div>
        <div><dt>{{ t('packageInspection.consumes', 'Consumes capabilities') }}</dt><dd>{{ inspection.manifest.capabilities.consumes.join(', ') || '—' }}</dd></div>
      </dl>
      <p class="inspection-notice">{{ t('packageInspection.warning', 'Publisher and signature are not verified. Dependencies and conflicts are declared, not resolved. Inspection is not approval and does not guarantee installation; uploading remains a separate action.') }}</p>
      <AuthorityReview v-if="inspection.package_kind === 'application'" :value="inspection.authority_review" />
      <details>
        <summary>{{ t('packageInspection.declarations', 'All declarations, configuration and runtime descriptors') }}</summary>
        <pre>{{ JSON.stringify({ manifest: inspection.manifest, descriptors: inspection.descriptors }, null, 2) }}</pre>
      </details>
    </div>
  </section>
</template>

<style scoped>
.package-inspection { margin-top: calc(var(--ui-space) * 4); min-width: 0; }
.inspection-toolbar { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); }
.inspection-toolbar > button { flex-shrink: 0; }
.inspection-result { padding-top: calc(var(--ui-space) * 4); border-top: 1px solid var(--ui-border); }
.inspection-result h3, .inspection-result p, .inspection-facts { margin: 0; }
.inspection-result h3 { font-size: 1.05rem; font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.inspection-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 4); }
.inspection-facts dt { color: var(--ui-text-secondary); font-size: .85em; }
.inspection-facts dd { margin: calc(var(--ui-space) * 1) 0 0; overflow-wrap: anywhere; }
.inspection-digest { font-family: monospace; font-size: .85em; }
.inspection-error { color: var(--ui-danger); overflow-wrap: anywhere; }
.inspection-notice { color: var(--ui-text-secondary); border-left: 3px solid var(--ui-border); padding-left: calc(var(--ui-space) * 3); }
summary { cursor: pointer; color: var(--ui-accent); }
pre { max-height: 24rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--ui-text); background: var(--ui-surface-alt); padding: calc(var(--ui-space) * 3); }
@media (max-width: 720px) {
  .inspection-toolbar { align-items: stretch; flex-direction: column; }
  .inspection-facts { grid-template-columns: minmax(0, 1fr); }
}
</style>
