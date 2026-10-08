<template>
  <SettingsSection :title="t('systemControl.title', 'Device control')">
    <p class="section-intro">
      {{ t('systemControl.description', 'Restart this Raspberry Pi or erase all persistent 3mm data and return it to first-boot setup.') }}
    </p>

    <div class="control-grid">
      <article class="control-card">
        <div class="control-icon" aria-hidden="true"><i class="bi bi-arrow-clockwise"></i></div>
        <div class="control-copy">
          <strong>{{ t('systemControl.restartTitle', 'Restart Raspberry Pi') }}</strong>
          <p>{{ t('systemControl.restartHelp', 'Restarts the device. The application will be unavailable for a short time.') }}</p>
        </div>
        <button
          type="button"
          class="ui-button"
          :disabled="busy !== null"
          @click="restartDevice"
        >
          {{ busy === 'restart' ? t('systemControl.working', 'Starting…') : t('systemControl.restartButton', 'Restart device') }}
        </button>
      </article>

      <article class="control-card danger-card">
        <div class="control-icon danger-icon" aria-hidden="true"><i class="bi bi-exclamation-triangle"></i></div>
        <div class="control-copy">
          <strong>{{ t('systemControl.factoryTitle', 'Factory reset') }}</strong>
          <p>{{ t('systemControl.factoryHelp', 'Permanently deletes users, settings, extensions, dashboards, Agent identity and provisioning data, then starts the setup Wi-Fi.') }}</p>
        </div>
        <button
          type="button"
          class="ui-button ui-button--danger"
          :disabled="busy !== null"
          @click="factoryReset"
        >
          {{ busy === 'factory' ? t('systemControl.working', 'Starting…') : t('systemControl.factoryButton', 'Erase and reset') }}
        </button>
      </article>
    </div>

    <div v-if="message" class="notice" :class="messageKind === 'error' ? 'notice-error' : 'notice-success'" role="status">
      {{ message }}
    </div>
  </SettingsSection>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SettingsSection from '@/components/SettingsSection.vue'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'

const { t } = useI18n()
const busy = ref<'restart' | 'factory' | null>(null)
const message = ref('')
const messageKind = ref<'success' | 'error'>('success')

async function restartDevice() {
  if (!confirm(t('systemControl.restartConfirm', 'Restart the Raspberry Pi now?'))) return
  busy.value = 'restart'
  message.value = ''
  try {
    await http.post('/api/v1/system-control/restart', { confirmation: 'RESTART' })
    messageKind.value = 'success'
    message.value = t('systemControl.restartQueued', 'Restart requested. Reconnect after the device starts again.')
  } catch (error: any) {
    messageKind.value = 'error'
    message.value = error?.response?.data?.detail || t('systemControl.actionFailed', 'The system action could not be started.')
    busy.value = null
  }
}

async function factoryReset() {
  const phrase = 'FACTORY RESET'
  const entered = prompt(
    t('systemControl.factoryConfirm', `This permanently deletes all 3mm data. Type ${phrase} to continue.`),
    '',
  )
  if (entered !== phrase) return
  busy.value = 'factory'
  message.value = ''
  try {
    await http.post('/api/v1/system-control/factory-reset', { confirmation: phrase })
    messageKind.value = 'success'
    message.value = t('systemControl.factoryQueued', 'Factory reset requested. Connect to the open 3mm Setup Wi-Fi to configure the device again.')
  } catch (error: any) {
    messageKind.value = 'error'
    message.value = error?.response?.data?.detail || t('systemControl.actionFailed', 'The system action could not be started.')
    busy.value = null
  }
}
</script>

<style scoped>
.section-intro { margin-bottom: calc(var(--ui-space) * 4); color: var(--ui-text-secondary); }
.control-grid { display: grid; gap: calc(var(--ui-space) * 4); }
.control-card { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-alt); }
.control-icon { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; border-radius: var(--ui-radius-sm); color: var(--ui-accent); background: var(--ui-surface); }
.control-copy { min-width: 0; overflow-wrap: anywhere; }
.control-copy strong { display: block; color: var(--ui-text); }
.control-copy p { margin-top: var(--ui-space); color: var(--ui-text-secondary); font-size: .9em; }
.danger-card { border-color: color-mix(in srgb, var(--ui-danger) 42%, var(--ui-border)); }
.danger-icon { color: var(--ui-danger); }
.notice { margin-top: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; }
.notice-error { color: var(--ui-danger); }
.notice-success { color: var(--ui-success); }
@media (max-width: 720px) {
  .control-card { grid-template-columns: auto minmax(0, 1fr); }
  .control-card .ui-button { grid-column: 1 / -1; width: 100%; }
}
</style>
