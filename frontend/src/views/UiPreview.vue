<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'
import { useUiLabels } from '@/utils/ui-labels'
import http from '@/utils/dynamic-http'

const settings = useSettingsStore()
const route = useRoute()
const router = useRouter()
const label = useUiLabels()
const recovery = computed(() => route.query.recovery === '1')
const editor = { name: 'Settings', query: { section: 'theme' } }
const restoring = ref(false)
const restoreMessage = ref<'restoreDone' | 'restoreFailed' | null>(null)
// Keep old bookmarks working, without a second editor or a hardcoded sample theme.
watch(recovery, enabled => {
  settings.appearanceRecovery = enabled
  settings.setDesignPreview(null)
  if (!enabled) void router.replace(editor)
}, { immediate: true })
onBeforeUnmount(() => { settings.appearanceRecovery = false })
const restoreInstalled = async () => {
  if (restoring.value) return
  restoring.value = true
  restoreMessage.value = null
  try {
    await http.post('/api/v1/modules/themes/selection', { sha256: null })
    await http.post('/api/v1/modules/themes/customization', { sha256: null, preferences: null })
    await settings.loadThemeAppearance()
    restoreMessage.value = 'restoreDone'
  } catch { restoreMessage.value = 'restoreFailed' }
  finally { restoring.value = false }
}
</script>

<template>
  <section v-if="recovery" class="ui-recovery">
    <h1>{{ label('recovery') }}</h1>
    <p>{{ label('recoveryNote') }}</p>
    <button type="button" :disabled="restoring" @click="restoreInstalled">{{ label('restoreInstalled') }}</button>
    <p v-if="restoreMessage" :role="restoreMessage === 'restoreFailed' ? 'alert' : 'status'">{{ label(restoreMessage) }}</p>
    <RouterLink :to="editor">{{ label('exit') }}</RouterLink>
  </section>
</template>

<style scoped>
/* Independent of selected tokens: protected recovery must always be readable. */
.ui-recovery { max-width: 720px; margin: 32px auto; padding: 24px; color: #20252d; background: #fff; border: 1px solid #667085; border-radius: 8px; font: 16px/1.5 system-ui, sans-serif; }
.ui-recovery h1 { font-size: 24px; }
.ui-recovery button { padding: 10px 16px; margin: 16px 16px 0 0; border: 1px solid #475467; background: #fff; color: #20252d; border-radius: 4px; }
.ui-recovery a { display: block; margin-top: 16px; color: #005c53; }
.ui-recovery :focus-visible { outline: 2px solid #005c53; outline-offset: 3px; }
@media (max-width: 760px) { .ui-recovery { margin: 16px; } }
</style>
