<template>
  <main class="reference-capability">
    <h1>Mock capability acceptance</h1>
    <p>Only use an explicitly reviewed mock target. Queuing does not prove execution.</p>
    <p v-if="!ready" role="status">Checking current operation access…</p>
    <label v-if="canProbe">Exact declared arguments (JSON)
      <textarea v-model="argumentsText" rows="4" :disabled="busy || uncertain" />
    </label>
    <button v-if="canProbe" :disabled="busy || uncertain" @click="submit">Queue one mock request</button>
    <p v-if="pending">Preserve request ID: <code>{{ pending.key }}</code></p>
    <p v-if="uncertain" role="alert">Outcome unconfirmed. Do not resubmit or create a replacement ID.</p>
    <label v-if="canLookup">Original request ID
      <input v-model.trim="lookupId" :disabled="busy" />
    </label>
    <button v-if="canLookup" :disabled="busy || !lookupId" @click="lookup">Read existing outcome</button>
    <pre v-if="result" role="status">{{ JSON.stringify(result, null, 2) }}</pre>
    <p v-if="error" role="alert">{{ error }}</p>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApplicationHostError, useApplicationHost, type ApplicationPayload } from '@3mm/application-ui/v1'

const host = useApplicationHost()
const ready = ref(false)
const canProbe = ref(false)
const canLookup = ref(false)
const busy = ref(false)
const uncertain = ref(false)
const argumentsText = ref('{}')
const lookupId = ref('')
const pending = ref<{ key: string; payload: ApplicationPayload } | null>(null)
const result = ref<ApplicationPayload | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    const info = await host.getInfo()
    canProbe.value = info.operations.some(operation => operation.operation_id === 'probe')
    canLookup.value = info.operations.some(operation => operation.operation_id === 'lookup')
    ready.value = true
  } catch { error.value = 'Current operation access is unavailable.' }
})

async function submit() {
  if (busy.value || uncertain.value || !canProbe.value) return
  error.value = ''
  result.value = null
  try {
    const argumentsValue = JSON.parse(argumentsText.value)
    if (!argumentsValue || typeof argumentsValue !== 'object' || Array.isArray(argumentsValue))
      throw new Error('Arguments must be a JSON object.')
    // getRandomValues also works on a LAN HTTP origin, unlike randomUUID.
    const key = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
    pending.value = { key, payload: { arguments: argumentsValue } }
    lookupId.value = pending.value.key
    busy.value = true
    result.value = await host.invoke('probe', pending.value.payload, { idempotencyKey: pending.value.key })
  } catch (reason) {
    uncertain.value = reason instanceof ApplicationHostError && ['unconfirmed', 'disposed'].includes(reason.code)
    error.value = reason instanceof Error ? reason.message : 'Request refused.'
  } finally { busy.value = false }
}

async function lookup() {
  if (busy.value || !canLookup.value || !lookupId.value) return
  busy.value = true
  error.value = ''
  try { result.value = await host.invoke('lookup', { request_id: lookupId.value }) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : 'Outcome unavailable.' }
  finally { busy.value = false }
}
</script>

<style scoped>
.reference-capability { max-width: 46rem; margin: 0 auto; padding: 1.5rem; display: grid; gap: 1rem; }
label { display: grid; gap: .4rem; }
input, textarea, button { font: inherit; color: var(--text-color); background: var(--card-bg, transparent); border: 1px solid var(--border-color); border-radius: .5rem; padding: .7rem; }
button { cursor: pointer; }
button:disabled { opacity: .55; cursor: default; }
pre, code { overflow-wrap: anywhere; white-space: pre-wrap; }
</style>
