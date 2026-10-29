<script setup lang="ts">
import { computed, useId } from 'vue'
import UiButton from '../components/ui/UiButton.vue'
import UiState from './UiState.vue'

const props = withDefaults(defineProps<{
  title: string; description?: string; dirty?: boolean; busy?: boolean; disabled?: boolean; valid?: boolean
  state?: 'idle' | 'unconfirmed' | 'conflict'; error?: string
  saveLabel?: string; cancelLabel?: string; dirtyLabel?: string; savedLabel?: string
  unconfirmedLabel?: string; conflictLabel?: string
}>(), {
  dirty: false, busy: false, disabled: false, valid: true, state: 'idle',
  saveLabel: 'Save changes', cancelLabel: 'Discard changes', dirtyLabel: 'Unsaved changes', savedLabel: 'No unsaved changes',
  unconfirmedLabel: 'Outcome unconfirmed. Read the original result before another change.',
  conflictLabel: 'The saved record changed. Reload and resolve the draft before saving.',
})
const emit = defineEmits<{ save: []; cancel: [] }>()
const headingId = useId()
const locked = computed(() => props.disabled || props.busy || props.state !== 'idle')
function save(event: Event) {
  if (!locked.value && props.dirty && props.valid && (event.target as HTMLFormElement).checkValidity()) emit('save')
}
</script>

<template>
  <form class="ui-editor ui-stack" :aria-labelledby="headingId" :aria-busy="busy || undefined" @submit.prevent="save">
    <header class="ui-editor-heading ui-stack">
      <h2 :id="headingId">{{ title }}</h2>
      <p v-if="description" class="ui-help">{{ description }}</p>
    </header>
    <UiState v-if="state !== 'idle'" kind="error" :message="state === 'unconfirmed' ? unconfirmedLabel : conflictLabel" />
    <UiState v-if="error" kind="error" :message="error" />
    <fieldset class="ui-form-fields" :disabled="locked">
      <slot :disabled="locked" />
    </fieldset>
    <div v-if="$slots.recovery && state !== 'idle'" class="ui-row"><slot name="recovery" /></div>
    <footer class="ui-editor-actions">
      <p class="ui-help" role="status">{{ dirty ? dirtyLabel : savedLabel }}</p>
      <div class="ui-row">
        <UiButton :disabled="locked || !dirty" @click="!locked && dirty && emit('cancel')">{{ cancelLabel }}</UiButton>
        <UiButton type="submit" variant="primary" :loading="busy" :disabled="locked || !dirty || !valid">{{ saveLabel }}</UiButton>
      </div>
    </footer>
  </form>
</template>
