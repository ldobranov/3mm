<template>
  <main class="reference-page">
    <h1>Reference operations</h1>
    <p>Use the generic operator gateway to inspect an accepted record.</p>
    <label>
      Record ID
      <input v-model.trim="recordId" />
    </label>
    <button type="button" :disabled="!recordId || busy" @click="load">Load</button>
    <pre v-if="record">{{ JSON.stringify(record, null, 2) }}</pre>
    <p v-if="error" role="alert">{{ error }}</p>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const recordId = ref('')
const record = ref<Record<string, unknown> | null>(null)
const error = ref('')
const busy = ref(false)

async function load() {
  busy.value = true
  error.value = ''
  record.value = null
  try {
    const token = localStorage.getItem('authToken') || ''
    const response = await fetch('/api/v1/application-extensions/org.3mm.application-reference/operator/operations/get_record', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ payload: { record_id: recordId.value } }),
    })
    if (!response.ok) throw new Error('Record lookup failed')
    record.value = await response.json()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Record lookup failed'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.reference-page { max-width: 50rem; margin: 0 auto; padding: 2rem; display: grid; gap: 1rem; }
label { display: grid; gap: .4rem; }
input, button { min-height: 2.75rem; border: 1px solid var(--border-color, #c7cbd1); border-radius: .55rem; padding: .65rem .8rem; }
button { background: var(--primary-color, #2f6fed); color: white; cursor: pointer; }
pre { overflow: auto; padding: 1rem; border-radius: .55rem; background: var(--surface-muted, #f3f4f6); }
</style>
