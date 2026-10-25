<template>
  <div class="extension-widget">
    <component
      v-if="extensionComponent"
      :is="extensionComponent"
      :config="config"
      :width="width"
      :height="height"
    />
    <div v-else-if="loadState === 'loading'" class="loading-extension">
      <i class="bi bi-puzzle-piece"></i>
      <span>{{ t('dashboard.editor.loadingWidgets', 'Loading widgets…') }}</span>
    </div>
    <div v-else class="loading-extension extension-error" role="alert">
      <i class="bi bi-exclamation-triangle"></i>
      <strong>{{ t('dashboard.editor.widgetUnavailable', 'Widget unavailable') }}</strong>
      <span>{{ loadError }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { loadCompiledComponentForType } from '@/utils/compiled-ui';
import { useI18n } from '@/utils/i18n';
const { t } = useI18n();
const props = defineProps<{ config: Record<string, any>; width: number; height: number; extensionName: string }>();
const extensionComponent = ref<any>(null);
const loadState = ref<'loading' | 'ready' | 'error'>('loading');
const loadError = ref('');
watch(() => props.extensionName, async (type, _previous, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  extensionComponent.value = null;
  loadState.value = 'loading';
  loadError.value = '';
  try {
    const component = await loadCompiledComponentForType(type, 'widget');
    if (!current) return;
    if (!component) throw new Error(t('dashboard.editor.widgetUnavailable', 'This widget package is unavailable.'));
    extensionComponent.value = component;
    loadState.value = 'ready';
  } catch {
    if (!current) return;
    loadError.value = t('dashboard.editor.widgetUnavailable', 'This widget package is unavailable.');
    loadState.value = 'error';
  }
}, { immediate: true });
</script>

<style scoped>
.extension-widget {
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  overflow: hidden;
  background-color: var(--card-bg);
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}

.loading-extension {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.loading-extension i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  opacity: 0.6;
}

.extension-error {
  gap: 0.35rem;
  padding: 1rem;
  text-align: center;
  color: var(--danger-color, #dc3545);
}

.extension-error span {
  overflow-wrap: anywhere;
}
</style>
