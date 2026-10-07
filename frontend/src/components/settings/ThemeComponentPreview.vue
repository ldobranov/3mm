<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useUiLabels } from '@/utils/ui-labels'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { uiDesignVariables } from '@/utils/ui-design'
import type { ThemeMode } from '@/utils/theme-extension'

const props = defineProps<{ mode?: ThemeMode }>()
const settings = useSettingsStore()
const modes = useThemeStore()
const paletteMode = computed(() => props.mode ?? modes.theme)
const variables = computed(() => {
  const tokens = uiDesignVariables(settings.uiDesign, paletteMode.value, settings.headerSettings)
  // Inherit the already verified package font, not the system-font fallback.
  delete tokens['--ui-font']
  return tokens
})
const label = useUiLabels()
const formId = useId()
const errorId = useId()
const open = ref(false)
const name = ref('')
const description = ref('')
const enabled = ref(true)
const attempted = ref(false)
const validated = ref(false)
const invalid = computed(() => attempted.value && !name.value.trim())
const validate = () => {
  attempted.value = true
  if (!invalid.value) { validated.value = true; open.value = false }
}
</script>

<template>
  <div class="component-preview ui-v2 ui-stack" :style="variables" :data-mode="paletteMode"
    :data-button="settings.uiDesign.components.button" :data-card="settings.uiDesign.components.card" :aria-label="label('livePreview')">
    <header><h3>{{ label('livePreview') }}</h3><p class="ui-help">{{ label('enabledHelp') }}</p></header>
    <section class="ui-section ui-stack">
      <h4>{{ label('primitives') }}</h4>
      <div class="ui-row"><UiButton variant="primary">{{ label('primary') }}</UiButton><UiButton>{{ label('secondary') }}</UiButton><UiButton variant="danger">{{ label('danger') }}</UiButton></div>
      <div class="ui-row"><UiButton disabled>{{ label('disabled') }}</UiButton><UiButton loading>{{ label('loading') }}</UiButton></div>
      <UiButton @click="open = true">{{ label('dialog') }}</UiButton>
      <p v-if="validated" class="ui-help" role="status">{{ label('validated') }}</p>
    </section>
    <section class="ui-section ui-stack">
      <h4>{{ label('forms') }}</h4>
      <label class="ui-field"><span>{{ label('name') }}</span><input v-model="name" class="ui-control" :placeholder="label('namePlaceholder')" :aria-invalid="invalid" :aria-describedby="invalid ? errorId : undefined" /></label>
      <p v-if="invalid" :id="errorId" class="ui-error" role="alert">{{ label('error') }}</p>
      <label class="ui-field"><span>{{ label('description') }}</span><textarea v-model="description" class="ui-control" :placeholder="label('descriptionPlaceholder')"></textarea></label>
      <label class="ui-check"><input v-model="enabled" type="checkbox" /><span>{{ label('enabled') }}</span></label>
    </section>
    <section class="ui-section ui-stack">
      <h4>{{ label('table') }}</h4>
      <div class="ui-table-wrap"><table class="ui-table"><caption class="visually-hidden">{{ label('table') }}</caption>
        <thead><tr><th scope="col">{{ label('resource') }}</th><th scope="col">{{ label('status') }}</th></tr></thead>
        <tbody><tr><td>{{ label('example') }}</td><td><span class="ui-badge ui-badge--success">✓ {{ label('ready') }}</span></td></tr>
          <tr><td>{{ label('secondary') }}</td><td><span class="ui-badge ui-badge--warning">◷ {{ label('pending') }}</span></td></tr></tbody>
      </table></div>
    </section>
    <UiDialog v-model:open="open" :title="label('dialogTitle')" :close-label="label('close')">
      <form :id="formId" class="ui-stack" @submit.prevent="validate">
        <p class="ui-help">{{ label('enabledHelp') }}</p>
        <label class="ui-field"><span>{{ label('name') }}</span><input v-model="name" autofocus class="ui-control" :aria-invalid="invalid" /></label>
        <p v-if="invalid" class="ui-error" role="alert">{{ label('error') }}</p>
      </form>
      <template #actions><UiButton @click="open = false">{{ label('cancel') }}</UiButton><UiButton variant="primary" type="submit" :form="formId">{{ label('confirm') }}</UiButton></template>
    </UiDialog>
  </div>
</template>

<style scoped>
.component-preview { min-width: 0; background: var(--ui-canvas); padding: calc(var(--ui-space) * 3); border-radius: var(--ui-radius-md); }
.component-preview[data-mode="light"] { color-scheme: light; }
.component-preview[data-mode="dark"] { color-scheme: dark; }
.component-preview h3, .component-preview h4 { margin: 0; font-size: 1rem; font-weight: 650; }
.component-preview header { display: grid; gap: .4rem; }
</style>
