<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import { UiButton, UiEditorForm, UiField } from '@/extension-ui/v1'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useUiLabels } from '@/utils/ui-labels'
import { applyThemePreferences, designPreferences, parseThemePreferences, themePreferencesValid, themeCustomizationOptions, type ThemeOptionField, type ThemePreferences } from '@/utils/theme-customization'
import type { UiColors } from '@/utils/ui-design'
import http from '@/utils/dynamic-http'
import ColorPicker from '@/components/ColorPicker.vue'
import ThemeComponentPreview from './ThemeComponentPreview.vue'
import ThemeMenuSettings from './ThemeMenuSettings.vue'

const props = defineProps<{ sha256: string | null; disabled?: boolean }>()
const settings = useSettingsStore()
const modes = useThemeStore()
const label = useUiLabels()
const id = useId()
const options = computed(() => themeCustomizationOptions(settings.activeTheme))
const fields = computed(() => (['navigation', 'density', 'button', 'card'] as const)
  .filter(key => options.value[key].length > 1)
  .map(key => ({ key, title: label(({ navigation: 'layout', density: 'density', button: 'buttons', card: 'cards' } as const)[key]),
    values: options.value[key].map(value => ({ value, label: label(value as 'sidebar') })) })))
const setVariant = (key: ThemeOptionField, value: string | boolean) => {
  if (typeof value === 'string' && options.value[key].includes(value)) (draft as unknown as Record<ThemeOptionField, string>)[key] = value
}
const defaults = computed(() => {
  const value = designPreferences(settings.baseUiDesign, settings.headerSettings)
  return parseThemePreferences(value) ? value : { ...value, header_style: 'theme' as const }
})
const baseline = computed(() => settings.themePreferences || defaults.value)
const copy = (value: ThemePreferences): ThemePreferences => JSON.parse(JSON.stringify(value))
const draft = reactive<ThemePreferences>(copy(baseline.value))
const replaceDraft = (value = baseline.value) => { delete draft.colors; delete draft.menu_layout; Object.assign(draft, copy(value)) }
const dirty = computed(() => JSON.stringify(draft) !== JSON.stringify(baseline.value))
const valid = computed(() => themePreferencesValid(settings.baseUiDesign, draft, settings.activeTheme?.theme_extension_version ?? null, options.value))
const previewDesign = computed(() => applyThemePreferences(settings.baseUiDesign, valid.value ? draft : baseline.value, settings.activeTheme?.theme_extension_version === 1))
const previewHeader = computed(() => ({ ...settings.headerSettings,
  backgroundColor: valid.value ? draft.header_background_color : baseline.value.header_background_color,
  textColor: valid.value ? draft.header_text_color : baseline.value.header_text_color }))
const paletteMode = ref(modes.theme)
const palette = computed(() => ({ ...settings.baseUiDesign[paletteMode.value], ...draft.colors?.[paletteMode.value] }))
const modeOptions = computed(() => ['light', 'dark'].map(value => ({ value, label: label(value as 'light') })))
const colorGroups = computed(() => [
  { title: label('colorSurfaces'), keys: ['canvas', 'content', 'surface', 'surface_alt', 'border'] },
  { title: label('colorTexts'), keys: ['text', 'text_secondary', 'text_muted'] },
  { title: label('colorButtons'), keys: ['accent', 'accent_text', 'secondary', 'secondary_text', 'danger', 'danger_text'] },
  { title: label('colorStates'), keys: ['success', 'warning', 'focus'] },
].map(group => ({ ...group, keys: group.keys.filter(key => options.value.colors.includes(key as keyof UiColors)) as (keyof UiColors)[] }))
  .filter(group => group.keys.length))
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
  const colors = { ...draft.colors }; delete colors[paletteMode.value]
  if (Object.keys(colors).length) draft.colors = colors
  else delete draft.colors
}
const busy = ref(false)
const message = ref(false)
const failure = ref('')
const state = ref<'idle' | 'unconfirmed' | 'conflict'>('idle')
const modeBusy = ref(false)
const modeFailure = ref(false)
const changeMode = async (value: string | boolean) => {
  if (modeBusy.value || props.disabled || (value !== 'light' && value !== 'dark')) return
  modeBusy.value = true; modeFailure.value = false
  try {
    if (localStorage.getItem('authToken')) await http.post('/settings/create', { key: 'user_theme', value, description: 'User theme preference' })
    modes.setTheme(value)
  } catch { modeFailure.value = true }
  finally { modeBusy.value = false }
}
let previousHash = props.sha256
let previousBaseline = JSON.stringify(baseline.value)
watch([baseline, () => props.sha256], () => {
  const next = JSON.stringify(baseline.value)
  if (props.sha256 === previousHash && next === previousBaseline) return
  if (busy.value) { previousBaseline = next; return }
  if (props.sha256 !== previousHash || JSON.stringify(draft) === previousBaseline) {
    replaceDraft(); state.value = 'idle'; failure.value = ''; message.value = false
  } else state.value = 'conflict'
  previousHash = props.sha256; previousBaseline = next
}, { deep: true })
watch(draft, () => { if (!busy.value) { message.value = false; failure.value = '' } }, { deep: true, flush: 'sync' })
const cancel = () => { replaceDraft(); failure.value = ''; message.value = false }
const reload = async () => {
  if (busy.value || props.disabled) return
  busy.value = true
  try {
    await settings.loadThemeAppearance()
    if (settings.appearanceUnavailable) throw new Error('unavailable')
    replaceDraft(); state.value = 'idle'; failure.value = ''; message.value = false
  } catch { failure.value = label('appearanceReloadFailed') }
  finally { busy.value = false }
}
const save = async () => {
  if (busy.value || props.disabled || !dirty.value || !valid.value || state.value !== 'idle') return
  busy.value = true; failure.value = ''; message.value = false
  try {
    await http.post('/api/v1/modules/themes/customization', { sha256: props.sha256, preferences: copy(draft) })
    await settings.loadThemeAppearance()
    if (settings.appearanceUnavailable) throw new Error('unconfirmed')
    replaceDraft(); message.value = true
    window.dispatchEvent(new Event('settings-updated'))
  } catch (error) {
    const status = (error as { response?: { status?: number } }).response?.status
    state.value = status === 409 ? 'conflict' : status && status >= 400 && status < 500 ? 'idle' : 'unconfirmed'
    failure.value = label('saveAppearanceFailed')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="appearance-editor ui-stack" :aria-label="label('appearanceTitle')">
    <section class="personal-mode ui-row" :aria-label="label('personalMode')">
      <UiField :id="`${id}-mode`" type="select" data-field="mode" :label="label('personalMode')" :description="label('modeHelp')"
        :model-value="modes.theme" :options="modeOptions" :disabled="modeBusy || disabled" @update:model-value="changeMode" />
      <p v-if="modeFailure" class="appearance-error" role="alert">{{ label('saveAppearanceFailed') }}</p>
    </section>
    <div class="appearance-workbench">
      <UiEditorForm :title="label('appearanceTitle')" :description="label('appearanceDraftHelp')"
        :dirty="dirty" :valid="valid" :busy="busy" :disabled="disabled" :state="state" :error="failure"
        :save-label="label('saveAppearance')" :cancel-label="label('discardAppearance')"
        :dirty-label="label('unsavedAppearance')" :saved-label="label('appearanceClean')"
        :unconfirmed-label="label('appearanceUnconfirmed')" :conflict-label="label('appearanceConflict')"
        @save="save" @cancel="cancel">
        <div class="appearance-grid">
          <UiField v-for="field in fields" :key="field.key" :id="`${id}-${field.key}`" type="select" :data-field="field.key"
            :label="field.title" :model-value="draft[field.key]" :options="field.values" @update:model-value="setVariant(field.key, $event)" />
        </div>
        <UiField v-if="options.header_style.length > 1" :id="`${id}-header`" type="checkbox" data-field="custom-header"
          :label="label('customHeader')" :model-value="draft.header_style === 'saved'"
          @update:model-value="draft.header_style = $event === true ? 'saved' : 'theme'" />
        <div v-if="draft.header_style === 'saved'" class="appearance-grid">
          <ColorPicker data-field="header-background" :label="label('headerBackground')" v-model="draft.header_background_color" />
          <ColorPicker data-field="header-text" :label="label('headerText')" v-model="draft.header_text_color" />
        </div>
        <ThemeMenuSettings :model-value="draft.menu_layout" :navigation="draft.navigation"
          @update:model-value="$event ? (draft.menu_layout = $event) : delete draft.menu_layout" />
        <section v-if="colorGroups.length" class="appearance-colors ui-stack">
          <UiField :id="`${id}-palette`" type="select" data-field="palette-mode" :label="label('editPalette')"
            :description="label('palettePreviewHelp')" :model-value="paletteMode" :options="modeOptions"
            @update:model-value="($event === 'light' || $event === 'dark') && (paletteMode = $event)" />
          <details v-for="group in colorGroups" :key="group.title" class="appearance-color-group">
            <summary>{{ group.title }}</summary>
            <div class="appearance-grid">
              <ColorPicker v-for="key in group.keys" :key="key" :data-color="key" :label="label(`color_${key}`)"
                :model-value="palette[key]" :placeholder="settings.baseUiDesign[paletteMode][key]" @update:model-value="updateColor(key, $event)" />
            </div>
          </details>
          <UiButton data-action="reset-palette" :disabled="!draft.colors?.[paletteMode]" @click="resetPalette">{{ label('resetPalette') }}</UiButton>
        </section>
        <p v-if="!valid" class="appearance-error" role="alert">{{ label('colorContrast') }}</p>
        <UiButton data-action="reset" @click="replaceDraft(defaults)">{{ label('resetDraft') }}</UiButton>
        <template #recovery><UiButton :disabled="busy || disabled" data-action="reload" @click="reload">{{ label('reloadAppearance') }}</UiButton></template>
      </UiEditorForm>
      <aside class="appearance-samples ui-stack">
        <p class="ui-help" role="status">{{ label(valid ? 'draftPreviewOnly' : 'invalidDraftPreview') }}</p>
        <ThemeComponentPreview :mode="paletteMode" :design="previewDesign" :header="previewHeader" />
      </aside>
    </div>
    <p v-if="message" role="status">{{ label('appearanceSaved') }}</p>
  </section>
</template>

<style scoped>
.appearance-editor { border-top: 1px solid var(--ui-border); padding-top: calc(var(--ui-space) * 5); min-width: 0; }
.personal-mode .ui-field { max-width: 32rem; }
.appearance-workbench { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: calc(var(--ui-space) * 6); align-items: start; }
.appearance-samples { position: sticky; top: 1rem; min-width: 0; }
.appearance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--ui-space) * 4); min-width: 0; }
.appearance-color-group { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); padding: calc(var(--ui-space) * 3); }
.appearance-color-group summary { cursor: pointer; font-weight: 600; }
.appearance-color-group .appearance-grid { margin-top: calc(var(--ui-space) * 4); }
.appearance-colors > .ui-button { justify-self: start; }
.appearance-error { color: var(--ui-danger); }
@media (max-width: 1100px) { .appearance-workbench { grid-template-columns: minmax(0, 1fr); } .appearance-samples { position: static; } }
@media (max-width: 600px) { .appearance-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
