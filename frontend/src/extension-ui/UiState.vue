<script setup lang="ts">
defineProps<{ kind: 'loading' | 'error' | 'empty'; message: string }>()
</script>

<template>
  <div class="ui-state" :class="`ui-state--${kind}`" :role="kind === 'error' ? 'alert' : 'status'"
    :aria-busy="kind === 'loading' || undefined">
    <span v-if="kind === 'loading'" class="ui-spinner" aria-hidden="true"></span>
    <p>{{ message }}</p>
    <slot />
  </div>
</template>
