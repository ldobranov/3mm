<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import http from '@/utils/dynamic-http'
import { useAuthorityLabels, type AuthorityLabel } from './authority-labels'
import { authorityRequestId, readAuthorityStatus, readAuthorityPlan, readAuthorityDecision,
  type AuthorityStatus, type AuthorityPlan, type Decision } from './authority-management'

const props = defineProps<{ moduleId: string; name: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const label = useAuthorityLabels()
const inputId = useId()
const base = `/api/v1/application-extensions/${encodeURIComponent(props.moduleId)}/authority`
const status = ref<AuthorityStatus | null>(null)
const plan = ref<AuthorityPlan | null>(null)
// A changed selection keeps the public cards, never an approvable old plan.
const peerDraft = ref<AuthorityPlan | null>(null)
const selectedPeers = ref<string[]>([])
const peerReview = computed(() => plan.value || peerDraft.value)
const nativeId = ref('')
const busy = ref(false)
const acknowledged = ref(false)
const error = ref<AuthorityLabel | null>(null)
const notice = ref<AuthorityLabel | null>(null)
const confirmRevoke = ref(false)
const now = ref(Date.now())
let deadline = 0
let generation = 0
const timer = setInterval(() => { now.value = Date.now() }, 1000)
onBeforeUnmount(() => { ++generation; clearInterval(timer) })
const remaining = computed(() => Math.max(0, Math.ceil((deadline - now.value) / 1000)))
const expired = computed(() => !!plan.value && remaining.value === 0)
const adoptionBlocked = computed(() => status.value?.mode === 'compatibility'
  && (status.value.installation_enabled || status.value.installation_status !== 'disabled'))
const reviewAvailable = computed(() => !!status.value && status.value.review_available !== false)
const canReview = computed(() => reviewAvailable.value && !!nativeId.value && !busy.value)
const canDecide = computed(() => !!plan.value && !busy.value && !expired.value)
const canRevoke = computed(() => reviewAvailable.value && status.value?.grant_state === 'active' && !!status.value.grant_record_revision && !busy.value)
const relationalUnconfirmed = computed(() => status.value?.runtime_blockers?.includes('relational_runtime_unavailable') === true)
const peerUnconfirmed = computed(() => status.value?.runtime_blockers?.includes('peer_read_runtime_unavailable') === true)
const statusLabel = computed(() => !reviewAvailable.value && status.value?.mode !== 'compatibility' ? 'statusOnly'
  : status.value?.mode === 'compatibility' ? 'compatAccess' : status.value?.grant_effective ? 'effective'
  : status.value?.grant_state !== 'active' ? 'stale' : !status.value.installation_enabled ? 'inactive'
  : peerUnconfirmed.value ? 'peerUnconfirmed' : relationalUnconfirmed.value ? 'relationalUnconfirmed' : 'stale')

function clearReview() { plan.value = null; peerDraft.value = null; acknowledged.value = false; deadline = 0; confirmRevoke.value = false }
function selectPeer(scope: string, event: Event) {
  const reviewed = peerReview.value
  if (!reviewed || busy.value || reviewed.state !== 'review_required'
    || !status.value?.scopes.includes(scope)) return
  const checked = (event.target as HTMLInputElement).checked
  selectedPeers.value = checked ? [...new Set([...selectedPeers.value, scope])] : selectedPeers.value.filter(item => item !== scope)
  clearReview(); peerDraft.value = reviewed; notice.value = null; error.value = null
}
function failure(cause: unknown, mutation = false): AuthorityLabel {
  const response = (cause as { response?: { status?: number; data?: { detail?: { code?: string } } } })?.response
  switch (response?.data?.detail?.code) {
    case 'actor_unavailable': return 'actor'
    case 'stale_review': case 'stale_grant': case 'grant_not_current': case 'request_conflict': return 'staleReview'
    case 'disabled_adoption_required': return 'adoption'
    case 'native_review_unavailable': case 'record_unavailable': return 'noNative'
    case 'unsupported_authority': case 'staged_authority_not_supported': return 'unsupported'
    default: return response?.status === 401 || response?.status === 403 ? 'actor'
      : mutation && !response ? 'uncertain' : 'unavailable'
  }
}
async function loadStatus(currentGeneration = generation) {
  const response = await http.get(base, { timeout: 12000 })
  if (currentGeneration !== generation) return
  const current = readAuthorityStatus(response.data)
  status.value = current
  selectedPeers.value = [] // Every fresh status begins with explicit opt-in.
  if (!current.native_reviews.some(item => item.native_review_id === nativeId.value)) {
    nativeId.value = current.native_reviews[0]?.native_review_id || ''
  }
}
async function refresh() {
  if (busy.value) return
  clearReview(); error.value = null; notice.value = null; busy.value = true
  const current = generation
  try { await loadStatus(current) }
  catch (cause) { if (current === generation) { status.value = null; error.value = failure(cause) } }
  finally { if (current === generation) busy.value = false }
}
async function createReview() {
  if (!canReview.value || !status.value) return
  const requested = status.value.scopes.filter(scope => !scope.startsWith('peer:') || selectedPeers.value.includes(scope))
  clearReview(); error.value = null; notice.value = null; busy.value = true
  const current = generation, started = Date.now()
  try {
    const response = await http.post(base + '/reviews', {
      request_id: authorityRequestId(), native_review_id: nativeId.value, scopes: requested,
    }, { timeout: 12000 })
    if (current !== generation) return
    plan.value = readAuthorityPlan(response.data, status.value, props.moduleId, requested)
    deadline = started + plan.value.expires_in_seconds * 1000
    now.value = Date.now()
  } catch (cause) { if (current === generation) { clearReview(); error.value = failure(cause, true) } }
  finally { if (current === generation) busy.value = false }
}
async function decide(decision: Decision) {
  const reviewed = plan.value
  if (!reviewed || !canDecide.value || (decision === 'approve' && !acknowledged.value)
    || (decision !== 'apply' && reviewed.state !== 'review_required')
    || (decision === 'apply' && (reviewed.state !== 'approved_pending_apply' || adoptionBlocked.value))) return
  busy.value = true; error.value = null; notice.value = null
  const current = generation
  try {
    const response = await http.post(`${base}/reviews/${reviewed.plan_id}/${decision}`, {
      request_id: authorityRequestId(), expected_revision: reviewed.revision, fingerprint: reviewed.fingerprint,
    }, { timeout: 12000 })
    if (current !== generation) return
    plan.value = readAuthorityDecision(response.data, reviewed, decision)
    if (decision === 'approve') { notice.value = 'pending'; return }
    clearReview()
    notice.value = decision === 'apply' ? 'applied' : 'denied'
    if (decision === 'apply') emit('changed')
    await loadStatus(current)
  } catch (cause) {
    if (current === generation) {
      clearReview(); status.value = null; error.value = failure(cause, true)
    }
  } finally { if (current === generation) busy.value = false }
}
async function revoke() {
  if (!canRevoke.value || !confirmRevoke.value || !status.value) return
  busy.value = true; error.value = null; notice.value = null
  const current = generation
  try {
    const response = await http.post(base + '/revoke', { request_id: authorityRequestId(),
      expected_revision: status.value.grant_record_revision }, { timeout: 12000 })
    if (current !== generation) return
    if (response.data?.state !== 'revoked' || response.data.historical || response.data.replayed) {
      throw new Error('Unconfirmed revocation')
    }
    clearReview(); notice.value = 'revoked'; emit('changed')
    await loadStatus(current)
  } catch (cause) {
    if (current === generation) { clearReview(); status.value = null; error.value = failure(cause, true) }
  } finally { if (current === generation) busy.value = false }
}
function close() { if (!busy.value) emit('close') }
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
function resourceTitle(resource: unknown): string {
  const declaration = record(record(resource).declaration)
  return String(declaration.binding_id || declaration.connector_id || declaration.subscription_id || declaration.publication_id || '—')
}
function resourceDetails(resource: unknown, kind: 'commands' | 'connectors' | 'events' | 'publications'): string {
  const value = record(resource), declaration = record(value.declaration)
  // Core-redacted fields only. Keep exact limits/schema visible, not private config.
  return JSON.stringify(kind === 'commands'
    ? { device: value.target_device_id, sensor_device: value.sensor_device_id ?? null, ...declaration }
    : kind === 'events' ? { device: value.source_device_id, ...declaration, handler: value.handler }
    : kind === 'publications' ? { ...declaration, operation: value.operation, service_artifact_sha256: value.service_artifact_sha256 }
    : { origin: record(value.stored).destination_origin, ...declaration,
        credential: record(value.stored).credential ? {
          reference: record(record(value.stored).credential).secret_ref,
          version: record(record(value.stored).credential).version,
          kind: record(record(value.stored).credential).credential_kind,
        } : null }, null, 2)
}
onMounted(refresh)
</script>

<template>
  <UiDialog :open="true" class="authority-dialog" :title="label('title')" :close-label="label('close')" @update:open="!$event && close()">
    <div class="authority-body ui-stack" :aria-busy="busy">
      <div class="authority-intro"><h3>{{ name }}</h3><p class="ui-help">{{ label('help') }}</p></div>
      <p class="authority-note">{{ label('nativeOnly') }}</p>
      <p v-if="error" class="authority-error" role="alert">{{ label(error) }}</p>
      <p v-if="notice" class="authority-notice" role="status">{{ label(notice) }}</p>
      <p v-if="busy" class="ui-help" role="status">{{ label('loading') }}</p>
      <template v-if="status">
        <div class="authority-status" aria-live="polite">
          <span class="ui-badge">{{ label(status.mode) }}</span>
          <span class="ui-badge" :class="{ 'authority-effective': status.grant_effective }">{{ label(statusLabel) }}</span>
        </div>
        <div class="authority-artifact"><span class="ui-help">{{ label('digest') }}</span><code>{{ status.artifact_sha256 }}</code></div>
        <p v-for="blocker in status.review_blockers || []" :key="blocker" class="authority-note" role="status">{{ label(blocker === 'review_key_unavailable' ? 'reviewKeyUnavailable' : 'unsupportedStatus') }}</p>
        <p v-if="relationalUnconfirmed" class="authority-note authority-runtime" role="status">{{ label('relationalRuntime') }}</p>
        <p v-if="peerUnconfirmed" class="authority-note authority-runtime" role="status">{{ label('peerRuntime') }}</p>
        <p v-if="reviewAvailable && status.mode === 'compatibility'" class="authority-note">{{ label(adoptionBlocked ? 'adoption' : 'adoptionReady') }}</p>
        <p v-if="reviewAvailable && !status.native_reviews.length" class="ui-help">{{ label('noNative') }}</p>
        <div v-else-if="reviewAvailable" class="authority-chooser ui-field">
          <label :for="inputId">{{ label('nativeReview') }}</label>
          <select :id="inputId" class="ui-control" v-model="nativeId" :disabled="busy || !!plan" @change="clearReview">
            <option v-for="review in status.native_reviews" :key="review.native_review_id" :value="review.native_review_id">{{ review.native_review_id }}</option>
          </select>
          <UiButton v-if="!plan" class="authority-create" :disabled="!canReview" @click="createReview">{{ label(peerDraft ? 'reviewSelection' : 'create') }}</UiButton>
        </div>
      </template>
      <section v-if="peerReview?.resources.peer_reads?.length" class="authority-resources authority-peer-choices" :aria-label="label('peerReads')">
        <h4>{{ label('peerReads') }}</h4>
        <p class="ui-help">{{ label('peerBoundary') }}</p>
        <p class="ui-help">{{ label('peerSelection') }}</p>
        <p v-if="peerDraft" class="authority-note" role="status">{{ label('selectionChanged') }}</p>
        <article v-for="peer in peerReview.resources.peer_reads" :key="peer.declaration.binding_id" class="authority-resource authority-peer-read">
          <label class="ui-check authority-peer-choice">
            <input type="checkbox" :checked="selectedPeers.includes(`peer:${peer.declaration.binding_id}:read`)"
              :disabled="busy || peerReview.state !== 'review_required' || !!plan && expired"
              @change="selectPeer(`peer:${peer.declaration.binding_id}:read`, $event)" />
            <span>{{ label('peerRead') }} · <code>{{ peer.declaration.binding_id }}</code></span>
          </label>
          <span class="ui-badge authority-peer-selection">{{ label(selectedPeers.includes(`peer:${peer.declaration.binding_id}:read`) ? 'peerSelected' : 'peerUnselected') }}</span>
          <code>peer:{{ peer.declaration.binding_id }}:read</code>
          <dl class="authority-file-limits">
            <dt>{{ label('fileOwner') }}</dt><dd>{{ peer.owner.module_id }} · #{{ peer.owner.application_installation_id }}</dd>
            <dt>{{ label('peerDirection') }}</dt><dd>{{ label('peerOutbound') }}</dd>
            <dt>{{ label('statusLink') }}</dt><dd><code>{{ peer.peer_id }}</code></dd>
            <dt>{{ label('statusReceiver') }}</dt><dd><code>{{ peer.receiver_identity.installation_id }}</code></dd>
            <dt>{{ label('statusOrigin') }}</dt><dd><code>{{ peer.origin }}</code></dd>
            <dt>{{ label('statusTarget') }}</dt><dd><code>{{ peer.target_module_id }}</code></dd>
            <dt>{{ label('statusRevision') }}</dt><dd>{{ peer.consent_revision }}</dd>
            <dt>{{ label('statusSummary') }}</dt><dd>{{ peer.consent.summary_fields.join(', ') || label('statusNone') }}</dd>
            <dt>{{ label('statusNodes') }}</dt><dd><ul v-if="peer.consent.node_ids.length" class="authority-status-nodes"><li v-for="node in peer.consent.node_ids" :key="node"><code>{{ node }}</code></li></ul><span v-else>{{ label('statusNone') }}</span></dd>
            <dt>{{ label('statusFields') }}</dt><dd>{{ peer.consent.node_fields.join(', ') || label('statusNone') }}</dd>
          </dl>
          <details class="authority-file-binding">
            <summary tabindex="0">{{ label('fileBinding') }}</summary>
            <dl class="authority-file-limits">
              <dt>{{ label('peerVersion') }}</dt><dd>{{ peer.peer_version }}</dd>
              <dt>{{ label('peerConfig') }}</dt><dd><code>{{ peer.declaration.peer_id_config_key }}</code></dd>
              <dt>{{ label('fileCore') }}</dt><dd><code>{{ peer.owner.core_installation_id }}</code></dd>
              <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ peer.owner.incarnation }}</code></dd>
              <dt>{{ label('statusInstance') }}</dt><dd><code>{{ peer.application_instance_id }}</code></dd>
              <dt>{{ label('digest') }}</dt><dd><code>{{ peer.package_artifact_sha256 }}</code></dd>
              <dt>{{ label('serviceDigest') }}</dt><dd><code>{{ peer.service_artifact_sha256 }}</code></dd>
              <template v-if="peer.enrollment_metadata">
                <dt>{{ label('peerIntent') }}</dt><dd><code>{{ peer.enrollment_metadata.application_intent }}</code></dd>
                <dt>{{ label('peerMetadataHash') }}</dt><dd><code>{{ peer.enrollment_metadata.metadata_hash }}</code></dd>
              </template>
            </dl>
            <template v-for="pin in (['sender_identity', 'receiver_identity'] as const)" :key="pin">
              <h6 class="authority-pin-heading">{{ label(pin === 'sender_identity' ? 'statusSender' : 'statusReceiverIdentity') }}</h6>
              <dl class="authority-file-limits">
                <dt>{{ label('identityVersion') }}</dt><dd>{{ peer[pin].identity_version }}</dd>
                <dt>{{ label('fileCore') }}</dt><dd><code>{{ peer[pin].installation_id }}</code></dd>
                <dt>{{ label('identityAlgorithm') }}</dt><dd>{{ peer[pin].algorithm }}</dd>
                <dt>{{ label('identityKeyId') }}</dt><dd><code>{{ peer[pin].key_id }}</code></dd>
                <dt>{{ label('identityPublicKey') }}</dt><dd><code>{{ peer[pin].public_key }}</code></dd>
                <dt>{{ label('identityGeneration') }}</dt><dd>{{ peer[pin].key_generation }}</dd>
                <dt>{{ label('identityCreated') }}</dt><dd><code>{{ peer[pin].created_at }}</code></dd>
              </dl>
            </template>
          </details>
        </article>
        <UiButton v-if="peerDraft" class="authority-create" :disabled="!canReview" @click="createReview">{{ label('reviewSelection') }}</UiButton>
      </section>
      <section v-if="plan" class="authority-review-plan ui-stack" :aria-label="label('review')">
        <div class="authority-review-heading"><h3>{{ label('review') }}</h3><small class="ui-help">{{ label('expires') }} {{ remaining }} {{ label('seconds') }}</small></div>
        <p class="ui-help">{{ label(plan.resources.peer_reads?.length ? 'peerSelection' : 'fullBindings') }}</p>
        <p v-if="expired" class="authority-error" role="alert">{{ label('expired') }}</p>
        <template v-for="kind in (['commands', 'connectors', 'events', 'publications'] as const)" :key="kind">
          <div v-if="plan.resources[kind]?.length" class="authority-resources">
            <h4>{{ label(kind) }}</h4>
            <article v-for="(resource, index) in plan.resources[kind]" :key="index" class="authority-resource">
              <h5>{{ resourceTitle(resource) }}</h5><pre>{{ resourceDetails(resource, kind) }}</pre>
            </article>
          </div>
        </template>
        <div v-if="plan.resources.private_files?.length" class="authority-resources">
          <h4>{{ label('privateFiles') }}</h4>
          <p class="ui-help">{{ label('fileBoundary') }}</p>
          <article v-for="file in plan.resources.private_files" :key="file.operation" class="authority-resource authority-file">
            <h5>{{ label(file.operation === 'read' ? 'fileRead' : 'fileWrite') }}</h5>
            <code>storage:private_files_{{ file.operation }}</code>
            <dl class="authority-file-limits">
              <dt>{{ label('fileOwner') }}</dt><dd>{{ file.owner.module_id }} · #{{ file.owner.application_installation_id }}</dd>
              <dt>{{ label('fileNamespace') }}</dt><dd>{{ file.declaration.namespace }}</dd>
              <dt>{{ label('fileMode') }}</dt><dd>{{ label(file.declaration.mode === 'read' ? 'fileReadOnly' : 'fileReadWrite') }}</dd>
              <dt>{{ label('fileMaximum') }}</dt><dd>{{ file.declaration.max_file_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('fileTotal') }}</dt><dd>{{ file.declaration.max_total_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('fileCount') }}</dt><dd>{{ file.declaration.max_files }}</dd>
            </dl>
            <details class="authority-file-binding">
              <summary tabindex="0">{{ label('fileBinding') }}</summary>
              <dl class="authority-file-limits">
                <dt>{{ label('fileCore') }}</dt><dd><code>{{ file.owner.core_installation_id }}</code></dd>
                <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ file.owner.incarnation }}</code></dd>
                <dt>{{ label('digest') }}</dt><dd><code>{{ file.package_artifact_sha256 }}</code></dd>
              </dl>
            </details>
          </article>
        </div>
        <div v-if="plan.resources.relational?.length" class="authority-resources">
          <h4>{{ label('relational') }}</h4>
          <p class="ui-help">{{ label('relationalBoundary') }}</p>
          <article v-for="database in plan.resources.relational" :key="database.operation" class="authority-resource authority-relational">
            <h5>{{ label(database.operation === 'read' ? 'relationalRead' : 'relationalWrite') }}</h5>
            <code>storage:relational_{{ database.operation }}</code>
            <dl class="authority-file-limits">
              <dt>{{ label('fileOwner') }}</dt><dd>{{ database.owner.module_id }} · #{{ database.owner.application_installation_id }}</dd>
              <dt>{{ label('fileMode') }}</dt><dd>{{ label(database.declaration.mode === 'read' ? 'fileReadOnly' : 'fileReadWrite') }}</dd>
              <dt>{{ label('relationalSchema') }}</dt><dd><code>{{ database.schema_revision }}</code></dd>
              <dt>{{ label('relationalMigration') }}</dt><dd><code>{{ database.migration_entrypoint }}</code></dd>
              <dt>{{ label('relationalProfile') }}</dt><dd><code>{{ database.resource_profile }}</code></dd>
              <dt>{{ label('relationalContract') }}</dt><dd>{{ database.declaration.contract_version }}</dd>
              <dt>{{ label('relationalLimits') }}</dt><dd><code>{{ database.declaration.limit_class }}</code></dd>
              <dt>{{ label('relationalDatabase') }}</dt><dd>{{ database.declaration.max_database_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('relationalAuxiliary') }}</dt><dd>{{ database.declaration.auxiliary_pause_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('relationalStatement') }}</dt><dd>{{ database.declaration.max_statement_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('relationalValue') }}</dt><dd>{{ database.declaration.max_value_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('relationalResult') }}</dt><dd>{{ database.declaration.max_result_bytes }} {{ label('fileBytes') }}</dd>
              <dt>{{ label('relationalRows') }}</dt><dd>{{ database.declaration.max_result_rows }}</dd>
              <dt>{{ label('relationalTransaction') }}</dt><dd>{{ database.declaration.max_transaction_ms }} {{ label('milliseconds') }}</dd>
              <dt>{{ label('relationalBusy') }}</dt><dd>{{ database.declaration.max_busy_ms }} {{ label('milliseconds') }}</dd>
            </dl>
            <details class="authority-file-binding">
              <summary tabindex="0">{{ label('fileBinding') }}</summary>
              <dl class="authority-file-limits">
                <dt>{{ label('fileCore') }}</dt><dd><code>{{ database.owner.core_installation_id }}</code></dd>
                <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ database.owner.incarnation }}</code></dd>
                <dt>{{ label('digest') }}</dt><dd><code>{{ database.package_artifact_sha256 }}</code></dd>
                <dt>{{ label('serviceDigest') }}</dt><dd><code>{{ database.service_artifact_sha256 }}</code></dd>
              </dl>
            </details>
          </article>
        </div>
        <div v-if="plan.resources.checkpoints?.length" class="authority-resources">
          <h4>{{ label('checkpoints') }}</h4>
          <p class="ui-help">{{ label('checkpointBoundary') }}</p>
          <article v-for="checkpoint in plan.resources.checkpoints" :key="`${checkpoint.declaration.checkpoint_id}:${checkpoint.operation}`" class="authority-resource authority-checkpoint">
            <h5>{{ label(checkpoint.operation === 'read' ? 'checkpointRead' : 'checkpointWrite') }} · {{ checkpoint.declaration.checkpoint_id }}</h5>
            <code>checkpoint:{{ checkpoint.declaration.checkpoint_id }}:{{ checkpoint.operation }}</code>
            <dl class="authority-file-limits">
              <dt>{{ label('checkpointId') }}</dt><dd><code>{{ checkpoint.declaration.checkpoint_id }}</code></dd>
              <dt>{{ label('fileOwner') }}</dt><dd>{{ checkpoint.owner.module_id }} · #{{ checkpoint.owner.application_installation_id }}</dd>
              <dt>{{ label('fileMode') }}</dt><dd>{{ label(checkpoint.declaration.mode === 'read' ? 'fileReadOnly' : 'fileReadWrite') }}</dd>
              <dt>{{ label('relationalContract') }}</dt><dd>{{ checkpoint.declaration.contract_version }}</dd>
              <dt>{{ label('checkpointMaximum') }}</dt><dd>{{ checkpoint.declaration.max_value_bytes }} {{ label('fileBytes') }}</dd>
            </dl>
            <details class="authority-file-binding">
              <summary tabindex="0">{{ label('fileBinding') }}</summary>
              <dl class="authority-file-limits">
                <dt>{{ label('fileCore') }}</dt><dd><code>{{ checkpoint.owner.core_installation_id }}</code></dd>
                <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ checkpoint.owner.incarnation }}</code></dd>
                <dt>{{ label('digest') }}</dt><dd><code>{{ checkpoint.package_artifact_sha256 }}</code></dd>
              </dl>
            </details>
          </article>
        </div>
        <div v-if="plan.resources.identities?.length" class="authority-resources">
          <h4>{{ label('identities') }}</h4>
          <p class="ui-help">{{ label('identityBoundary') }}</p>
          <article v-for="identityResource in plan.resources.identities" :key="identityResource.operation" class="authority-resource authority-identity">
            <h5>{{ label('identityRead') }}</h5>
            <code>platform:{{ identityResource.operation }}</code>
            <dl class="authority-file-limits">
              <dt>{{ label('fileOwner') }}</dt><dd>{{ identityResource.owner.module_id }} · #{{ identityResource.owner.application_installation_id }}</dd>
              <dt>{{ label('identityVersion') }}</dt><dd>{{ identityResource.identity.identity_version }}</dd>
              <dt>{{ label('fileCore') }}</dt><dd><code>{{ identityResource.identity.installation_id }}</code></dd>
              <dt>{{ label('identityAlgorithm') }}</dt><dd><code>{{ identityResource.identity.algorithm }}</code></dd>
              <dt>{{ label('identityKeyId') }}</dt><dd><code>{{ identityResource.identity.key_id }}</code></dd>
              <dt>{{ label('identityPublicKey') }}</dt><dd><code>{{ identityResource.identity.public_key }}</code></dd>
              <dt>{{ label('identityGeneration') }}</dt><dd>{{ identityResource.identity.key_generation }}</dd>
              <dt>{{ label('identityCreated') }}</dt><dd><code>{{ identityResource.identity.created_at }}</code></dd>
            </dl>
            <details class="authority-file-binding">
              <summary tabindex="0">{{ label('fileBinding') }}</summary>
              <dl class="authority-file-limits">
                <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ identityResource.owner.incarnation }}</code></dd>
                <dt>{{ label('digest') }}</dt><dd><code>{{ identityResource.package_artifact_sha256 }}</code></dd>
              </dl>
            </details>
          </article>
        </div>
        <div v-if="plan.resources.status_projections?.length" class="authority-resources">
          <h4>{{ label('statusProjections') }}</h4>
          <p class="ui-help">{{ label('statusBoundary') }}</p>
          <article v-for="projection in plan.resources.status_projections" :key="projection.link_id" class="authority-resource authority-status-projection">
            <h5>{{ label('statusRead') }}</h5>
            <code>status:{{ projection.link_id }}:read</code>
            <dl class="authority-file-limits">
              <dt>{{ label('fileOwner') }}</dt><dd>{{ projection.owner.module_id }} · #{{ projection.owner.application_installation_id }}</dd>
              <dt>{{ label('statusReceiver') }}</dt><dd><code>{{ projection.receiver_identity.installation_id }}</code></dd>
              <dt>{{ label('statusOrigin') }}</dt><dd><code>{{ projection.origin }}</code></dd>
              <dt>{{ label('statusTarget') }}</dt><dd><code>{{ projection.target_module_id }}</code></dd>
              <dt>{{ label('statusRevision') }}</dt><dd>{{ projection.consent_revision }}</dd>
              <dt>{{ label('statusSummary') }}</dt><dd>{{ projection.consent.summary_fields.join(', ') || label('statusNone') }}</dd>
              <dt>{{ label('statusNodes') }}</dt><dd><ul v-if="projection.consent.node_ids.length" class="authority-status-nodes"><li v-for="node in projection.consent.node_ids" :key="node"><code>{{ node }}</code></li></ul><span v-else>{{ label('statusNone') }}</span></dd>
              <dt>{{ label('statusFields') }}</dt><dd>{{ projection.consent.node_fields.join(', ') || label('statusNone') }}</dd>
            </dl>
            <details class="authority-file-binding">
              <summary tabindex="0">{{ label('fileBinding') }}</summary>
              <dl class="authority-file-limits">
                <dt>{{ label('statusLink') }}</dt><dd><code>{{ projection.link_id }}</code></dd>
                <dt>{{ label('fileCore') }}</dt><dd><code>{{ projection.owner.core_installation_id }}</code></dd>
                <dt>{{ label('fileIncarnation') }}</dt><dd><code>{{ projection.owner.incarnation }}</code></dd>
                <dt>{{ label('statusInstance') }}</dt><dd><code>{{ projection.application_instance_id }}</code></dd>
                <dt>{{ label('digest') }}</dt><dd><code>{{ projection.package_artifact_sha256 }}</code></dd>
              </dl>
              <template v-for="pin in (['sender_identity', 'receiver_identity'] as const)" :key="pin">
                <h6 class="authority-pin-heading">{{ label(pin === 'sender_identity' ? 'statusSender' : 'statusReceiverIdentity') }}</h6>
                <dl class="authority-file-limits">
                  <dt>{{ label('identityVersion') }}</dt><dd>{{ projection[pin].identity_version }}</dd>
                  <dt>{{ label('fileCore') }}</dt><dd><code>{{ projection[pin].installation_id }}</code></dd>
                  <dt>{{ label('identityAlgorithm') }}</dt><dd>{{ projection[pin].algorithm }}</dd>
                  <dt>{{ label('identityKeyId') }}</dt><dd><code>{{ projection[pin].key_id }}</code></dd>
                  <dt>{{ label('identityPublicKey') }}</dt><dd><code>{{ projection[pin].public_key }}</code></dd>
                  <dt>{{ label('identityGeneration') }}</dt><dd>{{ projection[pin].key_generation }}</dd>
                  <dt>{{ label('identityCreated') }}</dt><dd><code>{{ projection[pin].created_at }}</code></dd>
                </dl>
              </template>
            </details>
          </article>
        </div>
        <p v-if="!plan.scopes.length" class="ui-help">{{ label(plan.resources.peer_reads?.length ? 'peerEmpty' : 'empty') }}</p>
        <label v-if="plan.state === 'review_required'" class="ui-check authority-acknowledge">
          <input type="checkbox" v-model="acknowledged" :disabled="busy || expired" />{{ label('acknowledge') }}
        </label>
      </section>
      <section v-if="confirmRevoke" class="authority-revoke ui-stack" role="region" :aria-label="label('revokeTitle')">
        <h3>{{ label('revokeTitle') }}</h3><p>{{ label('revokeHelp') }}</p>
      </section>
    </div>
    <template #actions>
      <UiButton :disabled="busy" @click="close">{{ label('close') }}</UiButton>
      <template v-if="confirmRevoke">
        <UiButton :disabled="busy" @click="confirmRevoke = false">{{ label('cancel') }}</UiButton>
        <UiButton variant="danger" :disabled="!canRevoke" :loading="busy" @click="revoke">{{ label('confirmRevoke') }}</UiButton>
      </template>
      <template v-else>
        <UiButton :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton>
        <UiButton v-if="!plan && canRevoke" variant="danger" @click="confirmRevoke = true">{{ label('revoke') }}</UiButton>
        <UiButton v-if="plan?.state === 'review_required'" :disabled="!canDecide" @click="decide('deny')">{{ label('deny') }}</UiButton>
        <UiButton v-if="plan?.state === 'review_required'" variant="primary" :disabled="!canDecide || !acknowledged" :loading="busy" @click="decide('approve')">{{ label('approve') }}</UiButton>
        <UiButton v-if="plan?.state === 'approved_pending_apply'" variant="primary" :disabled="!canDecide || adoptionBlocked" :loading="busy" @click="decide('apply')">{{ label('apply') }}</UiButton>
      </template>
    </template>
  </UiDialog>
</template>

<style scoped>
.ui-v2 .authority-dialog { width: min(760px, calc(100vw - 32px)); }
.authority-body { min-width: 0; }
.authority-intro h3, .authority-intro p, .authority-note, .authority-notice, .authority-error, .authority-review-plan h3, .authority-resources h4, .authority-revoke h3, .authority-revoke p { margin: 0; }
.authority-intro h3 { margin-bottom: calc(var(--ui-space) * 2); font-size: 1.05em; overflow-wrap: anywhere; }
.authority-note { padding: calc(var(--ui-space) * 3); border-left: 3px solid var(--ui-border); background: var(--ui-surface-alt); color: var(--ui-text-secondary); font-size: .9em; }
.authority-error { color: var(--ui-danger); }
.authority-notice { color: var(--ui-text); padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-accent); border-radius: var(--ui-radius-sm); }
.authority-status, .authority-review-heading { display: flex; flex-wrap: wrap; justify-content: space-between; gap: calc(var(--ui-space) * 2); }
.authority-effective { color: var(--ui-success); }
.authority-artifact { display: grid; gap: var(--ui-space); }
.authority-artifact code { color: var(--ui-text-secondary); font-size: .8em; overflow-wrap: anywhere; }
.authority-chooser { display: grid; gap: calc(var(--ui-space) * 2); }
.authority-chooser select { min-width: 0; width: 100%; }
.authority-create { justify-self: start; }
.authority-review-plan { padding-top: calc(var(--ui-space) * 4); border-top: 1px solid var(--ui-border); }
.authority-review-heading h3, .authority-revoke h3 { font-size: 1em; font-weight: 650; }
.authority-resources { display: grid; gap: calc(var(--ui-space) * 2); }
.authority-resources h4 { font-size: .9em; color: var(--ui-text-secondary); }
.authority-resource { min-width: 0; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-alt); padding: calc(var(--ui-space) * 3); }
.authority-resource h5 { font-size: .95em; margin: 0 0 calc(var(--ui-space) * 2); overflow-wrap: anywhere; }
.authority-resource pre { margin: 0; font-size: .8em; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 18rem; overflow: auto; color: var(--ui-text-secondary); }
.authority-file code, .authority-relational code, .authority-checkpoint code, .authority-identity code, .authority-status-projection code, .authority-peer-read code { font-size: .8em; color: var(--ui-text-secondary); overflow-wrap: anywhere; }
.authority-peer-choice { align-items: flex-start; margin: 0 0 calc(var(--ui-space) * 2); overflow-wrap: anywhere; }
.authority-peer-choice code { font-size: 1em; }
.authority-peer-selection { margin: 0 calc(var(--ui-space) * 2) var(--ui-space) 0; }
.authority-status-nodes { margin: 0; padding-left: 1.1em; max-height: 12rem; overflow: auto; }
.authority-pin-heading { font-size: .9em; margin: calc(var(--ui-space) * 4) 0 0; }
.authority-file-limits { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--ui-space) calc(var(--ui-space) * 3); margin: calc(var(--ui-space) * 3) 0 0; font-size: .9em; }
.authority-file-limits dt { font-weight: 500; color: var(--ui-text-secondary); }
.authority-file-limits dd { margin: 0; overflow-wrap: anywhere; }
.authority-file-binding { margin-top: calc(var(--ui-space) * 3); }
.authority-file-binding summary { cursor: pointer; font-size: .9em; }
.authority-acknowledge { align-items: flex-start; }
.authority-revoke { border-top: 1px solid var(--ui-danger); padding-top: calc(var(--ui-space) * 4); }
@media (max-width: 600px) { .authority-create { width: 100%; } .authority-file-limits { grid-template-columns: minmax(0, 1fr); } .authority-file-limits dd { margin-bottom: calc(var(--ui-space) * 2); } }
</style>
