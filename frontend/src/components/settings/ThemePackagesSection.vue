<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import { useSettingsStore } from '@/stores/settings'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import ThemeAppearanceSection from './ThemeAppearanceSection.vue'
import { useUiLabels } from '@/utils/ui-labels'
import { useThemeStore } from '@/stores/theme'
import ThemeComponentPreview from './ThemeComponentPreview.vue'

const props = withDefaults(defineProps<{ active?: boolean }>(), { active: true })

interface ThemeItem {
  module_id: string
  version: string
  sha256: string
  name: { en: string; translations?: Record<string, string> }
  enabled: boolean
  is_selected: boolean
  is_available: boolean
  status: string
}
const { t, currentLanguage } = useI18n()
const uiLabel = useUiLabels()
const settings = useSettingsStore()
const modes = useThemeStore()
const items = ref<ThemeItem[]>([])
const selection = ref('')
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const message = ref('')
const previewBusy = ref(false)
const previewHash = ref<string | null>(null)
let previewController: AbortController | null = null
let previewRequest = 0
let initialMode: 'light' | 'dark' | null = null
const selectedHash = computed(() => items.value.find(item => item.is_selected)?.sha256 || '')
const label = (item: ThemeItem) => `${item.name.translations?.[currentLanguage.value] || item.name.en} · ${item.version}`
const previewName = computed(() => {
  const item = items.value.find(item => item.sha256 === previewHash.value)
  return item ? label(item) : t('themePackages.builtin', 'Built-in — saved custom colors')
})
const cancelPreview = (resetSelection = true) => {
  ++previewRequest
  previewController?.abort()
  previewController = null
  previewBusy.value = false
  previewHash.value = null
  settings.clearPackagePreview()
  if (initialMode) modes.setTheme(initialMode)
  initialMode = null
  if (resetSelection) selection.value = selectedHash.value
}
const base = '/api/v1/modules/themes'
async function preview() {
  if (busy.value || previewBusy.value || !props.active) return
  cancelPreview(false)
  const hash = selection.value
  const request = previewRequest
  const controller = new AbortController()
  previewController = controller
  previewBusy.value = true
  initialMode = modes.theme
  error.value = ''; message.value = ''
  try {
    const response = await http.get(`${base}/preview`, {
      params: hash ? { sha256: hash } : {}, signal: controller.signal, timeout: 5000,
    })
    const baseUrl = await http.getCurrentBackendUrl()
    if (request !== previewRequest || controller.signal.aborted) return
    if (!(await settings.previewThemeAppearance(response.data, baseUrl, controller.signal))) throw new Error('unavailable')
    if (request === previewRequest && !controller.signal.aborted) previewHash.value = hash
  } catch {
    if (request === previewRequest) { cancelPreview(false); error.value = 'previewFailed' }
  } finally {
    if (request === previewRequest) previewBusy.value = false
  }
}
async function loadCatalog() {
  const response = await http.get(`${base}/catalog`)
  items.value = response.data.items
  selection.value = selectedHash.value
  loaded.value = true
}
async function run(action: () => Promise<unknown>, success?: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await action()
    await Promise.all([loadCatalog(), settings.loadThemeAppearance()])
    message.value = success || ''
  } catch {
    error.value = 'failed'
  } finally {
    cancelPreview(false)
    busy.value = false
  }
}
const refresh = () => { cancelPreview(false); return run(async () => {}) }
const apply = () => run(() => http.post(`${base}/selection`, { sha256: selection.value || null }),
  'applied')
watch(selection, () => cancelPreview(false))
watch(() => props.active, active => { if (!active) cancelPreview() })
onBeforeUnmount(() => cancelPreview(false))
onMounted(refresh)
</script>

<template>
  <SettingsSection :title="uiLabel('themeWorkspace')" class="theme-workspace ui-v2 ui-section"
    :data-button="settings.uiDesign?.components.button" :data-card="settings.uiDesign?.components.card">
    <p class="theme-help">{{ t('themePackages.help', 'The theme applies to this installation. Light/dark mode remains a separate preference. Header and menu settings are preserved.') }}</p>
    <form class="theme-choice" @submit.prevent="apply">
      <label for="installed-theme">{{ t('themePackages.select', 'Application theme') }}</label>
      <select id="installed-theme" v-model="selection" class="input ui-control" :disabled="busy || previewBusy || !loaded">
        <option value="">{{ t('themePackages.builtin', 'Built-in — saved custom colors') }}</option>
        <option v-for="item in items.filter(item => item.is_available || item.is_selected)" :key="item.sha256"
          :value="item.sha256" :disabled="!item.is_available">{{ label(item) }}</option>
      </select>
      <div class="theme-actions">
        <button type="button" class="ui-button" :disabled="busy || previewBusy || !loaded" @click="preview">{{ uiLabel('previewTheme') }}</button>
        <button type="submit" class="ui-button ui-button--primary" :disabled="busy || previewBusy || !loaded || selection === selectedHash">
          {{ t('themePackages.apply', 'Apply theme') }}
        </button>
        <button type="button" class="ui-button" :disabled="busy || previewBusy" @click="refresh">{{ t('themePackages.refresh', 'Refresh') }}</button>
      </div>
    </form>
    <section v-if="previewBusy || previewHash !== null" class="theme-preview" :aria-label="uiLabel('previewTheme')">
      <p role="status">{{ previewBusy ? uiLabel('loading') : `${uiLabel('previewTheme')}: ${previewName}` }}</p>
      <p class="theme-help">{{ uiLabel('packagePreviewNote') }}</p>
      <div class="theme-actions">
        <label v-if="!previewBusy" class="theme-preview-mode">{{ uiLabel('mode') }}
          <select class="input ui-control" :value="modes.theme" :disabled="busy" @change="modes.setTheme(($event.target as HTMLSelectElement).value as 'light' | 'dark')">
            <option value="light">{{ uiLabel('light') }}</option><option value="dark">{{ uiLabel('dark') }}</option>
          </select>
        </label>
        <button type="button" class="ui-button" :disabled="busy" @click="cancelPreview()">{{ uiLabel('cancel') }}</button>
      </div>
      <p v-if="settings.previewAssetWarnings.length" role="status" class="theme-help">{{ uiLabel('previewAssetsFallback') }}</p>
      <p class="theme-help">{{ uiLabel('applyBeforeEdit') }}</p>
      <ThemeComponentPreview v-if="!previewBusy" />
    </section>
    <p class="theme-help">{{ t('themePackages.extensionsHelp', 'Upload, enable, disable and delete theme packages in Extensions.') }}</p>
    <p v-if="loaded && !items.some(item => item.is_available)" class="theme-help">{{ t('themePackages.noneEnabled', 'No enabled themes are available. Built-in settings remain available.') }}</p>
    <p v-if="items.some(item => item.is_selected && !item.is_available)" class="theme-help">{{ t('themePackages.unavailableHelp', 'Package missing or invalid. Built-in settings are used if it was selected.') }}</p>
    <p v-if="busy" role="status" class="theme-help">{{ t('themePackages.working', 'Working…') }}</p>
    <p v-if="error" role="alert" class="theme-error">{{ error === 'previewFailed' ? uiLabel('previewThemeFailed') : t(`themePackages.${error}`, error) }}</p>
    <p v-if="message" role="status">{{ t(`themePackages.${message}`, message) }}</p>
    <p v-if="settings.activeTheme && !previewBusy && previewHash === null" class="theme-help">{{ uiLabel('themeColorSettings') }}</p>
    <p v-if="settings.assetWarnings.length" role="status" class="theme-help">{{ t('themePackages.assetFallback', 'A theme font or image could not be loaded. System font and saved branding remain available.') }}</p>
    <p v-if="settings.appearanceUnavailable" role="status" class="theme-help">{{ uiLabel('appearanceOffline') }}</p>
    <ThemeAppearanceSection v-if="active && loaded && !previewBusy && !settings.isPackagePreview && !items.some(item => item.is_selected && !item.is_available)" :sha256="selectedHash || null" :disabled="busy" />
    <details class="theme-recovery"><summary>{{ uiLabel('recovery') }}</summary>
      <RouterLink :to="{ name: 'UiPreview', query: { recovery: '1' } }">{{ uiLabel('restoreInstalled') }}</RouterLink>
    </details>
  </SettingsSection>
</template>

<style scoped>
.theme-help { color: var(--text-secondary); font-size: 0.9rem; }
.theme-workspace { background: var(--ui-surface, var(--card-bg)); color: var(--ui-text, var(--text-primary)); border-color: var(--ui-border, var(--card-border)); }
.theme-recovery { margin-top: 1rem; font-size: .9rem; }
.theme-choice { display: grid; gap: 0.65rem; min-width: 0; }
.input { width: 100%; min-width: 0; border: 1px solid var(--input-border); background: var(--input-bg); color: var(--text-primary); }
.input:focus-visible, .ui-button:focus-visible { outline: 2px solid var(--input-focus-border); outline-offset: 2px; }
.theme-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.theme-error { color: var(--button-danger-bg); }
.theme-preview { margin: 1rem 0; padding: 1rem; border: 1px solid var(--input-focus-border); border-radius: var(--border-radius-sm); overflow-wrap: anywhere; }
.theme-preview p { margin: 0 0 .65rem; }
.theme-preview-mode { display: grid; gap: .35rem; min-width: 0; }
.theme-preview .theme-actions { align-items: end; }
</style>
