<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { UiButton, UiField, UiForm } from '@/extension-ui/v1'
import { useI18n } from '@/utils/i18n'
import type { HardwareProviderTemplate } from '@/utils/hardware-profiles'

const props = defineProps<{ templates: HardwareProviderTemplate[]; busy: boolean; disabled: boolean }>()
const emit = defineEmits<{ prepare: [templateId: string, configuration: Record<string, string | number | boolean>] }>()
const { t } = useI18n(), prefix = useId()
const label = (key: string, fallback: string) => t('hardwareProfiles.' + key, fallback)
const selected = ref(''), draft = ref<Record<string, string | boolean>>({}), invalid = ref(false)
const template = computed(() => props.templates.find(item => item.template_id === selected.value))
watch(() => props.templates, items => {
  if (!items.some(item => item.template_id === selected.value)) selected.value = items[0]?.template_id || ''
}, { immediate: true })
watch(() => template.value?.template_id, () => {
  const item = template.value
  draft.value = Object.fromEntries((item?.fields || []).map(f => [f.key,
    typeof f.default === 'boolean' ? f.default : String(f.default)]))
  invalid.value = false
}, { immediate: true })
function prepare() {
  if (!template.value || props.busy || props.disabled) return
  const configuration: Record<string, string | number | boolean> = {}
  invalid.value = false
  for (const field of template.value.fields) {
    const value = draft.value[field.key]
    if (field.type === 'checkbox') configuration[field.key] = value === true
    else if (typeof value !== 'string' || !value.length
        || (field.pattern && !new RegExp(field.pattern).test(value))
        || (field.options && !field.options.some(option => option.value === value))) invalid.value = true
    else if (typeof field.default === 'number') {
      const n = Number(value)
      if (!Number.isInteger(n) || (field.min !== undefined && n < field.min)
          || (field.max !== undefined && n > field.max)) invalid.value = true
      else configuration[field.key] = n
    } else configuration[field.key] = value
  }
  if (!invalid.value) emit('prepare', template.value.template_id, configuration)
}
</script>

<template>
  <section v-if="templates.length" class="provider-setup">
    <h4>{{ label('setupTitle', 'Configure a supported provider') }}</h4>
    <p>{{ label('setupHelp', 'Choose the driver and actual hardware settings. Preparation only adds an immutable package to the catalog; review and installation are separate.') }}</p>
    <UiForm :busy="busy" @submit="prepare">
      <UiField :id="prefix + '-template'" v-model="selected" type="select"
        :label="label('template', 'Provider driver')" :disabled="disabled"
        :options="templates.map(item => ({ value: item.template_id, label: item.name }))" />
      <template v-if="template">
        <p role="status">{{ template.simulated ? label('mock', 'Simulated provider') : label('physical', 'Physical hardware profile') }}</p>
        <div class="profile-fields">
          <UiField v-for="field in template.fields" :id="prefix + '-' + field.key" :key="template.template_id + field.key"
            v-model="draft[field.key]" :label="label('field_' + field.key, field.label)" :type="field.type"
            :min="field.min" :max="field.max" :maxlength="field.maxlength" :step="1" :options="field.options"
            :required="field.type !== 'checkbox'" :disabled="disabled" />
        </div>
        <p v-if="template.help">{{ template.help }}</p>
        <p v-if="invalid" role="alert">{{ label('invalidConfiguration', 'Check the profile settings before preparation.') }}</p>
        <UiButton type="submit" class="prepare-provider" :disabled="disabled || busy">{{ label('prepare', 'Prepare provider') }}</UiButton>
      </template>
    </UiForm>
  </section>
</template>

<style scoped>
.provider-setup { margin-block: 1rem; padding: 1rem; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
h4 { margin-block: 0 .5rem; }
.profile-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
[role="alert"] { color: var(--ui-danger); }
@media (max-width: 600px) { .profile-fields { grid-template-columns: minmax(0, 1fr); } }
</style>
