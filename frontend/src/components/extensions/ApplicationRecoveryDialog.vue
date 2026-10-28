<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { interruptedLifecycleStatuses, useRecoveryLabels } from './recovery-labels'

const props = defineProps<{ moduleId: string; name: string }>()
const emit = defineEmits<{ close: []; recovered: [] }>()
const label = useRecoveryLabels()
const status = ref('')
const lifecycleError = ref('')
const error = ref('')
const reviewed = ref(false)
const loading = ref(false)
const saving = ref(false)
const fresh = ref(false)
const pending = computed(() => interruptedLifecycleStatuses.has(status.value))
const canRecover = computed(() => fresh.value && pending.value && reviewed.value && !loading.value && !saving.value)
const close = () => { if (!saving.value) emit('close') }

async function refresh() {
  if (saving.value || loading.value) return
  loading.value = true; fresh.value = false; reviewed.value = false; error.value = ''
  try {
    const { data } = await http.get('/api/v1/application-extensions', { timeout: 12000 })
    if (!Array.isArray(data)) throw new Error('Invalid installation catalog')
    const installation = data.find(item => item.module_id === props.moduleId)
    if (!installation) { status.value = ''; lifecycleError.value = ''; error.value = label('missing'); return }
    if (typeof installation.status !== 'string') throw new Error('Invalid lifecycle stage')
    status.value = installation.status
    lifecycleError.value = typeof installation.error === 'string' ? installation.error : ''
    fresh.value = true
  } catch { error.value = label('unavailable') }
  finally { loading.value = false }
}

async function recover() {
  if (!canRecover.value) return
  saving.value = true; error.value = ''; fresh.value = false
  try {
    const { data } = await http.post(`/api/v1/application-extensions/${encodeURIComponent(props.moduleId)}/lifecycle/recover`,
      { confirmed_external_outcome_reviewed: true }, { timeout: 60000 })
    if (data?.module_id !== props.moduleId || data.status !== 'disabled' || data.enabled !== false || data.active_version !== null)
      throw new Error('Recovery result is unconfirmed')
    emit('recovered')
  } catch {
    // No retry or inferred success: a lost reply may follow a completed stop.
    error.value = label('uncertain'); reviewed.value = false
  } finally { saving.value = false }
}
onMounted(refresh)
</script>

<template>
  <UiDialog :open="true" :title="label('title')" :close-label="label('close')" @update:open="!$event && close()">
    <div class="modal-body ui-stack application-recovery">
      <h3>{{ name }}</h3>
      <p>{{ label('help') }}</p>
      <p>{{ label('boundary') }}</p>
      <p v-if="loading" role="status">{{ label('loading') }}</p>
      <p v-else-if="status"><strong>{{ label('status') }}:</strong> <code>{{ status }}</code></p>
      <p v-if="lifecycleError" class="ui-help">{{ lifecycleError }}</p>
      <p v-if="error" class="error-message" role="alert">{{ error }}</p>
      <p v-if="fresh && !pending" class="ui-help">{{ label(status === 'disabled' ? 'stopped' : 'inactive') }}</p>
      <label v-if="pending" class="recovery-confirmation">
        <input type="checkbox" v-model="reviewed" :disabled="!fresh || loading || saving" />
        <span>{{ label('confirm') }}</span>
      </label>
    </div>
    <template #actions>
      <UiButton :disabled="saving" @click="close">{{ label('close') }}</UiButton>
      <UiButton :disabled="saving || loading" @click="refresh">{{ label('refresh') }}</UiButton>
      <UiButton variant="primary" class="recover-confirm-btn" :disabled="!canRecover" :loading="saving" @click="recover">
        {{ label(saving ? 'working' : 'action') }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.application-recovery { overflow-wrap: anywhere; }
.recovery-confirmation { display: flex; align-items: flex-start; gap: .75rem; }
.recovery-confirmation input { flex-shrink: 0; margin-top: .3rem; }
</style>
