<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue';
import { useSettingsStore } from '@/stores/settings';
import type { Widget } from '@/stores/widgets';
import ClockWidgetEditor from '@/components/widgets/ClockWidgetEditor.vue';
import TextWidgetEditor from '@/components/widgets/TextWidgetEditor.vue';
import RSSWidgetEditor from '@/components/widgets/RSSWidgetEditor.vue';

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
const styleSettings = computed(() => settingsStore.styleSettings);
const localConfig = ref<any>({});
const widgetId = computed(() => props.widget?.id ?? 0);
const widgetType = computed(() => props.widget?.type || 'TEXT');
const editorMap = {
  CLOCK: ClockWidgetEditor,
  TEXT: TextWidgetEditor,
  RSS: RSSWidgetEditor,
} as const;
const CurrentEditor = computed(() => editorMap[widgetType.value as keyof typeof editorMap] || TextWidgetEditor);

watch(() => props.widget, (w) => {
  localConfig.value = w ? JSON.parse(JSON.stringify(w.config || {})) : {};
}, { immediate: true });

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
            <component :is="CurrentEditor" v-model="localConfig" />
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
</style>