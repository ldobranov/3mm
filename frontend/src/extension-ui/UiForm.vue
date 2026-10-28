<script setup lang="ts">
const props = withDefaults(defineProps<{ busy?: boolean }>(), { busy: false })
const emit = defineEmits<{ submit: [] }>()
function submit(event: Event) {
  if (!props.busy && (event.target as HTMLFormElement).checkValidity()) emit('submit')
}
</script>

<template>
  <form class="ui-form" :aria-busy="busy || undefined" @submit.prevent="submit">
    <fieldset class="ui-form-fields" :disabled="busy"><slot /></fieldset>
  </form>
</template>
