<template>
  <main class="reference-page">
    <h1>Reference registration</h1>
    <p>This neutral screen verifies the restricted kiosk route.</p>
    <label>
      Label
      <input v-model.trim="label" maxlength="120" />
    </label>
    <button type="button" :disabled="!label || busy || unconfirmed" @click="submit">Submit</button>
    <p v-if="message" role="status">{{ message }}</p>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ApplicationHostError, useApplicationHost } from '@3mm/application-ui/v1'

const host = useApplicationHost()
const unconfirmed = ref(false)
const label = ref('')
const busy = ref(false)
const message = ref('')

async function submit() {
  if (busy.value || unconfirmed.value) return
  busy.value = true
  message.value = ''
  const requestId = crypto.randomUUID()
  try {
    const result = await host.invoke('register', { label: label.value }, { idempotencyKey: requestId })
    message.value = `Created ${result.record_id}`
    label.value = ''
  } catch (error) {
    unconfirmed.value = error instanceof ApplicationHostError && ['unconfirmed', 'disposed'].includes(error.code)
    message.value = unconfirmed.value
      ? `Outcome unconfirmed. Preserve request ${requestId} for review; do not resubmit.`
      : error instanceof Error ? error.message : 'Registration failed'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.reference-page { max-width: 42rem; margin: 0 auto; padding: 2rem; display: grid; gap: 1rem; }
label { display: grid; gap: .4rem; }
input, button { min-height: 2.75rem; border: 1px solid var(--border-color, #c7cbd1); border-radius: .55rem; padding: .65rem .8rem; }
button { background: var(--primary-color, #2f6fed); color: white; cursor: pointer; }
</style>
