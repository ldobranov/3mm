<script setup lang="ts">
import { onMounted, ref } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import http from '@/utils/dynamic-http'
import { useRecoveryLabels } from './recovery-labels'

const label = useRecoveryLabels()
const base = '/api/v1/application-extensions/authority/review-key-recovery'
type Ticket = { expected_key_id: string; expected_generation: string }
const ticket = ref<Ticket | null>(null)
const visible = ref(false)
const busy = ref(false)
const confirmed = ref(false)
const result = ref<'ready' | 'unavailable' | 'unconfirmed' | null>(null)

async function refresh() {
  if (busy.value) return
  busy.value = true
  ticket.value = null
  confirmed.value = false
  try {
    const { data } = await http.get(base, { timeout: 12000 })
    if (data?.state === 'recovery_required'
      && typeof data.expected_key_id === 'string' && /^review_[0-9a-f]{32}$/.test(data.expected_key_id)
      && typeof data.expected_generation === 'string' && /^[0-9a-f]{32}$/.test(data.expected_generation)) {
      ticket.value = { expected_key_id: data.expected_key_id, expected_generation: data.expected_generation }
      visible.value = true
      result.value = null
    } else if (visible.value) {
      result.value = data?.state === 'current' ? 'ready' : 'unavailable'
    }
  } catch { if (visible.value) result.value = 'unavailable' }
  finally { busy.value = false }
}

async function recover() {
  if (!ticket.value || !confirmed.value || busy.value) return
  const expected = ticket.value
  busy.value = true
  ticket.value = null
  confirmed.value = false
  try {
    const { data } = await http.post(base, { ...expected, confirm_recovery_without_permissions: true }, { timeout: 12000 })
    result.value = data?.state === 'current' && data?.permission_approval === 'not_evaluated' ? 'ready' : 'unconfirmed'
  } catch { result.value = 'unconfirmed' }
  finally { busy.value = false }
}

defineExpose({ refresh })
onMounted(refresh)
</script>

<template>
  <section v-if="visible" class="ui-section ui-stack review-recovery" :aria-busy="busy" aria-labelledby="review-recovery-title">
    <h2 id="review-recovery-title">{{ label('keyRecoveryTitle') }}</h2>
    <p v-if="ticket">{{ label('keyRecoveryHelp') }}</p>
    <p v-if="result === 'ready'" role="status">{{ label('keyRecoveryReady') }}</p>
    <p v-else-if="result === 'unavailable'" role="alert">{{ label('keyRecoveryUnavailable') }}</p>
    <p v-else-if="result === 'unconfirmed'" role="alert">{{ label('keyRecoveryUnconfirmed') }}</p>
    <label v-if="ticket" class="ui-check">
      <input v-model="confirmed" type="checkbox" :disabled="busy" />
      {{ label('keyRecoveryConfirm') }}
    </label>
    <div v-if="result !== 'ready'" class="ui-actions">
      <UiButton v-if="ticket" variant="primary" :disabled="!confirmed || busy" @click="recover">{{ label('keyRecoveryAction') }}</UiButton>
      <UiButton variant="secondary" :disabled="busy" @click="refresh">{{ label('refresh') }}</UiButton>
    </div>
  </section>
</template>

<style scoped>
.review-recovery { padding: calc(var(--ui-space) * 4); margin-bottom: calc(var(--ui-space) * 6); }
</style>
