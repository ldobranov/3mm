<template>
  <div class="extension-widget" :style="widgetStyle">
    <component
      v-if="extensionComponent"
      :is="extensionComponent"
      :config="config"
      :width="width"
      :height="height"
    />
    <div v-else-if="loadState === 'loading'" class="loading-extension">
      <i class="bi bi-puzzle-piece"></i>
      <span>Loading {{ extensionName }}...</span>
    </div>
    <div v-else class="loading-extension extension-error" role="alert">
      <i class="bi bi-exclamation-triangle"></i>
      <strong>Widget unavailable</strong>
      <span>{{ loadError }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch, markRaw } from 'vue';
import http from '@/utils/dynamic-http';
import { loadBundledExtensionComponentByPath } from '@/utils/extension-components';
import { loadCompiledComponentForType } from '@/utils/compiled-ui';

interface Props {
  config: Record<string, any>;
  width: number;
  height: number;
  extensionId: number;
  extensionName: string;
}

interface ExtensionData {
  id: number;
  name: string;
  version: string;
  frontend_entry: string;
  frontend_editor?: string;
}

const props = defineProps<Props>();

const extensionComponent = ref<any>(null);
const extensionData = ref<ExtensionData | null>(null);
const loadState = ref<'loading' | 'ready' | 'error'>('loading');
const loadError = ref('');
const widgetStyle = computed(() => ({
  // Remove fixed width/height - let CSS handle sizing
}));

const authHeaders = () => {
  const token = localStorage.getItem('authToken') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const getAuthHeaders = () => {
  const token = localStorage.getItem('authToken');
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
};

const fetchExtensionData = async (extensionId: number): Promise<ExtensionData | null> => {
  try {
    const res = await http.get('/api/extensions/widgets', { headers: authHeaders() });
    const extensions = res.data.items || [];
    return extensions.find((ext: ExtensionData) => ext.id === extensionId) || null;
  } catch (error) {
    console.error('Failed to fetch extension data:', error);
    return null;
  }
};

const loadExtensionComponent = async () => {
  loadState.value = 'loading';
  loadError.value = '';
  extensionComponent.value = null;
  try {
    if (props.extensionName.startsWith('compiled:')) {
      const component = await loadCompiledComponentForType(props.extensionName, 'widget');
      if (!component) throw new Error(`Compiled widget is unavailable: ${props.extensionName}`);
      extensionComponent.value = component;
      loadState.value = 'ready';
      return;
    }
    const extensionId = props.extensionId;
    let componentUrl: string;

    if (extensionId === 0) {
      // Built-in widget: load directly from extensions directory
      const builtInMap: Record<string, string> = {
        CLOCK: 'ClockWidget',
        TEXT: 'TextWidget',
        RSS: 'RSSWidget'
      };
      const widgetBase = builtInMap[props.extensionName] || `${props.extensionName}Widget`;
      componentUrl = `../../extensions/${widgetBase}_1.0.0/${widgetBase}.vue`;
      console.log('Loading built-in widget component from:', componentUrl);
    } else {
      // Extension widget: fetch data first
      const extData = await fetchExtensionData(extensionId);
      if (!extData) {
        console.error(`Extension with ID ${extensionId} not found`);
        throw new Error(`Extension with ID ${extensionId} was not found`);
      }

      extensionData.value = extData;

      // Construct the component URL dynamically
      componentUrl = `../../extensions/${extData.name}_${extData.version}/${extData.frontend_entry}`;
      console.log('Loading extension component from:', componentUrl);
    }

    const component = await loadBundledExtensionComponentByPath(componentUrl);
    if (!component) {
      throw new Error(`Component is not bundled: ${componentUrl}`);
    }
    extensionComponent.value = markRaw(component);
    loadState.value = 'ready';
  } catch (error) {
    console.error(`Failed to load extension component ${props.extensionName}:`, error);
    // Fallback to a generic component or error display
    extensionComponent.value = null;
    loadError.value = error instanceof Error ? error.message : String(error);
    loadState.value = 'error';
  }
};

// Helper functions (these would need to be implemented based on your auth/user system)
const getCurrentUserId = () => {
  // Get current user ID from auth store or localStorage
  return localStorage.getItem('userId') || 'unknown';
};

const getExtensionVersion = () => {
  // Use actual version from extension data
  return extensionData.value?.version || '1.0.0';
};

onMounted(() => {
  loadExtensionComponent();
});

watch(() => [props.extensionId, props.extensionName], () => {
  loadExtensionComponent();
});
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
