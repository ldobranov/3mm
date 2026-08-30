<template>
  <main class="reference-page">
    <h1>Reference registration</h1>
    <p>This neutral screen verifies the restricted kiosk route.</p>
    <label>
      Label
      <input v-model.trim="label" maxlength="120" />
    </label>
    <button type="button" :disabled="!label || busy" @click="submit">Submit</button>
    <p v-if="message" role="status">{{ message }}</p>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const label = ref('')
const busy = ref(false)
const message = ref('')

async function submit() {
  busy.value = true
  message.value = ''
  try {
    const token = localStorage.getItem('applicationKioskToken') || ''
    const response = await fetch('/api/v1/application-extensions/org.3mm.application-reference/kiosk/operations/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ payload: { label: label.value }, idempotency_key: crypto.randomUUID() }),
    })
    if (!response.ok) throw new Error('Registration failed')
    const result = await response.json()
    message.value = `Created ${result.record_id}`
    label.value = ''
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Registration failed'
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
