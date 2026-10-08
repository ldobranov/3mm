<template>
  <div class="settings-card ui-section">
    <div class="settings-card-header">
      <h2>{{ title }}</h2>
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
  gap: calc(var(--ui-space, 4px) * 4);
  margin-bottom: calc(var(--ui-space, 4px) * 5);
  padding-bottom: calc(var(--ui-space, 4px) * 4);
  border-bottom: 1px solid var(--ui-border, var(--card-border));
}

.settings-card-header h2 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: var(--ui-text, var(--text-primary));
  overflow-wrap: anywhere;
}

.settings-card {
  box-shadow: none;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
