<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useUiLabels } from '@/utils/ui-labels'
import { useI18n } from '@/utils/i18n'
import { designPreferences, parseThemePreferences, themePreferencesValid, LEGACY_UI_COLOR_KEYS, type ThemePreferences } from '@/utils/theme-customization'
import { UI_COLOR_KEYS, type UiColors } from '@/utils/ui-design'
import http from '@/utils/dynamic-http'
import ColorPicker from '@/components/ColorPicker.vue'

const props = defineProps<{ sha256: string | null; disabled?: boolean }>()
const settings = useSettingsStore()
const modes = useThemeStore()
const label = useUiLabels()
const { t } = useI18n()
const defaults = computed(() => {
  const value = designPreferences(settings.baseUiDesign, settings.headerSettings)
  // Keep legacy colors intact, but don't start a new customization with unreadable text.
  return parseThemePreferences(value) ? value : { ...value, header_style: 'theme' as const }
})
const baseline = computed(() => settings.themePreferences || defaults.value)
const copy = (value: ThemePreferences): ThemePreferences => JSON.parse(JSON.stringify(value))
const draft = reactive<ThemePreferences>(copy(baseline.value))
const replaceDraft = () => {
  delete draft.colors
  Object.assign(draft, copy(baseline.value))
}
const dirty = computed(() => JSON.stringify(draft) !== JSON.stringify(baseline.value))
const valid = computed(() => themePreferencesValid(settings.baseUiDesign, draft, settings.activeTheme?.theme_extension_version ?? null))
const paletteMode = ref(modes.theme)
const palette = computed(() => ({ ...settings.baseUiDesign[paletteMode.value], ...draft.colors?.[paletteMode.value] }))
const colorGroups = computed(() => {
  const allowed: readonly string[] = settings.activeTheme?.theme_extension_version === 2 ? UI_COLOR_KEYS : LEGACY_UI_COLOR_KEYS
  return [
    { title: label('colorSurfaces'), keys: ['canvas', 'content', 'surface', 'surface_alt', 'border'] },
    { title: label('colorTexts'), keys: ['text', 'text_secondary', 'text_muted'] },
    { title: label('colorButtons'), keys: ['accent', 'accent_text', 'secondary', 'secondary_text', 'danger', 'danger_text'] },
    { title: label('colorStates'), keys: ['success', 'warning', 'focus'] },
  ].map(group => ({ ...group, keys: group.keys.filter(key => allowed.includes(key)) as (keyof UiColors)[] }))
    .filter(group => group.keys.length)
})
const colorLabel = (key: keyof UiColors) => label(`color_${key}`)
const updateColor = (key: keyof UiColors, value: string) => {
  const mode = paletteMode.value
  const colors = { ...draft.colors, [mode]: { ...draft.colors?.[mode] } }
  if (value.toLowerCase() === settings.baseUiDesign[mode][key].toLowerCase()) delete colors[mode]![key]
  else colors[mode]![key] = value
  if (!Object.keys(colors[mode]!).length) delete colors[mode]
  if (Object.keys(colors).length) draft.colors = colors
  else delete draft.colors
}
const resetPalette = () => {
  if (!draft.colors) return
  const colors = { ...draft.colors }
  delete colors[paletteMode.value]
  if (Object.keys(colors).length) draft.colors = colors
  else delete draft.colors
}
const busy = ref(false)
const message = ref('')
const failure = ref('')
const modeBusy = ref(false)
const modeFailure = ref(false)
const changeMode = async (event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  if (value !== 'light' && value !== 'dark') return
  const previous = modes.theme
  modeBusy.value = true; modeFailure.value = false
  try {
    if (localStorage.getItem('authToken')) {
      await http.post('/settings/create', { key: 'user_theme', value, description: 'User theme preference' })
    }
    modes.setTheme(value)
  } catch {
    modes.setTheme(previous)
    modeFailure.value = true
  } finally { modeBusy.value = false }
}
let previousHash = props.sha256
let previousBaseline = JSON.stringify(baseline.value)
watch([baseline, () => props.sha256], () => {
  const nextBaseline = JSON.stringify(baseline.value)
  if (props.sha256 === previousHash && nextBaseline === previousBaseline) return
  if (props.sha256 !== previousHash || JSON.stringify(draft) === previousBaseline) {
    replaceDraft()
    settings.setPreferencePreview(null)
    message.value = ''; failure.value = ''
  }
  previousHash = props.sha256
  previousBaseline = nextBaseline
}, { deep: true })
watch(draft, () => {
  if (busy.value) return
  // Invalid colors never reach the real shell, and nothing is persisted yet.
  settings.setPreferencePreview(dirty.value && valid.value ? draft : null)
  message.value = ''; failure.value = ''
}, { deep: true, flush: 'sync' })
const cancel = () => {
  replaceDraft()
  settings.setPreferencePreview(null)
  failure.value = ''; message.value = ''
}
const save = async (reset = false) => {
  if (busy.value || props.disabled || (!reset && !valid.value)) return
  busy.value = true; failure.value = ''; message.value = ''
  try {
    await http.post('/api/v1/modules/themes/customization', {
      sha256: props.sha256, preferences: reset ? null : { ...draft },
    })
    await settings.loadThemeAppearance()
    settings.setPreferencePreview(null)
    replaceDraft()
    message.value = reset ? 'resetDone' : 'saved'
    window.dispatchEvent(new Event('settings-updated'))
  } catch { failure.value = 'failed' }
  finally { busy.value = false }
}
onBeforeUnmount(() => settings.setPreferencePreview(null))
</script>

<template>
  <section class="appearance-editor" :aria-label="label('appearanceTitle')">
    <h3>{{ label('appearanceTitle') }}</h3>
    <p class="appearance-help">{{ label('appearanceHelp') }}</p>
    <form @submit.prevent="save()">
      <fieldset :disabled="busy || disabled" class="appearance-fields">
        <div class="appearance-grid">
          <label class="appearance-field"><span>{{ label('layout') }}</span>
            <select v-model="draft.navigation" class="input" data-field="navigation"><option value="sidebar">{{ label('sidebar') }}</option><option value="top">{{ label('top') }}</option></select>
          </label>
          <label class="appearance-field"><span>{{ label('density') }}</span>
            <select v-model="draft.density" class="input" data-field="density"><option value="compact">{{ label('compact') }}</option><option value="comfortable">{{ label('comfortable') }}</option></select>
          </label>
          <label class="appearance-field"><span>{{ label('buttons') }}</span>
            <select v-model="draft.button" class="input" data-field="button"><option value="solid">{{ label('solid') }}</option><option value="outline">{{ label('outline') }}</option></select>
          </label>
          <label class="appearance-field"><span>{{ label('cards') }}</span>
            <select v-model="draft.card" class="input" data-field="card"><option value="bordered">{{ label('bordered') }}</option><option value="raised">{{ label('raised') }}</option></select>
          </label>
        </div>
        <label class="appearance-check"><input type="checkbox" :checked="draft.header_style === 'saved'" data-field="custom-header"
          @change="draft.header_style = ($event.target as HTMLInputElement).checked ? 'saved' : 'theme'" />
          <span>{{ label('customHeader') }}</span>
        </label>
        <div v-if="draft.header_style === 'saved'" class="appearance-grid">
          <ColorPicker :label="label('headerBackground')" v-model="draft.header_background_color" />
          <ColorPicker :label="label('headerText')" v-model="draft.header_text_color" />
        </div>
        <section v-if="settings.activeTheme" class="appearance-colors">
          <h4>{{ label('themeColors') }}</h4>
          <p class="appearance-help">{{ label('themeColorsHelp') }}</p>
          <label class="appearance-field appearance-mode"><span>{{ label('editPalette') }}</span>
            <select v-model="paletteMode" class="input" data-field="palette-mode">
              <option value="light">{{ label('light') }}</option><option value="dark">{{ label('dark') }}</option>
            </select>
          </label>
          <section v-for="group in colorGroups" :key="group.title" class="appearance-color-group">
            <h5>{{ group.title }}</h5>
            <div class="appearance-grid">
              <ColorPicker v-for="key in group.keys" :key="key" :data-color="key"
                :label="colorLabel(key)" :model-value="palette[key]" :placeholder="settings.baseUiDesign[paletteMode][key]"
                @update:model-value="updateColor(key, $event)" />
            </div>
          </section>
          <button type="button" class="button" data-action="reset-palette" :disabled="!draft.colors?.[paletteMode]" @click="resetPalette">{{ label('resetPalette') }}</button>
        </section>
        <p v-if="!valid" class="appearance-error" role="alert">{{ draft.colors ? label('colorContrast') : label('headerContrast') }}</p>
        <p class="appearance-help">{{ label('modeHelp') }}</p>
        <label class="appearance-field appearance-mode"><span>{{ label('mode') }}</span>
          <select :value="modes.theme" class="input" data-field="mode" :disabled="modeBusy" @change="changeMode">
            <option value="light">{{ label('light') }}</option><option value="dark">{{ label('dark') }}</option>
          </select>
        </label>
        <p v-if="modeFailure" class="appearance-error" role="alert">{{ t('settings.saveFailed', 'Save failed') }}</p>
        <div class="appearance-actions">
          <button type="submit" class="button button-primary" data-action="save" :disabled="!dirty || !valid">{{ busy ? t('settings.saving', 'Saving…') : label('saveAppearance') }}</button>
          <button type="button" class="button" data-action="discard" :disabled="!dirty" @click="cancel">{{ label('discardAppearance') }}</button>
          <button type="button" class="button" data-action="reset" :disabled="!settings.themePreferences && !dirty" @click="save(true)">{{ label('resetAppearance') }}</button>
        </div>
      </fieldset>
    </form>
    <p v-if="dirty" role="status" class="appearance-help">{{ label('unsavedAppearance') }}</p>
    <p v-if="failure" role="alert" class="appearance-error">{{ label('saveAppearanceFailed') }}</p>
    <p v-if="message" role="status">{{ label(message === 'saved' ? 'appearanceSaved' : 'appearanceReset') }}</p>
    <RouterLink :to="{ name: 'UiPreview' }">{{ label('componentPreview') }}</RouterLink>
  </section>
</template>

<style scoped>
.appearance-editor { border-top: 1px solid var(--card-border); margin-top: 1.25rem; padding-top: 1.25rem; min-width: 0; }
.appearance-editor h3 { font-size: 1.1rem; margin: 0 0 .5rem; }
.appearance-fields { border: 0; padding: 0; margin: 0; display: grid; gap: 1rem; min-width: 0; }
.appearance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; min-width: 0; }
.appearance-field { display: grid; gap: .4rem; min-width: 0; }
.appearance-mode { max-width: 16rem; }
.appearance-colors { display: grid; gap: 1rem; min-width: 0; border-top: 1px solid var(--card-border); padding-top: 1rem; }
.appearance-colors h4, .appearance-color-group h5 { margin: 0 0 .6rem; font-size: 1rem; }
.appearance-colors > .button { justify-self: start; }
.input { width: 100%; min-width: 0; color: var(--text-primary); background: var(--input-bg); border: 1px solid var(--input-border); }
.appearance-check { display: flex; align-items: center; gap: .6rem; }
.appearance-check input { flex: 0 0 auto; }
.appearance-help { color: var(--text-secondary); font-size: .9rem; margin: .5rem 0; }
.appearance-actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.button:not(.button-primary) { background: var(--panel-bg); color: var(--text-primary); border: 1px solid var(--card-border); }
.appearance-error { color: var(--button-danger-bg); }
.appearance-editor :focus-visible { outline: 2px solid var(--input-focus-border); outline-offset: 2px; }
@media (max-width: 600px) { .appearance-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
