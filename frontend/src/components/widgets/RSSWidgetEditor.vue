<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);

const props = defineProps<{ modelValue: any }>();
const emit = defineEmits<{ (e: 'update:modelValue', v: any): void }>();

const cfg = computed({
  get: () => props.modelValue || {},
  set: (v) => emit('update:modelValue', { ...(v || {}) }),
});
</script>

<template>
  <div class="widget-editor">
    <div class="form-group">
      <label class="form-label">Feed URL</label>
      <input
        type="url"
        class="input"
        v-model="cfg.feed_url"
        placeholder="https://example.com/feed.xml"
      />
    </div>
    <div class="form-group">
      <label class="form-label">Items Limit</label>
      <input
        type="number"
        class="input"
        v-model.number="cfg.items_limit"
        placeholder="5"
        min="1"
        max="20"
      />
    </div>
  </div>
</template>

<style scoped>
.widget-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.input {
  padding: 0.5rem;
  border: 1px solid var(--input-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-size: 0.875rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--input-focus-border);
  box-shadow: 0 0 0 2px rgba(var(--button-primary-bg), 0.2);
}

.input::placeholder {
  color: var(--input-placeholder);
}
</style>
