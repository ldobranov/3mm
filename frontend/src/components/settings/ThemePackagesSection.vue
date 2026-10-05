<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import { useSettingsStore } from '@/stores/settings'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'

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
const settings = useSettingsStore()
const items = ref<ThemeItem[]>([])
const selection = ref('')
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const message = ref('')
const selectedHash = computed(() => items.value.find(item => item.is_selected)?.sha256 || '')
const label = (item: ThemeItem) => `${item.name.translations?.[currentLanguage.value] || item.name.en} · ${item.version}`
const base = '/api/v1/modules/themes'
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
    busy.value = false
  }
}
const refresh = () => run(async () => {})
const apply = () => run(() => http.post(`${base}/selection`, { sha256: selection.value || null }),
  'applied')
onMounted(refresh)
</script>

<template>
  <SettingsSection :title="t('themePackages.title', 'Installed themes')">
    <p class="theme-help">{{ t('themePackages.help', 'The theme applies to this installation. Light/dark mode remains a separate preference. Header and menu settings are preserved.') }}</p>
    <form class="theme-choice" @submit.prevent="apply">
      <label for="installed-theme">{{ t('themePackages.select', 'Application theme') }}</label>
      <select id="installed-theme" v-model="selection" class="input" :disabled="busy || !loaded">
        <option value="">{{ t('themePackages.builtin', 'Built-in — saved custom colors') }}</option>
        <option v-for="item in items.filter(item => item.is_available || item.is_selected)" :key="item.sha256"
          :value="item.sha256" :disabled="!item.is_available">{{ label(item) }}</option>
      </select>
      <div class="theme-actions">
        <button type="submit" class="button button-primary" :disabled="busy || !loaded || selection === selectedHash">
          {{ t('themePackages.apply', 'Apply theme') }}
        </button>
        <button type="button" class="button" :disabled="busy" @click="refresh">{{ t('themePackages.refresh', 'Refresh') }}</button>
      </div>
    </form>
    <p class="theme-help">{{ t('themePackages.extensionsHelp', 'Upload, enable, disable and delete theme packages in Extensions.') }}</p>
    <p v-if="loaded && !items.some(item => item.is_available)" class="theme-help">{{ t('themePackages.noneEnabled', 'No enabled themes are available. Built-in settings remain available.') }}</p>
    <p v-if="items.some(item => item.is_selected && !item.is_available)" class="theme-help">{{ t('themePackages.unavailableHelp', 'Package missing or invalid. Built-in settings are used if it was selected.') }}</p>
    <p v-if="busy" role="status" class="theme-help">{{ t('themePackages.working', 'Working…') }}</p>
    <p v-if="error" role="alert" class="theme-error">{{ t(`themePackages.${error}`, error) }}</p>
    <p v-if="message" role="status">{{ t(`themePackages.${message}`, message) }}</p>
    <p v-if="settings.activeTheme" class="theme-help">{{ t('themePackages.legacyHelp', 'Package colors are read-only. Choose built-in to edit your saved custom colors; they have not been erased.') }}</p>
    <p v-if="settings.assetWarnings.length" role="status" class="theme-help">{{ t('themePackages.assetFallback', 'A theme font or image could not be loaded. System font and saved branding remain available.') }}</p>
    <RouterLink :to="{ name: 'UiPreview', query: { recovery: '1' } }">{{ t('uiPlatform.recovery', 'Built-in appearance recovery') }}</RouterLink>
  </SettingsSection>
</template>

<style scoped>
.theme-help { color: var(--text-secondary); font-size: 0.9rem; }
.theme-choice { display: grid; gap: 0.65rem; min-width: 0; }
.input { width: 100%; min-width: 0; border: 1px solid var(--input-border); background: var(--input-bg); color: var(--text-primary); }
.input:focus-visible, .button:focus-visible { outline: 2px solid var(--input-focus-border); outline-offset: 2px; }
.theme-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.button:not(.button-primary) { background: var(--panel-bg); color: var(--text-primary); border: 1px solid var(--card-border); }
.button:disabled { opacity: 0.5; cursor: not-allowed; }
.theme-error { color: var(--button-danger-bg); }
</style>
