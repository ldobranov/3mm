<template>
  <section class="fleet-pairing" aria-labelledby="fleet-pairing-title">
    <header>
      <h2 id="fleet-pairing-title">{{ t('fleetPairing.title') }}</h2>
      <button type="button" :disabled="loading || busy !== null" @click="refresh()">{{ t('fleetPairing.refresh') }}</button>
    </header>
    <p>{{ t('fleetPairing.help') }}</p>
    <p v-if="error" role="alert">{{ t('fleetPairing.failed') }}</p>
    <p v-if="message" role="status">{{ t(message) }}</p>
    <p v-if="loading && !items.length">{{ t('fleetPairing.loading') }}</p>
    <p v-else-if="!error && !items.length">{{ t('fleetPairing.empty') }}</p>
    <article v-for="item in items" :key="item.request_id" class="fleet-request">
      <div>
        <strong>{{ item.display_name }}</strong>
        <code>{{ item.device_id }}</code>
      </div>
      <div class="fleet-actions">
        <button type="button" class="fleet-approve" :disabled="busy !== null || loading" @click="decide(item, 'approve')">{{ t('fleetPairing.add') }}</button>
        <button type="button" :disabled="busy !== null || loading" @click="decide(item, 'reject')">{{ t('fleetPairing.reject') }}</button>
      </div>
    </article>
    <button v-if="items.length === 50" type="button" :disabled="loading || busy !== null" @click="refresh(items[items.length - 1]!.request_id)">{{ t('fleetPairing.next') }}</button>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'

interface PendingRequest { request_id: number; device_id: string; display_name: string }
const emit = defineEmits<{ approved: []; registryRefresh: [] }>()
const { t } = useI18n()
const items = ref<PendingRequest[]>([])
const loading = ref(false)
const busy = ref<number | null>(null)
const error = ref(false)
const message = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let registryRefreshes = 0
const controller = new AbortController()

async function refresh(afterId = 0) {
  if (loading.value || disposed) return
  loading.value = true
  try {
    const response = await http.get('/api/v1/pairing/requests', {
      params: { after_id: afterId, limit: 50 }, signal: controller.signal, timeout: 10000,
    })
    if (!disposed) { items.value = response.data; error.value = false }
  } catch {
    if (!disposed) error.value = true
  } finally { loading.value = false }
}

async function decide(item: PendingRequest, action: 'approve' | 'reject') {
  if (busy.value !== null) return
  busy.value = item.request_id
  error.value = false
  message.value = ''
  try {
    await http.post(`/api/v1/pairing/requests/${item.request_id}/${action}`, undefined, {
      signal: controller.signal, timeout: 10000,
    })
    if (disposed) return
    message.value = action === 'approve' ? 'fleetPairing.approved' : 'fleetPairing.rejected'
    if (action === 'approve') { registryRefreshes = 4; emit('approved') }
    await refresh()
  } catch {
    // A lost reply is not confirmation. Refresh before offering another decision.
    await refresh()
    if (!disposed) error.value = true
  } finally { busy.value = null }
}

async function poll() {
  if (busy.value === null && !document.hidden) await refresh()
  if (!disposed && registryRefreshes > 0) { registryRefreshes--; emit('registryRefresh') }
  if (!disposed) timer = setTimeout(poll, 10000)
}
onMounted(poll)
onUnmounted(() => { disposed = true; clearTimeout(timer); controller.abort() })
</script>

<style scoped>
.fleet-pairing { padding: 1.25rem; margin-bottom: 1.5rem; border: 1px solid var(--surface-border); border-radius: var(--border-radius-lg, 8px); background: var(--surface-1); color: var(--text-primary); }
header, .fleet-request, .fleet-actions { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
header, .fleet-request { justify-content: space-between; }
h2 { font-size: 1.2rem; margin: 0; }
p { color: var(--text-secondary); margin: .75rem 0; }
[role="alert"] { color: var(--error-color); }
.fleet-request { padding: .85rem 0; border-top: 1px solid var(--surface-border); }
.fleet-request > div { min-width: 0; }
code { display: block; overflow-wrap: anywhere; color: var(--text-secondary); font-size: .8rem; }
button { border: 1px solid var(--surface-border); border-radius: 6px; padding: .5rem .8rem; background: var(--surface-2); color: var(--text-primary); }
button:disabled { opacity: .5; cursor: wait; }
.fleet-approve { background: var(--primary-color); color: #fff; }
button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
@media (max-width: 480px) { .fleet-actions { width: 100%; } .fleet-actions button { flex: 1; } }
</style>
