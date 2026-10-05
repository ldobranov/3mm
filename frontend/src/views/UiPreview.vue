<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { builtinUiDesign } from '@/utils/ui-design'
import { useUiLabels } from '@/utils/ui-labels'
import { useI18n } from '@/utils/i18n'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import http from '@/utils/dynamic-http'

const settings = useSettingsStore()
const modes = useThemeStore()
const route = useRoute()
const router = useRouter()
const label = useUiLabels()
const { currentLanguage, setPreviewLanguage } = useI18n()
const design = reactive(builtinUiDesign())
design.header_style = 'theme' // Explicit, temporary choice. Does not erase saved colors.
const recovery = computed(() => route.query.recovery === '1')
const restoring = ref(false)
const restoreMessage = ref<'restoreDone' | 'restoreFailed' | null>(null)
const open = ref(false)
const name = ref('')
const description = ref('')
const enabled = ref(true)
const attempted = ref(false)
const validated = ref(false)
const invalid = computed(() => attempted.value && !name.value.trim())
const initialMode = modes.theme
const initialLanguage = currentLanguage.value
watch([design, recovery], () => {
  settings.appearanceRecovery = recovery.value
  settings.setDesignPreview(recovery.value ? null : design)
}, { deep: true, immediate: true })
onBeforeUnmount(() => {
  settings.appearanceRecovery = false
  settings.setDesignPreview(null)
  modes.setTheme(initialMode) // Restore the browser mode; no account preference API write.
  void setPreviewLanguage(initialLanguage)
})
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
const restore = () => {
  Object.assign(design, builtinUiDesign(), { header_style: 'theme' })
  void router.replace({ name: 'UiPreview' })
}
const validate = () => {
  attempted.value = true
  if (invalid.value) return
  validated.value = true
  open.value = false
}
</script>

<template>
  <section v-if="recovery" class="ui-recovery">
    <h1>{{ label('recovery') }}</h1>
    <p>{{ label('recoveryNote') }}</p>
    <button type="button" @click="restore">{{ label('restore') }}</button>
    <button type="button" :disabled="restoring" @click="restoreInstalled">{{ label('restoreInstalled') }}</button>
    <p v-if="restoreMessage" :role="restoreMessage === 'restoreFailed' ? 'alert' : 'status'">{{ label(restoreMessage) }}</p>
    <RouterLink to="/settings">{{ label('exit') }}</RouterLink>
  </section>
  <div v-else class="ui-stack ui-preview">
    <div class="ui-preview-heading">
      <div><h1>{{ label('preview') }}</h1><p class="ui-muted">{{ label('previewNote') }}</p></div>
      <RouterLink to="/settings" class="ui-button">{{ label('exit') }}</RouterLink>
    </div>
    <section class="ui-section ui-stack" :aria-label="label('preferences')">
      <h2>{{ label('preferences') }}</h2>
      <div class="ui-preview-controls">
        <label class="ui-field"><span>{{ label('layout') }}</span>
          <select v-model="design.layout.navigation" class="ui-control"><option value="sidebar">{{ label('sidebar') }}</option><option value="top">{{ label('top') }}</option></select>
        </label>
        <label class="ui-field"><span>{{ label('density') }}</span>
          <select v-model="design.layout.density" class="ui-control"><option value="compact">{{ label('compact') }}</option><option value="comfortable">{{ label('comfortable') }}</option></select>
        </label>
        <label class="ui-field"><span>{{ label('buttons') }}</span>
          <select v-model="design.components.button" class="ui-control"><option value="solid">{{ label('solid') }}</option><option value="outline">{{ label('outline') }}</option></select>
        </label>
        <label class="ui-field"><span>{{ label('cards') }}</span>
          <select v-model="design.components.card" class="ui-control"><option value="bordered">{{ label('bordered') }}</option><option value="raised">{{ label('raised') }}</option></select>
        </label>
        <label class="ui-field"><span>{{ label('mode') }}</span>
          <select :value="modes.theme" class="ui-control" @change="modes.setTheme(($event.target as HTMLSelectElement).value as 'light' | 'dark')">
            <option value="light">{{ label('light') }}</option><option value="dark">{{ label('dark') }}</option>
          </select>
        </label>
      </div>
      <label class="ui-check"><input type="checkbox" :checked="design.header_style === 'theme'"
        @change="design.header_style = ($event.target as HTMLInputElement).checked ? 'theme' : 'saved'" /><span>{{ label('header') }}</span></label>
    </section>
    <div class="ui-preview-grid">
      <section class="ui-section ui-stack">
        <h2>{{ label('primitives') }}</h2>
        <div class="ui-row"><UiButton variant="primary">{{ label('primary') }}</UiButton><UiButton>{{ label('secondary') }}</UiButton><UiButton variant="danger">{{ label('danger') }}</UiButton></div>
        <div class="ui-row"><UiButton disabled>{{ label('disabled') }}</UiButton><UiButton loading>{{ label('loading') }}</UiButton></div>
        <p class="ui-help">{{ label('enabledHelp') }}</p>
        <UiButton variant="primary" @click="open = true">{{ label('dialog') }}</UiButton>
        <p v-if="validated" class="ui-help" role="status">{{ label('validated') }}</p>
      </section>
      <section class="ui-section ui-stack">
        <h2>{{ label('forms') }}</h2>
        <label class="ui-field"><span>{{ label('name') }}</span><input v-model="name" class="ui-control" :placeholder="label('namePlaceholder')" :aria-invalid="invalid" :aria-describedby="invalid ? 'ui-name-error' : undefined" /></label>
        <p v-if="invalid" id="ui-name-error" class="ui-error" role="alert">{{ label('error') }}</p>
        <label class="ui-field"><span>{{ label('description') }}</span><textarea v-model="description" class="ui-control" :placeholder="label('descriptionPlaceholder')"></textarea></label>
        <label class="ui-check"><input v-model="enabled" type="checkbox" /><span>{{ label('enabled') }}</span></label>
      </section>
    </div>
    <section class="ui-section ui-stack">
      <h2>{{ label('table') }}</h2>
      <div class="ui-table-wrap"><table class="ui-table"><caption class="visually-hidden">{{ label('table') }}</caption>
        <thead><tr><th scope="col">{{ label('resource') }}</th><th scope="col">{{ label('status') }}</th><th scope="col">{{ label('owner') }}</th></tr></thead>
        <tbody><tr><td>{{ label('example') }}</td><td><span class="ui-badge ui-badge--success">✓ {{ label('ready') }}</span></td><td>{{ label('currentUser') }}</td></tr>
          <tr><td>{{ label('secondary') }}</td><td><span class="ui-badge ui-badge--warning">◷ {{ label('pending') }}</span></td><td>—</td></tr></tbody>
      </table></div>
    </section>
    <UiDialog v-model:open="open" :title="label('dialogTitle')" :close-label="label('close')">
      <form id="ui-example-form" class="ui-stack" @submit.prevent="validate">
        <p class="ui-help">{{ label('enabledHelp') }}</p>
        <label class="ui-field"><span>{{ label('name') }}</span><input v-model="name" autofocus class="ui-control" :aria-invalid="invalid" :aria-describedby="invalid ? 'ui-dialog-error' : undefined" /></label>
        <p v-if="invalid" id="ui-dialog-error" class="ui-error" role="alert">{{ label('error') }}</p>
      </form>
      <template #actions><UiButton @click="open = false">{{ label('cancel') }}</UiButton><UiButton variant="primary" type="submit" form="ui-example-form">{{ label('confirm') }}</UiButton></template>
    </UiDialog>
  </div>
</template>

<style scoped>
.ui-preview-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.ui-preview-heading h1 { margin: 0 0 6px; }
.ui-preview-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 16px; }
.ui-preview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
/* Independent of selected tokens: protected recovery must always be readable. */
.ui-recovery { max-width: 720px; margin: 32px auto; padding: 24px; color: #20252d; background: #fff; border: 1px solid #667085; border-radius: 8px; font: 16px/1.5 system-ui, sans-serif; }
.ui-recovery h1 { font-size: 24px; }
.ui-recovery button { padding: 10px 16px; margin: 16px 16px 0 0; border: 1px solid #475467; background: #fff; color: #20252d; border-radius: 4px; }
.ui-recovery a { color: #005c53; }
.ui-recovery :focus-visible { outline: 2px solid #005c53; outline-offset: 3px; }
@media (max-width: 760px) { .ui-preview-grid { grid-template-columns: minmax(0, 1fr); } .ui-recovery { margin: 16px; } }
</style>
