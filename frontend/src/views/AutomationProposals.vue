<template>
  <main class="view automation-review">
    <header class="review-header">
      <div>
        <p class="eyebrow">{{ t('automations.proposals.eyebrow', 'Milestone 6 · Review') }}</p>
        <h1 class="view-title">{{ t('automations.proposals.title', 'Automation proposals') }}</h1>
        <p class="intro">
          {{ t('automations.proposals.subtitle', 'Review validated changes before approving them. Approval does not run the automation.') }}
        </p>
      </div>
      <button class="button button-secondary" :disabled="loading" @click="loadProposals">
        <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
        {{ t('automations.proposals.refresh', 'Refresh') }}
      </button>
    </header>

    <div v-if="errorMessage" class="notice notice-error" role="alert">{{ errorMessage }}</div>

    <section class="planner-card card">
      <div class="planner-heading">
        <div>
          <p class="eyebrow">{{ t('automations.planner.eyebrow', 'AI planner') }}</p>
          <h2>{{ t('automations.planner.title', 'Describe the behavior') }}</h2>
          <p>{{ t('automations.planner.subtitle', 'The AI can use only capabilities currently trusted by 3mm.') }}</p>
        </div>
        <div class="credit-balance">
          <span>{{ t('automations.planner.balance', 'AI credit') }}</span>
          <strong>{{ creditBalance.toLocaleString() }}</strong>
          <small>microcredits</small>
        </div>
      </div>
      <textarea v-model="plannerIntent" class="planner-intent" rows="3" :placeholder="t('automations.planner.placeholder', 'When input one turns on, set output one to on on the same device.')"></textarea>
      <div class="planner-options">
        <label>
          <span>{{ t('automations.planner.provider', 'Provider') }}</span>
          <select v-model="plannerProvider"><option value="groq">Groq</option><option value="openrouter">OpenRouter</option></select>
        </label>
        <label>
          <span>{{ t('automations.planner.payment', 'Payment') }}</span>
          <select v-model="paymentMode"><option value="prepaid">{{ t('automations.planner.prepaid', 'Prepaid credit') }}</option><option value="byok">{{ t('automations.planner.byok', 'My provider key (BYOK)') }}</option></select>
        </label>
        <label v-if="paymentMode === 'byok'">
          <span>{{ t('automations.planner.temporaryKey', 'Temporary provider key') }}</span>
          <input v-model="temporaryKey" type="password" autocomplete="off" :placeholder="t('automations.planner.notSaved', 'Used once — never saved')" />
        </label>
      </div>
      <div v-if="estimatedJob" class="estimate-panel">
        <div><span>{{ t('automations.planner.estimatedTokens', 'Maximum output') }}</span><strong>{{ estimatedJob.estimated_output_tokens }} tokens</strong></div>
        <div><span>{{ t('automations.planner.estimatedCost', 'Estimated maximum') }}</span><strong>{{ estimatedJob.estimated_max_microcredits }} microcredits</strong></div>
        <label class="approval-check"><input v-model="budgetConfirmed" type="checkbox" /><span>{{ t('automations.planner.approveMaximum', 'I approve this maximum for this job.') }}</span></label>
      </div>
      <div class="planner-actions">
        <button class="button button-secondary" :disabled="working || !plannerIntent.trim()" @click="estimatePlanningJob">{{ t('automations.planner.estimate', 'Estimate') }}</button>
        <button v-if="estimatedJob" class="button button-primary" :disabled="working || !budgetConfirmed || (paymentMode === 'byok' && !temporaryKey)" @click="executePlanningJob">{{ working ? t('automations.planner.generating', 'Generating…') : t('automations.planner.generate', 'Generate proposal') }}</button>
      </div>
    </section>

    <section class="deployments-card card" aria-live="polite">
      <div class="list-heading">
        <div>
          <p class="eyebrow">{{ t('automations.deployments.eyebrow', 'Device state') }}</p>
          <h2>{{ t('automations.deployments.title', 'Device automations') }}</h2>
        </div>
        <span class="count">{{ deployments.length }}</span>
      </div>
      <div v-if="deployments.length === 0" class="deployment-empty">
        {{ t('automations.deployments.empty', 'No automation revisions have been sent to a device.') }}
      </div>
      <div v-else class="deployment-grid">
        <article v-for="deployment in deployments" :key="deployment.revision_id" class="deployment-item">
          <div class="deployment-heading">
            <div>
              <strong>{{ deployment.definition?.name || deployment.automation_id }}</strong>
              <span>{{ deployment.device_id }}</span>
            </div>
            <span class="status" :class="`status-${deployment.deliveryStatus}`">
              {{ deploymentStatusLabel(deployment.deliveryStatus) }}
            </span>
          </div>
          <p v-if="deployment.error" class="deployment-error">{{ deployment.error }}</p>
          <dl>
            <div><dt>{{ t('automations.deployments.revision', 'Revision') }}</dt><dd>{{ deployment.revision }}</dd></div>
            <div><dt>{{ t('automations.deployments.configuration', 'Configuration') }}</dt><dd>{{ deployment.definition?.enabled ? t('common.enabled', 'Enabled') : t('common.disabled', 'Disabled') }}</dd></div>
          </dl>
          <button
            v-if="deployment.deliveryStatus === 'installed'"
            class="button button-secondary deployment-toggle"
            :disabled="working"
            @click="setDeploymentEnabled(deployment, !deployment.definition!.enabled)"
          >
            {{ deployment.definition?.enabled ? t('automations.deployments.disable', 'Disable') : t('automations.deployments.enable', 'Enable') }}
          </button>
        </article>
      </div>
    </section>

    <section class="review-layout" aria-live="polite">
      <aside class="proposal-list card" aria-label="Automation proposals">
        <div class="list-heading">
          <div>
            <h2>{{ t('automations.proposals.queue', 'Review queue') }}</h2>
            <label class="history-toggle">
              <input v-model="showCompleted" type="checkbox" />
              <span>{{ t('automations.proposals.showCompleted', 'Show completed') }}</span>
            </label>
          </div>
          <span class="count">{{ visibleProposals.length }}</span>
        </div>

        <div v-if="loading && visibleProposals.length === 0" class="empty-state">
          {{ t('automations.proposals.loading', 'Loading proposals…') }}
        </div>
        <div v-else-if="visibleProposals.length === 0" class="empty-state">
          <i class="bi bi-inbox" aria-hidden="true"></i>
          <strong>{{ t('automations.proposals.emptyTitle', 'Nothing to review') }}</strong>
          <span>{{ t('automations.proposals.emptyText', 'New AI proposals will appear here after validation.') }}</span>
        </div>

        <button
          v-for="proposal in visibleProposals"
          :key="proposal.proposal_id"
          class="proposal-item"
          :class="{ selected: selected?.proposal_id === proposal.proposal_id }"
          @click="selectProposal(proposal)"
        >
          <span class="proposal-name">{{ proposal.candidate.name }}</span>
          <span class="proposal-summary">{{ proposal.intent }}</span>
          <span class="proposal-meta">
            <span class="status" :class="`status-${proposal.status}`">{{ statusLabel(proposal.status) }}</span>
            <time :datetime="proposal.created_at">{{ formatDate(proposal.created_at) }}</time>
          </span>
        </button>
      </aside>

      <article class="proposal-detail card">
        <div v-if="!selected" class="empty-state detail-empty">
          <i class="bi bi-file-earmark-check" aria-hidden="true"></i>
          <strong>{{ t('automations.proposals.selectTitle', 'Select a proposal') }}</strong>
          <span>{{ t('automations.proposals.selectText', 'Its trigger, actions and target devices will be shown here.') }}</span>
        </div>

        <template v-else>
          <div class="detail-heading">
            <div>
              <span class="status" :class="`status-${selected.status}`">{{ statusLabel(selected.status) }}</span>
              <h2>{{ selected.candidate.name }}</h2>
              <p>{{ selected.intent }}</p>
            </div>
            <span class="execution-badge">{{ selected.diff.automation.execution }}</span>
          </div>

          <div v-if="selected.validation_issues.length" class="notice notice-error">
            <strong>{{ t('automations.proposals.validationIssues', 'Validation issues') }}</strong>
            <ul>
              <li v-for="issue in selected.validation_issues" :key="`${issue.path}-${issue.code}`">
                <code>{{ issue.path }}</code> — {{ issue.message }}
              </li>
            </ul>
          </div>

          <section class="change-section">
            <h3>{{ t('automations.proposals.changeSummary', 'Proposed change') }}</h3>
            <dl class="summary-grid">
              <div><dt>{{ t('automations.proposals.operation', 'Operation') }}</dt><dd>{{ selected.diff.operation }}</dd></div>
              <div><dt>{{ t('automations.proposals.state', 'Initial state') }}</dt><dd>{{ selected.diff.automation.enabled ? t('common.enabled', 'Enabled') : t('common.disabled', 'Disabled') }}</dd></div>
              <div><dt>{{ t('automations.proposals.targets', 'Target devices') }}</dt><dd>{{ selected.diff.target_devices.join(', ') }}</dd></div>
            </dl>
          </section>

          <section class="execution-tools">
            <div>
              <h3>{{ t('automations.proposals.safeChecks', 'Safe checks') }}</h3>
              <p>{{ t('automations.proposals.safeChecksText', 'Simulation and dry-run do not change the device.') }}</p>
            </div>
            <div class="tool-actions">
              <button class="button button-secondary" :disabled="working" @click="simulateSelected">
                {{ t('automations.proposals.simulate', 'Simulate') }}
              </button>
              <button class="button button-secondary" :disabled="working || selected.status === 'invalid'" @click="dryRunSelected">
                {{ t('automations.proposals.dryRun', 'Dry run') }}
              </button>
            </div>
            <pre v-if="executionResult" class="result-preview">{{ executionResult }}</pre>
          </section>

          <section class="change-section">
            <h3>{{ t('automations.proposals.when', 'When') }}</h3>
            <div class="flow-card">
              <i class="bi bi-lightning-charge" aria-hidden="true"></i>
              <div><strong>{{ selected.diff.trigger.event }}</strong><span>{{ selected.diff.trigger.capability_id }} · {{ selected.diff.trigger.device_id }}</span></div>
            </div>
          </section>

          <section class="change-section">
            <h3>{{ t('automations.proposals.then', 'Then') }}</h3>
            <ol class="action-list">
              <li v-for="(action, index) in selected.diff.actions" :key="`${action.device_id}-${action.capability_id}-${index}`">
                <span class="step-number">{{ index + 1 }}</span>
                <div><strong>{{ action.action }}</strong><span>{{ action.capability_id }} · {{ action.device_id }}</span></div>
              </li>
            </ol>
          </section>

          <footer class="approval-panel">
            <label v-if="selected.status === 'validated'" class="approval-check">
              <input v-model="approvalConfirmed" type="checkbox" />
              <span>{{ t('automations.proposals.confirm', 'I reviewed this exact proposal and approve it for the next stage.') }}</span>
            </label>
            <p v-else-if="selected.status === 'approved'" class="approved-message">
              <i class="bi bi-check-circle-fill" aria-hidden="true"></i>
              {{ t('automations.proposals.approvedMessage', 'This proposal is approved. It has not been executed.') }}
            </p>
            <button
              v-if="selected.status === 'validated'"
              class="button button-primary"
              :disabled="!approvalConfirmed || approving"
              @click="approveSelected"
            >
              {{ approving ? t('automations.proposals.approving', 'Approving…') : t('automations.proposals.approve', 'Approve proposal') }}
            </button>
            <button
              v-else-if="selected.status === 'approved'"
              class="button button-primary"
              :disabled="working"
              @click="applySelected"
            >
              {{ working ? t('automations.proposals.applying', 'Applying…') : t('automations.proposals.apply', 'Apply to device') }}
            </button>
            <button
              v-else-if="selected.status === 'applied' && activeRevision"
              class="button button-danger"
              :disabled="working"
              @click="rollbackSelected"
            >
              {{ working ? t('automations.proposals.rollingBack', 'Rolling back…') : t('automations.proposals.rollback', 'Roll back') }}
            </button>
          </footer>

          <details class="technical-details">
            <summary>{{ t('automations.proposals.technicalDetails', 'Technical details') }}</summary>
            <div><span>Proposal ID</span><code>{{ selected.proposal_id }}</code></div>
            <div><span>Candidate hash</span><code>{{ selected.candidate_hash }}</code></div>
            <div><span>Context hash</span><code>{{ selected.context_hash }}</code></div>
          </details>
        </template>
      </article>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

type ProposalStatus = 'validated' | 'invalid' | 'approved' | 'applied'
type JsonValue = string | number | boolean

interface ProposalAction {
  device_id: string
  capability_id: string
  action: string
  arguments: Record<string, JsonValue>
}

interface AutomationProposal {
  proposal_id: string
  intent: string
  candidate_hash: string
  context_hash: string
  status: ProposalStatus
  created_at: string
  candidate: { name: string }
  validation_issues: Array<{ path: string; code: string; message: string }>
  diff: {
    operation: string
    automation: { name: string; execution: string; enabled: boolean }
    trigger: { device_id: string; capability_id: string; event: string; conditions: Record<string, JsonValue> }
    actions: ProposalAction[]
    target_devices: string[]
  }
}

interface AutomationRevision {
  revision_id: string
  automation_id: string
  revision: number
  active: boolean
  operation: string
  command_ids: string[]
  definition: {
    name: string
    enabled: boolean
    trigger: { device_id: string }
  } | null
}

type DeliveryStatus = 'queued' | 'installed' | 'failed'

interface DeviceCommand {
  command_id: string
  status: string
  error: string | null
}

interface AutomationDeployment extends AutomationRevision {
  device_id: string
  deliveryStatus: DeliveryStatus
  error: string | null
}

interface AiJob {
  job_id: string
  status: string
  estimated_output_tokens: number
  estimated_max_microcredits: number
  proposal_id: string | null
}

const { t } = useI18n()
const proposals = ref<AutomationProposal[]>([])
const showCompleted = ref(false)
const visibleProposals = computed(() => showCompleted.value
  ? proposals.value
  : proposals.value.filter(proposal => proposal.status !== 'applied'))
const selected = ref<AutomationProposal | null>(null)
const loading = ref(false)
const approving = ref(false)
const working = ref(false)
const approvalConfirmed = ref(false)
const errorMessage = ref('')
const executionResult = ref('')
const activeRevision = ref<AutomationRevision | null>(null)
const deployments = ref<AutomationDeployment[]>([])
const plannerIntent = ref('')
const plannerProvider = ref<'groq' | 'openrouter'>('groq')
const paymentMode = ref<'prepaid' | 'byok'>('prepaid')
const temporaryKey = ref('')
const estimatedJob = ref<AiJob | null>(null)
const budgetConfirmed = ref(false)
const creditBalance = ref(0)

function errorText(error: any): string {
  return error?.response?.data?.detail || error?.message || t('automations.proposals.unknownError', 'The request could not be completed.')
}

function statusLabel(status: ProposalStatus): string {
  return {
    validated: t('automations.proposals.statusValidated', 'Ready for review'),
    invalid: t('automations.proposals.statusInvalid', 'Needs changes'),
    approved: t('automations.proposals.statusApproved', 'Approved'),
    applied: t('automations.proposals.statusApplied', 'Applied'),
  }[status]
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function deploymentStatusLabel(status: DeliveryStatus): string {
  return {
    queued: t('automations.deployments.statusQueued', 'Queued'),
    installed: t('automations.deployments.statusInstalled', 'Installed'),
    failed: t('automations.deployments.statusFailed', 'Failed'),
  }[status]
}

async function loadDeployments() {
  const revisionResponse = await http.get('/api/v1/ai/automation-revisions')
  const revisions = (revisionResponse.data as AutomationRevision[]).filter(item => item.active && item.definition)
  const deviceIds = [...new Set(revisions.map(item => item.definition!.trigger.device_id))]
  const commandResponses = await Promise.all(deviceIds.map(async deviceId => ({
    deviceId,
    response: await http.get(`/api/v1/devices/${deviceId}/commands?limit=100`),
  })))
  const commands = new Map<string, DeviceCommand>()
  for (const { response } of commandResponses) {
    for (const command of response.data.items as DeviceCommand[]) commands.set(command.command_id, command)
  }
  deployments.value = revisions.map(revision => {
    const command = revision.command_ids.map(id => commands.get(id)).find(Boolean)
    return {
      ...revision,
      device_id: revision.definition!.trigger.device_id,
      deliveryStatus: command?.status === 'succeeded' ? 'installed' : command?.status === 'failed' ? 'failed' : 'queued',
      error: command?.error || null,
    }
  })
}

async function setDeploymentEnabled(deployment: AutomationDeployment, enabled: boolean) {
  const result = await runAction(`/api/v1/ai/automation-revisions/${deployment.revision_id}/enabled`, { enabled })
  if (!result) return
  await loadDeployments()
}

function selectProposal(proposal: AutomationProposal) {
  selected.value = proposal
  approvalConfirmed.value = false
  errorMessage.value = ''
  executionResult.value = ''
  loadActiveRevision()
}

async function loadActiveRevision() {
  activeRevision.value = null
  if (!selected.value || selected.value.status !== 'applied') return
  try {
    const response = await http.get('/api/v1/ai/automation-revisions', { params: { automation_id: selected.value.proposal_id } })
    activeRevision.value = (response.data as AutomationRevision[]).find(item => item.active) || null
  } catch (error) {
    errorMessage.value = errorText(error)
  }
}

async function loadProposals() {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await http.get('/api/v1/ai/automation-proposals')
    proposals.value = response.data
    if (selected.value) {
      selected.value = visibleProposals.value.find(item => item.proposal_id === selected.value?.proposal_id) || visibleProposals.value[0] || null
    } else {
      selected.value = visibleProposals.value[0] || null
    }
    await loadActiveRevision()
    await loadDeployments()
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    loading.value = false
  }
}

async function loadCredits() {
  try {
    const response = await http.get('/api/v1/ai/credits')
    creditBalance.value = response.data.available_microcredits
  } catch (error) {
    errorMessage.value = errorText(error)
  }
}

async function estimatePlanningJob() {
  working.value = true; errorMessage.value = ''; estimatedJob.value = null; budgetConfirmed.value = false
  try {
    const response = await http.post('/api/v1/ai/jobs/estimate', {
      intent: plannerIntent.value.trim(), provider: plannerProvider.value,
      payment_mode: paymentMode.value, max_output_tokens: 1200,
    })
    estimatedJob.value = response.data
    if (response.data.status === 'reused') {
      await loadProposals()
      executionResult.value = t('automations.planner.reused', 'An unchanged proposal was reused without another AI call.')
    }
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally { working.value = false }
}

async function executePlanningJob() {
  if (!estimatedJob.value) return
  working.value = true; errorMessage.value = ''
  try {
    const config = paymentMode.value === 'byok' ? { headers: { 'X-3mm-AI-Key': temporaryKey.value } } : undefined
    const response = await http.post(`/api/v1/ai/jobs/${estimatedJob.value.job_id}/execute`, {
      intent: plannerIntent.value.trim(), approved_max_microcredits: estimatedJob.value.estimated_max_microcredits,
    }, config)
    temporaryKey.value = ''
    if (response.data.proposal_id) {
      await Promise.all([loadProposals(), loadCredits()])
      const generated = proposals.value.find(item => item.proposal_id === response.data.proposal_id)
      if (generated) selectProposal(generated)
    }
    estimatedJob.value = null; budgetConfirmed.value = false
  } catch (error) {
    temporaryKey.value = ''
    errorMessage.value = errorText(error)
  } finally { working.value = false }
}

async function runAction(path: string, body?: object) {
  working.value = true
  errorMessage.value = ''
  try {
    const response = await http.post(path, body)
    return response.data
  } catch (error) {
    errorMessage.value = errorText(error)
    return null
  } finally {
    working.value = false
  }
}

async function simulateSelected() {
  if (!selected.value) return
  const result = await runAction(`/api/v1/ai/automation-proposals/${selected.value.proposal_id}/simulate`, { event: null })
  if (result) executionResult.value = JSON.stringify(result, null, 2)
}

async function dryRunSelected() {
  if (!selected.value) return
  const result = await runAction(`/api/v1/ai/automation-proposals/${selected.value.proposal_id}/dry-run`)
  if (result) executionResult.value = JSON.stringify(result, null, 2)
}

async function applySelected() {
  if (!selected.value) return
  const result = await runAction(`/api/v1/ai/automation-proposals/${selected.value.proposal_id}/apply`)
  if (!result) return
  activeRevision.value = result
  selected.value.status = 'applied'
  proposals.value = proposals.value.map(item => item.proposal_id === selected.value?.proposal_id ? selected.value : item) as AutomationProposal[]
  executionResult.value = t('automations.proposals.applyQueued', 'The approved revision was queued for the device.')
  await loadDeployments()
}

async function rollbackSelected() {
  if (!activeRevision.value) return
  const result = await runAction(`/api/v1/ai/automation-revisions/${activeRevision.value.revision_id}/rollback`)
  if (!result) return
  activeRevision.value = result.active ? result : null
  executionResult.value = t('automations.proposals.rollbackQueued', 'Rollback was queued for the device.')
}

async function approveSelected() {
  if (!selected.value || !approvalConfirmed.value) return
  approving.value = true
  errorMessage.value = ''
  try {
    const response = await http.post(
      `/api/v1/ai/automation-proposals/${selected.value.proposal_id}/approve`,
      { expected_candidate_hash: selected.value.candidate_hash },
    )
    const approved = response.data as AutomationProposal
    proposals.value = proposals.value.map(item => item.proposal_id === approved.proposal_id ? approved : item)
    selected.value = approved
    approvalConfirmed.value = false
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    approving.value = false
  }
}

onMounted(() => Promise.all([loadProposals(), loadCredits()]))
</script>

<style scoped>
.automation-review { max-width: 1180px; margin: 0 auto; }
.review-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.5rem; }
.review-header h1 { margin: 0; }
.eyebrow { margin: 0 0 .35rem; color: var(--accent); font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.intro { max-width: 680px; margin: .5rem 0 0; color: var(--color-muted); }
.review-layout { display: grid; grid-template-columns: minmax(250px, 340px) minmax(0, 1fr); gap: 1rem; align-items: start; }
.planner-card { margin-bottom: 1rem; padding: 1.25rem; }
.deployments-card { margin-bottom: 1rem; overflow: hidden; }
.deployments-card .list-heading h2 { margin: 0; font-size: 1rem; }
.deployments-card .eyebrow { margin-bottom: .2rem; }
.deployment-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: .75rem; padding: 1rem; }
.deployment-item { padding: .9rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-soft); }
.deployment-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: .75rem; }
.deployment-heading > div { display: flex; min-width: 0; flex-direction: column; }
.deployment-heading span:not(.status) { overflow: hidden; color: var(--color-muted); font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.deployment-item dl { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin: .8rem 0 0; }
.deployment-item dl div { display: flex; flex-direction: column; }
.deployment-item dt { color: var(--color-muted); font-size: .68rem; text-transform: uppercase; }
.deployment-item dd { margin: .15rem 0 0; font-size: .82rem; font-weight: 650; }
.deployment-error { margin: .7rem 0 0; color: var(--danger); font-size: .78rem; }
.deployment-toggle { width: 100%; margin-top: .8rem; }
.deployment-empty { padding: 1rem; color: var(--color-muted); }
.status-installed { background: rgba(16, 185, 129, .14); color: var(--accent); }
.status-queued { background: rgba(37, 99, 235, .13); color: var(--color-link); }
.status-failed { background: rgba(239, 68, 68, .13); color: var(--danger); }
.planner-heading { display: flex; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.planner-heading h2 { margin: 0; font-size: 1.15rem; }
.planner-heading p:not(.eyebrow) { margin: .3rem 0 0; color: var(--color-muted); }
.credit-balance { display: flex; min-width: 130px; flex-direction: column; align-items: flex-end; color: var(--color-muted); font-size: .72rem; }
.credit-balance strong { color: var(--color-text); font-size: 1.1rem; }
.planner-intent, .planner-options input, .planner-options select { width: 100%; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); padding: .65rem; }
.planner-intent:focus, .planner-options input:focus, .planner-options select:focus { outline: 2px solid color-mix(in srgb, var(--accent) 35%, transparent); border-color: var(--accent); }
.planner-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-top: .75rem; }
.planner-options label { display: grid; gap: .3rem; color: var(--color-muted); font-size: .75rem; }
.estimate-panel { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; margin-top: .9rem; padding: .8rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-soft); }
.estimate-panel > div { display: flex; flex-direction: column; color: var(--color-muted); font-size: .72rem; }
.estimate-panel strong { color: var(--color-text); font-size: .88rem; }
.estimate-panel .approval-check { grid-column: 1 / -1; }
.planner-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .9rem; }
.proposal-list, .proposal-detail { padding: 0; overflow: hidden; }
.list-heading { display: flex; align-items: center; justify-content: space-between; padding: 1rem; border-bottom: 1px solid var(--color-border); }
.list-heading h2 { margin: 0; font-size: 1rem; }
.history-toggle { display: flex; align-items: center; gap: .4rem; margin-top: .35rem; color: var(--color-muted); font-size: .72rem; cursor: pointer; }
.history-toggle input { accent-color: var(--accent); }
.count { min-width: 1.6rem; padding: .15rem .4rem; border-radius: 999px; background: var(--color-background-soft); color: var(--color-muted); text-align: center; font-size: .75rem; }
.proposal-item { display: flex; width: 100%; flex-direction: column; gap: .35rem; padding: .9rem 1rem; border: 0; border-bottom: 1px solid var(--color-border); background: transparent; color: var(--color-text); text-align: left; cursor: pointer; }
.proposal-item:hover { background: var(--color-background-soft); }
.proposal-item.selected { background: color-mix(in srgb, var(--accent) 10%, var(--color-surface)); box-shadow: inset 3px 0 var(--accent); }
.proposal-name { font-weight: 700; }
.proposal-summary { overflow: hidden; color: var(--color-muted); font-size: .82rem; text-overflow: ellipsis; white-space: nowrap; }
.proposal-meta { display: flex; align-items: center; justify-content: space-between; gap: .5rem; color: var(--color-muted); font-size: .72rem; }
.status { display: inline-flex; width: fit-content; padding: .2rem .5rem; border-radius: 999px; font-size: .72rem; font-weight: 700; }
.status-validated { background: rgba(37, 99, 235, .13); color: var(--color-link); }
.status-invalid { background: rgba(239, 68, 68, .13); color: var(--danger); }
.status-approved { background: rgba(16, 185, 129, .14); color: var(--accent); }
.proposal-detail { min-height: 500px; }
.detail-heading { display: flex; justify-content: space-between; gap: 1rem; padding: 1.25rem; border-bottom: 1px solid var(--color-border); }
.detail-heading h2 { margin: .55rem 0 .25rem; font-size: 1.35rem; }
.detail-heading p { margin: 0; color: var(--color-muted); }
.execution-badge { align-self: flex-start; padding: .3rem .55rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); color: var(--color-muted); font-size: .75rem; text-transform: uppercase; }
.change-section { padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border); }
.change-section h3 { margin: 0 0 .75rem; font-size: .78rem; letter-spacing: .05em; text-transform: uppercase; color: var(--color-muted); }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin: 0; }
.summary-grid div { padding: .75rem; border-radius: var(--radius-sm); background: var(--color-background-soft); }
.summary-grid dt { margin-bottom: .25rem; color: var(--color-muted); font-size: .72rem; }
.summary-grid dd { margin: 0; overflow-wrap: anywhere; font-weight: 650; }
.flow-card, .action-list li { display: flex; align-items: center; gap: .75rem; }
.flow-card i, .step-number { display: grid; width: 2rem; height: 2rem; flex: 0 0 2rem; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--accent) 13%, var(--color-surface)); color: var(--accent); }
.flow-card div, .action-list div { display: flex; min-width: 0; flex-direction: column; }
.flow-card span, .action-list span:not(.step-number) { color: var(--color-muted); font-size: .78rem; overflow-wrap: anywhere; }
.action-list { display: grid; gap: .8rem; margin: 0; padding: 0; list-style: none; }
.step-number { font-size: .75rem; font-weight: 700; }
.approval-panel { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1.25rem; background: var(--color-background-soft); }
.execution-tools { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border); }
.execution-tools h3 { margin: 0 0 .2rem; font-size: .9rem; }
.execution-tools p { margin: 0; color: var(--color-muted); font-size: .8rem; }
.tool-actions { display: flex; gap: .5rem; }
.result-preview { grid-column: 1 / -1; max-height: 240px; margin: 0; padding: .8rem; overflow: auto; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-background-soft); color: var(--color-text); font-size: .75rem; white-space: pre-wrap; }
.approval-check { display: flex; align-items: flex-start; gap: .65rem; max-width: 520px; cursor: pointer; font-size: .86rem; }
.approval-check input { margin-top: .2rem; accent-color: var(--accent); }
.approved-message { display: flex; align-items: center; gap: .5rem; margin: 0; color: var(--accent); font-weight: 650; }
.technical-details { padding: 1rem 1.25rem; color: var(--color-muted); font-size: .78rem; }
.technical-details summary { cursor: pointer; font-weight: 650; }
.technical-details div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: .75rem; margin-top: .65rem; }
.technical-details code { color: var(--color-text); overflow-wrap: anywhere; }
.notice { margin-bottom: 1rem; padding: .75rem 1rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.proposal-detail > .notice { margin: 1rem 1.25rem 0; }
.notice-error { border-color: color-mix(in srgb, var(--danger) 45%, var(--color-border)); background: color-mix(in srgb, var(--danger) 8%, var(--color-surface)); color: var(--color-text); }
.notice ul { margin: .5rem 0 0; padding-left: 1.25rem; }
.empty-state { display: flex; min-height: 220px; flex-direction: column; align-items: center; justify-content: center; gap: .45rem; padding: 1.5rem; color: var(--color-muted); text-align: center; }
.empty-state i { font-size: 1.5rem; }
.empty-state strong { color: var(--color-text); }
.detail-empty { min-height: 500px; }
@media (max-width: 760px) {
  .review-header { flex-direction: column; }
  .review-layout { grid-template-columns: 1fr; }
  .planner-heading { flex-direction: column; }
  .credit-balance { align-items: flex-start; }
  .planner-options { grid-template-columns: 1fr; }
  .proposal-detail { min-height: 0; }
  .detail-empty { min-height: 240px; }
  .summary-grid { grid-template-columns: 1fr; }
  .approval-panel { align-items: stretch; flex-direction: column; }
  .execution-tools { grid-template-columns: 1fr; }
  .tool-actions { flex-wrap: wrap; }
}
</style>
