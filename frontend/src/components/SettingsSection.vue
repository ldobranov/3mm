<template>
  <div class="settings-card">
    <h3>{{ title }}</h3>
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
/* Uses .settings-card class from styles.css */
</style>