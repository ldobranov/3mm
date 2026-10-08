<script setup lang="ts">
import { ref, watch, computed, onBeforeUnmount, markRaw, nextTick } from 'vue';
import type { Widget } from '@/stores/widgets';
import { useWidgetsStore } from '@/stores/widgets';
import { loadBundledExtensionComponentByPath } from '@/utils/extension-components';
import { findCompiledEntrypoint, getCompiledUiCatalog, loadCompiledComponent } from '@/utils/compiled-ui';
import { useI18n } from '@/utils/i18n';
import UiButton from '@/components/ui/UiButton.vue';

const props = withDefaults(defineProps<{
  modelValue: boolean;
  widget: Widget | null;
  saving?: boolean;
  error?: string;
}>(), { saving: false, error: '' });
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
  (e: 'save', data: { id: number; config: any }): void;
  (e: 'preview', data: { id: number; config: any }): void;
  (e: 'cancel', id: number): void;
}>();

const widgetsStore = useWidgetsStore();
const { t } = useI18n();
const panel = ref<HTMLElement>();
const localConfig = ref<any>({});
const widgetId = computed(() => props.widget?.id ?? 0);
const extensionEditor = ref<any>(null);
const editorState = ref<'idle' | 'loading' | 'ready' | 'missing' | 'error'>('idle');
const editorError = ref('');
let previewTimer: ReturnType<typeof setTimeout> | undefined;

function clearPreview() {
  clearTimeout(previewTimer);
  previewTimer = undefined;
}

// Each selection owns its async editor request and preview timer.
watch(() => [props.widget, props.modelValue] as const, async ([widget, open], _previous, onCleanup) => {
  clearPreview();
  let current = true;
  onCleanup(() => { current = false; clearPreview(); });
  extensionEditor.value = null;
  editorError.value = '';
  if (!widget || !open) { editorState.value = 'idle'; return; }
  localConfig.value = JSON.parse(JSON.stringify(widget.config || {}));
  editorState.value = 'loading';
  await nextTick();
  if (!current) return;
  panel.value?.focus();
  try {
    let component: any = null;
    if (widget.type.startsWith('compiled:')) {
      let resolved = await findCompiledEntrypoint(widget.type);
      if (!resolved) {
        await getCompiledUiCatalog(true);
        resolved = await findCompiledEntrypoint(widget.type);
      }
      const editor = resolved?.pkg.entrypoints.find(entrypoint =>
        entrypoint.kind === 'editor' &&
        entrypoint.target_entrypoint_id === resolved.entrypoint.entrypoint_id
      );
      component = resolved && editor ? await loadCompiledComponent(resolved.pkg, editor) : null;
    } else if (widget.type.startsWith('extension:')) {
      const extensionId = widget.type.split(':')[1];
      const extensions = await widgetsStore.fetchAvailableExtensions();
      const extension = extensions.find(ext => ext.id === parseInt(extensionId));
      if (extension && extension.frontend_editor) {
        const editorUrl = `/src/extensions/${extension.name}_${extension.version}/${extension.frontend_editor}`;
        component = await loadBundledExtensionComponentByPath(editorUrl);
      }
    } else {
      // Existing legacy built-in resolver; extension registrations stay dynamic.
      const builtInMap: Record<string, string> = {
        CLOCK: 'ClockWidget_1.0.0', TEXT: 'TextWidget_1.0.0', RSS: 'RSSWidget_1.0.0'
      };
      const extensionName = builtInMap[widget.type] || `${widget.type}Widget_1.0.0`;
      const editorUrl = `/src/extensions/${extensionName}/${widget.type.charAt(0) + widget.type.slice(1).toLowerCase()}WidgetEditor.vue`;
      component = await loadBundledExtensionComponentByPath(editorUrl);
    }
    if (!current) return;
    extensionEditor.value = component ? markRaw(component) : null;
    editorState.value = component ? 'ready' : 'missing';
    await nextTick();
    if (current && document.activeElement === panel.value) {
      panel.value?.querySelector<HTMLElement>('input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')?.focus();
    }
  } catch (error) {
    if (!current) return;
    console.error('Failed to load editor:', error);
    editorError.value = error instanceof Error ? error.message : String(error);
    editorState.value = 'error';
  }
}, { immediate: true, flush: 'sync' });

watch(localConfig, val => {
  clearPreview();
  if (!props.modelValue || !widgetId.value || props.saving) return;
  const id = widgetId.value;
  const config = JSON.parse(JSON.stringify(val));
  previewTimer = setTimeout(() => {
    previewTimer = undefined;
    if (props.modelValue && widgetId.value === id && !props.saving) emit('preview', { id, config });
  }, 150);
}, { deep: true, flush: 'sync' });

watch(() => props.saving, saving => { if (saving) clearPreview(); });

function save() {
  if (!widgetId.value || props.saving || editorState.value !== 'ready') return;
  clearPreview();
  emit('save', { id: widgetId.value, config: JSON.parse(JSON.stringify(localConfig.value)) });
  // The parent closes only after persistence succeeds; errors retain the draft.
}

function cancel() {
  if (!widgetId.value || props.saving) return;
  clearPreview();
  emit('cancel', widgetId.value);
  emit('update:modelValue', false);
}

function onKeydown(event: KeyboardEvent) {
  if (!props.modelValue || props.saving) return;
  if (event.key === 'Escape') {
    event.stopPropagation();
    cancel();
  } else if (event.key === 'Enter' && !event.shiftKey &&
    event.target instanceof HTMLInputElement && !['checkbox', 'radio', 'button', 'submit'].includes(event.target.type)) {
    event.preventDefault();
    save();
  }
}

onBeforeUnmount(clearPreview);
</script>

<template>
  <div ref="panel" class="widget-properties" role="group" :aria-label="t('dashboard.editor.widgetProperties', 'Widget properties')" tabindex="-1" @keydown="onKeydown">
    <template v-if="modelValue && widget">
      <div class="properties-heading">
        <span class="widget-identity">{{ widget.type }} · #{{ widget.id }}</span>
        <UiButton variant="quiet" :disabled="saving" :aria-label="t('dashboard.editor.closeProperties', 'Close properties')" @click="cancel">×</UiButton>
      </div>
      <fieldset class="editor-fields" :disabled="saving">
        <component v-if="extensionEditor" :is="extensionEditor" :config="localConfig" @update:modelValue="localConfig = $event" />
        <div v-else-if="editorState === 'loading'" class="editor-status" role="status">
          <span class="ui-spinner" aria-hidden="true"></span>{{ t('dashboard.editor.loadingWidgetEditor', 'Loading editor…') }}
        </div>
        <div v-else-if="editorState === 'error'" class="editor-status ui-error" role="alert">
          <strong>{{ t('dashboard.editor.widgetEditorFailed', 'The widget editor could not be loaded.') }}</strong>
          <span>{{ editorError }}</span>
        </div>
        <div v-else class="editor-status">
          <strong>{{ t('dashboard.editor.noWidgetSettings', 'This widget does not provide editable settings.') }}</strong>
          <span>{{ t('dashboard.editor.noWidgetSettingsHint', 'You can still move, resize, or remove it from the dashboard.') }}</span>
        </div>
      </fieldset>
      <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
      <div class="properties-actions">
        <UiButton :disabled="saving" @click="cancel">{{ t('dashboard.editor.cancelButton', 'Cancel') }}</UiButton>
        <UiButton variant="primary" :loading="saving" :disabled="editorState !== 'ready'" @click="save">{{ t('dashboard.editor.saveButton', 'Save') }}</UiButton>
      </div>
    </template>
    <p v-else class="properties-empty ui-help">{{ t('dashboard.editor.chooseWidgetHint', 'Choose a widget on the canvas or from the list to edit its properties.') }}</p>
  </div>
</template>

<style scoped>
.widget-properties { min-width: 0; }
.properties-heading { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--ui-space) * 2); margin-bottom: calc(var(--ui-space) * 3); }
.widget-identity { color: var(--ui-text-muted); font-size: .85em; overflow-wrap: anywhere; }
.editor-fields { border: 0; padding: 0; margin: 0; min-width: 0; }
.editor-status { display: grid; gap: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 4) 0; color: var(--ui-text-secondary); font-size: .9em; overflow-wrap: anywhere; }
.editor-status.ui-error { color: var(--ui-danger); }
.properties-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: calc(var(--ui-space) * 2); margin-top: calc(var(--ui-space) * 4); padding-top: calc(var(--ui-space) * 3); border-top: 1px solid var(--ui-border); }
.properties-empty { padding-block: calc(var(--ui-space) * 4); }
</style>
