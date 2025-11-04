<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useSettingsStore } from '@/stores/settings';
import { useWidgetsStore } from '@/stores/widgets';
import type { ExtensionWidget } from '@/stores/widgets';

const settingsStore = useSettingsStore();
const widgetsStore = useWidgetsStore();
const styleSettings = computed(() => settingsStore.styleSettings);

const extensionWidgets = ref<ExtensionWidget[]>([]);

const emit = defineEmits<{ (e: 'add', type: string): void }>();

onMounted(async () => {
  try {
    extensionWidgets.value = await widgetsStore.fetchAvailableExtensions();
  } catch (error) {
    console.error('Failed to load extension widgets:', error);
  }
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
    <!-- Extension widgets only -->
    <div
      v-for="ext in extensionWidgets"
      :key="ext.id"
      class="palette-item"
      draggable="true"
      @dragstart="setDragData($event, `extension:${ext.id}`)"
    >
      <button class="palette-button" @click="emit('add', `extension:${ext.id}`)">
        <i :class="getWidgetIcon(ext.name)"></i>
        <span>{{ ext.name }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.widget-palette {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
}

.palette-item {
  display: flex;
}

.palette-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background-color: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: 1px solid var(--button-primary-border);
  border-radius: var(--border-radius-md);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
}

.palette-button:hover {
  background-color: var(--button-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--card-shadow);
}

.palette-button:active {
  transform: translateY(0);
}

.palette-button i {
  font-size: 1rem;
}

.palette-item[draggable="true"] {
  cursor: grab;
}

.palette-item[draggable="true"]:active {
  cursor: grabbing;
}
</style>