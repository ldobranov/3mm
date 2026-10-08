<script setup lang="ts">
import { ref, onMounted } from 'vue';
import UiButton from '@/components/ui/UiButton.vue';
import { useI18n } from '@/utils/i18n';
import { useWidgetsStore } from '@/stores/widgets';
import type { ExtensionWidget } from '@/stores/widgets';

const widgetsStore = useWidgetsStore();
const { t } = useI18n();
const loading = ref(true);
const loadError = ref('');

const extensionWidgets = ref<ExtensionWidget[]>([]);

const emit = defineEmits<{ (e: 'add', type: string): void }>();

onMounted(async () => {
  try {
    extensionWidgets.value = await widgetsStore.fetchAvailableExtensions();
  } catch (error) {
    console.error('Failed to load extension widgets:', error);
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally { loading.value = false; }
});

function setDragData(ev: DragEvent, type: string) {
  if (!ev.dataTransfer) return;
  ev.dataTransfer.effectAllowed = 'copyMove';
  // minimal data so GridStack recognizes a drag
  ev.dataTransfer.setData('text/plain', type);
}

function getWidgetIcon(name: string): string {
  const iconMap: Record<string, string> = {
    'ClockWidget': 'bi-clock',
    'TextWidget': 'bi-textarea-t',
    'RSSWidget': 'bi-rss',
    'SystemMonitor': 'bi-cpu'
  };
  return iconMap[name] || 'bi-puzzle-piece'; // Default icon for extensions
}
</script>

<template>
  <div class="widget-palette">
    <p v-if="loading" class="ui-help" role="status">{{ t('dashboard.editor.loadingWidgets', 'Loading widgets…') }}</p>
    <p v-else-if="loadError" class="ui-error" role="alert">{{ t('dashboard.editor.widgetsFailed', 'Could not load available widgets.') }} {{ loadError }}</p>
    <p v-else-if="!extensionWidgets.length" class="ui-help" role="status">{{ t('dashboard.editor.noWidgets', 'No widget extensions are available.') }}</p>
    <!-- Extension widgets only -->
    <div
      v-for="ext in extensionWidgets"
      :key="ext.widget_type || ext.id"
      class="palette-item"
      draggable="true"
      @dragstart="setDragData($event, ext.widget_type || `extension:${ext.id}`)"
    >
      <UiButton class="palette-button" @click="emit('add', ext.widget_type || `extension:${ext.id}`)">
        <i :class="['bi', getWidgetIcon(ext.name)]" aria-hidden="true"></i>
        <span>{{ ext.name }}</span>
      </UiButton>
    </div>
  </div>
</template>

<style scoped>
.widget-palette { display: grid; gap: calc(var(--ui-space) * 2); min-width: 0; }
.palette-item { display: flex; min-width: 0; cursor: grab; }
.palette-item:active { cursor: grabbing; }
.palette-button { width: 100%; justify-content: flex-start; text-align: left; }
.palette-button span { min-width: 0; overflow-wrap: anywhere; }
.palette-button i { flex: 0 0 auto; color: var(--ui-text-secondary); }
</style>
