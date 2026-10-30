<script setup lang="ts">
import { computed, provide, ref, useId } from 'vue'
import { UiButton, UiCollectionEditor, UiDialog, UiEditorForm, UiField, UiForm, UiRecordPicker, UiState, UiSurface, UiTable } from '@/extension-ui/v1'
import { extensionUiKey } from '@/extension-ui/context'
import { useUiLabels } from '@/utils/ui-labels'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { uiDesignVariables, type UiDesign } from '@/utils/ui-design'
import type { ResolvedHeaderSettings } from '@/utils/header-settings'
import type { ThemeMode } from '@/utils/theme-extension'

const props = defineProps<{ mode?: ThemeMode; controlsOnly?: boolean; design?: UiDesign; header?: ResolvedHeaderSettings }>()
const settings = useSettingsStore()
const design = computed(() => props.design ?? settings.uiDesign)
provide(extensionUiKey, computed(() => design.value.components))
const modes = useThemeStore()
const paletteMode = computed(() => props.mode ?? modes.theme)
const variables = computed(() => {
  const tokens = uiDesignVariables(design.value, paletteMode.value, props.header ?? settings.headerSettings)
  // Inherit the already verified package font, not the system-font fallback.
  delete tokens['--ui-font']
  return tokens
})
const label = useUiLabels()
const formId = useId()
const open = ref(false)
const name = ref('')
const description = ref('')
const enabled = ref(true)
const editorState = ref<'idle' | 'unconfirmed' | 'conflict'>('idle')
const selected = ref<string[]>(['first'])
const panels = ref([{ id: '1', title: '' }, { id: '2', title: '' }])
const sampleValue = () => JSON.stringify({ selected: selected.value, panels: panels.value })
const savedSample = ref(sampleValue())
const sampleDirty = computed(() => sampleValue() !== savedSample.value)
const discardSample = () => {
  const saved = JSON.parse(savedSample.value) as { selected: string[]; panels: { id: string; title: string }[] }
  selected.value = saved.selected; panels.value = saved.panels
}
let panelSequence = 2
const addPanel = () => { if (panels.value.length < 2) panels.value = [...panels.value, { id: String(++panelSequence), title: '' }] }
const pickerOptions = computed(() => [{ id: 'first', label: label('primary') }, { id: 'second', label: label('secondary') }])
const state = ref<'loading' | 'error' | 'empty'>('loading')
const attempted = ref(false)
const validated = ref(false)
const invalid = computed(() => attempted.value && !name.value.trim())
const rows = computed(() => [{ id: 'ready', name: label('example'), ready: true }, { id: 'pending', name: label('secondary'), ready: false }])
const columns = computed(() => [{ key: 'name', label: label('resource') }, { key: 'ready', label: label('status') }])
const validate = () => {
  attempted.value = true
  if (!invalid.value) { validated.value = true; open.value = false }
}
</script>

<template>
  <UiSurface class="component-preview ui-stack" :style="variables" :data-mode="paletteMode" :aria-label="label('livePreview')">
    <div class="preview-heading"><h3>{{ label('livePreview') }}</h3><p class="ui-help">{{ label('enabledHelp') }}</p></div>
    <div class="preview-appearance-bar ui-row"><strong>{{ (header ?? settings.headerSettings).siteName }}</strong><span>{{ label(paletteMode) }}</span></div>
    <section class="ui-section ui-stack">
      <h4>{{ label('primitives') }}</h4>
      <div class="ui-row"><UiButton variant="primary">{{ label('primary') }}</UiButton><UiButton>{{ label('secondary') }}</UiButton><UiButton variant="danger">{{ label('danger') }}</UiButton></div>
      <div class="ui-row"><UiButton disabled>{{ label('disabled') }}</UiButton><UiButton loading>{{ label('loading') }}</UiButton></div>
      <UiButton @click="open = true">{{ label('dialog') }}</UiButton>
      <p v-if="validated" class="ui-help" role="status">{{ label('validated') }}</p>
    </section>
    <section v-if="!controlsOnly" class="ui-section ui-stack">
      <h4>{{ label('forms') }}</h4>
      <UiForm @submit="validate" @invalid.capture="attempted = true">
        <UiField :id="`${formId}-name`" :label="label('name')" v-model="name" required
          :placeholder="label('namePlaceholder')" :error="invalid ? label('error') : undefined" />
        <UiField :id="`${formId}-description`" :label="label('description')" v-model="description" type="textarea" :placeholder="label('descriptionPlaceholder')" />
        <UiField :id="`${formId}-enabled`" :label="label('enabled')" v-model="enabled" type="checkbox" />
        <UiField :id="`${formId}-disabled`" :label="label('disabled')" :model-value="label('example')" disabled />
      </UiForm>
    </section>
    <section v-if="!controlsOnly" class="ui-section ui-stack">
      <h4>{{ label('table') }}</h4>
      <UiTable :rows="rows" :columns="columns" :row-key="row => row.id" :caption="label('table')" :empty-label="label('emptyMessage')">
        <template #cell="{ row, column, value }">
          <span v-if="column.key === 'ready'" class="ui-badge" :class="row.ready ? 'ui-badge--success' : 'ui-badge--warning'">{{ row.ready ? label('ready') : label('pending') }}</span>
          <template v-else>{{ value }}</template>
        </template>
      </UiTable>
    </section>
    <section v-if="!controlsOnly" class="ui-section ui-stack">
      <div class="ui-row">
        <UiButton v-for="kind in ['idle', 'unconfirmed', 'conflict'] as const" :key="kind" :aria-pressed="editorState === kind" @click="editorState = kind">
          {{ label(kind === 'idle' ? 'ready' : kind === 'unconfirmed' ? 'previewUnconfirmed' : 'previewConflict') }}
        </UiButton>
      </div>
      <UiEditorForm :title="label('editingControls')" :description="label('enabledHelp')" :dirty="sampleDirty" :state="editorState"
        :save-label="label('confirm')" :cancel-label="label('cancel')" :dirty-label="label('localSampleDraft')" :saved-label="label('validated')"
        :unconfirmed-label="label('appearanceUnconfirmed')" :conflict-label="label('appearanceConflict')"
        @save="savedSample = sampleValue()" @cancel="discardSample">
        <template #default="{ disabled }">
          <UiRecordPicker :id="`${formId}-records`" :label="label('resource')" v-model="selected" multiple :options="pickerOptions" :disabled="disabled"
            :placeholder="label('namePlaceholder')" :empty-label="label('emptyMessage')" :selected-label="label('resource')"
            :remove-label="label('remove')" :toggle-label="label('chooseRecords')" :loading-label="label('loading')" :unavailable-label="label('disabled')" />
          <UiCollectionEditor :title="label('orderedPanels')" v-model="panels" :item-key="item => item.id" :item-label="item => `${label('panel')} ${item.id}`" @add="addPanel"
            :disabled="disabled" :min-items="1" :max-items="2" :add-label="label('addPanel')" :remove-label="label('remove')"
            :move-up-label="label('moveUp')" :move-down-label="label('moveDown')" :empty-label="label('emptyMessage')" :invalid-keys-label="label('errorState')">
            <template #default="{ item, disabled: locked }">
              <UiField :id="`${formId}-${item.id}`" :label="label('name')" v-model="item.title" :disabled="locked" :placeholder="label('namePlaceholder')" />
            </template>
          </UiCollectionEditor>
        </template>
        <template #recovery><UiButton @click="editorState = 'idle'">{{ label('resolveExample') }}</UiButton></template>
      </UiEditorForm>
    </section>
    <section v-if="!controlsOnly" class="ui-section ui-stack">
      <div class="ui-row"><UiButton v-for="kind in ['loading', 'error', 'empty'] as const" :key="kind" :aria-pressed="state === kind" @click="state = kind">{{ label(kind === 'error' ? 'errorState' : kind) }}</UiButton></div>
      <UiState :kind="state" :message="label(state === 'empty' ? 'emptyMessage' : state)" />
    </section>
    <UiDialog v-model:open="open" :title="label('dialogTitle')" :close-label="label('close')">
      <UiForm :id="formId" @submit="validate" @invalid.capture="attempted = true">
        <p class="ui-help">{{ label('enabledHelp') }}</p>
        <UiField :id="`${formId}-dialog-name`" :label="label('name')" v-model="name" required autofocus :error="invalid ? label('error') : undefined" />
      </UiForm>
      <template #actions><UiButton @click="open = false">{{ label('cancel') }}</UiButton><UiButton variant="primary" type="submit" :form="formId">{{ label('confirm') }}</UiButton></template>
    </UiDialog>
  </UiSurface>
</template>

<style scoped>
.component-preview { min-width: 0; background: var(--ui-canvas); padding: calc(var(--ui-space) * 3); border-radius: var(--ui-radius-md); }
.component-preview h3, .component-preview h4 { margin: 0; font-size: 1em; font-weight: 650; }
.preview-heading { display: grid; gap: calc(var(--ui-space) * 2); }
.preview-appearance-bar { justify-content: space-between; padding: calc(var(--ui-space) * 3); border-radius: var(--ui-radius-sm); background: var(--ui-header-bg); color: var(--ui-header-text); }
</style>
