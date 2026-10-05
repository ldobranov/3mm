<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'quiet'
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
  loading?: boolean
}>(), { variant: 'secondary', type: 'button', disabled: false, loading: false })
</script>

<template>
  <button class="ui-button" :class="`ui-button--${variant}`" :type="type"
    :disabled="disabled || loading" :aria-busy="loading || undefined">
    <span v-if="loading" class="ui-spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>
