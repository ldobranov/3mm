<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue';
import { useSettingsStore } from '@/stores/settings';
import type { Widget } from '@/stores/widgets';
import { useWidgetsStore } from '@/stores/widgets';
import { markRaw } from 'vue';
import { loadBundledExtensionComponentByPath } from '@/utils/extension-components';
import { findCompiledEntrypoint, getCompiledUiCatalog, loadCompiledComponent } from '@/utils/compiled-ui';
import { useI18n } from '@/utils/i18n';

const props = defineProps<{
  modelValue: boolean;
  widget: Widget | null;
}>();
const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void;
  (e: 'save', data: { id: number; config: any }): void;
  (e: 'preview', data: { id: number; config: any }): void;
  (e: 'cancel', id: number): void;
}>();

const settingsStore = useSettingsStore();
const widgetsStore = useWidgetsStore();
const { t } = useI18n();
const styleSettings = computed(() => settingsStore.styleSettings);
const localConfig = ref<any>({});
const widgetId = computed(() => props.widget?.id ?? 0);
const widgetType = computed(() => props.widget?.type || 'TEXT');
const extensionEditor = ref<any>(null);
const editorState = ref<'idle' | 'loading' | 'ready' | 'missing' | 'error'>('idle');
const editorError = ref('');


const CurrentEditor = computed(() => {
  return extensionEditor.value || null; // All editors loaded dynamically
});

// Load editor when widget changes
watch(() => props.widget, async (widget) => {
  if (!widget) {
    extensionEditor.value = null;
    editorState.value = 'idle';
    return;
  }

  extensionEditor.value = null; // Reset while loading
  editorState.value = 'loading';
  editorError.value = '';

  try {
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
      extensionEditor.value = resolved && editor
        ? await loadCompiledComponent(resolved.pkg, editor)
        : null;
    } else if (widget.type.startsWith('extension:')) {
      const extensionId = widget.type.split(':')[1];
      const extensions = await widgetsStore.fetchAvailableExtensions();
      const extension = extensions.find(ext => ext.id === parseInt(extensionId));

      if (extension && extension.frontend_editor) {
        // Load the extension editor component dynamically
        const editorUrl = `/src/extensions/${extension.name}_${extension.version}/${extension.frontend_editor}`;
        const component = await loadBundledExtensionComponentByPath(editorUrl);
        extensionEditor.value = component ? markRaw(component) : null;
      }
    } else {
      // Built-in widgets: load from extensions directory
      const builtInMap: Record<string, string> = {
        CLOCK: 'ClockWidget_1.0.0',
        TEXT: 'TextWidget_1.0.0',
        RSS: 'RSSWidget_1.0.0'
      };
      const extensionName = builtInMap[widget.type] || `${widget.type}Widget_1.0.0`;
      const editorUrl = `/src/extensions/${extensionName}/${widget.type.charAt(0) + widget.type.slice(1).toLowerCase()}WidgetEditor.vue`;
      const component = await loadBundledExtensionComponentByPath(editorUrl);
      extensionEditor.value = component ? markRaw(component) : null;
    }
    editorState.value = extensionEditor.value ? 'ready' : 'missing';
  } catch (error) {
    console.error('Failed to load editor:', error);
    extensionEditor.value = null;
    editorError.value = error instanceof Error ? error.message : String(error);
    editorState.value = 'error';
  }
}, { immediate: true });

watch(() => props.widget, (w) => {
  const newConfig = w ? JSON.parse(JSON.stringify(w.config || {})) : {};
  // Only update if config actually changed
  if (JSON.stringify(localConfig.value) !== JSON.stringify(newConfig)) {
    localConfig.value = newConfig;
  }
}, { immediate: true });

// Update local config when extension editor loads
watch(() => extensionEditor.value, (newEditor) => {
  if (newEditor && props.widget && props.widget.config) {
    // Re-trigger config loading when editor is ready
    const configToLoad = props.widget.config;
    // Only update if config actually changed
    if (JSON.stringify(localConfig.value) !== JSON.stringify(configToLoad)) {
      localConfig.value = JSON.parse(JSON.stringify(configToLoad));
    }
  }
});

// Debounce preview emits
let previewTimer: number | null = null;
watch(localConfig, (val) => {
  if (!widgetId.value) return;
  if (previewTimer) window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(() => {
    emit('preview', { id: widgetId.value, config: val });
  }, 150);
}, { deep: true });

function save() {
  if (!widgetId.value) return;
  emit('save', { id: widgetId.value, config: localConfig.value });
  emit('update:modelValue', false);
}

function cancel() {
  if (!widgetId.value) return;
  emit('cancel', widgetId.value);
  emit('update:modelValue', false);
}

function handleBackdropClick(event: MouseEvent) {
  // Only close if clicking directly on the backdrop (container)
  if (event.target === event.currentTarget) {
    cancel();
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) {
    e.stopPropagation();
    cancel();
  } else if (e.key === 'Enter' && props.modelValue && !e.shiftKey) {
    // Don't submit if focus is on textarea
    const target = e.target as HTMLElement;
    if (target.tagName !== 'TEXTAREA') {
      e.preventDefault();
      save();
    }
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <teleport to="body">
    <div v-if="modelValue">
      <!-- backdrop -->
      <div 
        class="modal-backdrop"
        @click="cancel"
      ></div>
      
      <!-- dialog centered -->
      <div class="modal-container">
        <div
          class="modal-dialog"
          role="dialog"
          aria-modal="true"
          @click.stop
          :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }"
        >
          <div class="modal-header">
            <div class="modal-title">Edit {{ widgetType }}</div>
            <button
              class="modal-close"
              type="button"
              @click.stop="cancel"
            >
              ×
            </button>
          </div>

          <div class="modal-content">
            <div v-if="CurrentEditor" class="editor-content">
              <component :is="CurrentEditor" :config="localConfig" @update:modelValue="localConfig = $event" />
            </div>
            <div v-else-if="editorState === 'loading'" class="editor-status">
              <div class="loading-spinner"></div>
              <span>{{ t('dashboard.editor.loadingWidgetEditor', 'Loading editor...') }}</span>
            </div>
            <div v-else-if="editorState === 'error'" class="editor-status editor-status-error">
              <i class="bi bi-exclamation-triangle"></i>
              <strong>{{ t('dashboard.editor.widgetEditorFailed', 'The widget editor could not be loaded.') }}</strong>
              <span>{{ editorError }}</span>
            </div>
            <div v-else class="editor-status">
              <i class="bi bi-sliders"></i>
              <strong>{{ t('dashboard.editor.noWidgetSettings', 'This widget does not provide editable settings.') }}</strong>
              <span>{{ t('dashboard.editor.noWidgetSettingsHint', 'You can still move, resize, or remove it from the dashboard.') }}</span>
            </div>
          </div>

          <div class="modal-actions">
            <button
              class="button button-secondary"
              type="button"
              @click.stop="cancel"
            >
              Cancel
            </button>
            <button
              class="button button-primary"
              type="button"
              @click.stop="save"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.6);
  z-index: 9998;
}

.modal-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  pointer-events: none;
}

.modal-dialog {
  position: relative;
  border-radius: var(--border-radius-md);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  padding: 1.25rem;
  width: min(90vw, 48rem);
  max-height: 85vh;
  overflow: auto;
  pointer-events: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--card-border);
  margin-bottom: 1rem;
}

.modal-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.25rem;
  line-height: 1;
  transition: color 0.2s ease;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-content {
  padding: 1rem 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border);
}

.editor-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  gap: 1rem;
  color: var(--text-secondary);
}

.editor-status i {
  font-size: 1.5rem;
}

.editor-status-error {
  color: var(--danger-color, #dc3545);
  text-align: center;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-top: 2px solid var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
