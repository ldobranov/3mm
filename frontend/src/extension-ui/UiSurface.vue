<script setup lang="ts">
import { useExtensionUiAppearance } from './context'

const appearance = useExtensionUiAppearance()
</script>

<template>
  <div class="ui-v2" :data-button="appearance.button" :data-card="appearance.card">
    <slot />
  </div>
</template>
