<template>
  <div class="settings-card">
    <div class="settings-card-header">
      <h3>{{ title }}</h3>
    </div>
    <slot />
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'SettingsSection',
  props: {
    title: {
      type: String,
      required: true
    }
  }
})
</script>

<style scoped>
.settings-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid var(--card-border, #e3e3e3);
}

.settings-card-header h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--text-primary, #222222);
}

:root[data-theme="dark"] .settings-card-header,
.dark .settings-card-header {
  border-bottom-color: var(--card-border, #4b5563);
}
</style>
