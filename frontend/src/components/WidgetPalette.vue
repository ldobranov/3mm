<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);

const emit = defineEmits<{ (e: 'add', type: 'CLOCK' | 'TEXT' | 'RSS'): void }>();

function setDragData(ev: DragEvent, type: 'CLOCK' | 'TEXT' | 'RSS') {
  if (!ev.dataTransfer) return;
  ev.dataTransfer.effectAllowed = 'copyMove';
  // minimal data so GridStack recognizes a drag
  ev.dataTransfer.setData('text/plain', type);
}
</script>

<template>
  <div class="widget-palette">
    <div class="palette-item" draggable="true" @dragstart="setDragData($event, 'CLOCK')">
      <button class="palette-button" @click="emit('add','CLOCK')">
        <i class="bi bi-clock"></i>
        <span>Clock</span>
      </button>
    </div>
    <div class="palette-item" draggable="true" @dragstart="setDragData($event, 'TEXT')">
      <button class="palette-button" @click="emit('add','TEXT')">
        <i class="bi bi-textarea-t"></i>
        <span>Text</span>
      </button>
    </div>
    <div class="palette-item" draggable="true" @dragstart="setDragData($event, 'RSS')">
      <button class="palette-button" @click="emit('add','RSS')">
        <i class="bi bi-rss"></i>
        <span>RSS Feed</span>
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