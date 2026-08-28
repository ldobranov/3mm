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
          class="button button-secondary"
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
          class="button button-danger"
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
.section-intro {
  margin: 0 0 1rem;
  color: var(--text-secondary);
}

.control-grid {
  display: grid;
  gap: 0.85rem;
}

.control-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.9rem;
  padding: 1rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--panel-bg);
}

.control-icon {
  display: grid;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--border-radius-sm);
  color: var(--button-primary-bg);
  background: color-mix(in srgb, var(--button-primary-bg) 12%, transparent);
}

.control-copy strong {
  display: block;
  color: var(--text-primary);
}

.control-copy p {
  margin: 0.25rem 0 0;
  color: var(--text-secondary);
  font-size: 0.88rem;
}

.danger-card {
  border-color: color-mix(in srgb, var(--button-danger-bg) 42%, var(--card-border));
}

.danger-icon {
  color: var(--button-danger-bg);
  background: color-mix(in srgb, var(--button-danger-bg) 12%, transparent);
}

.notice {
  margin-top: 1rem;
}

@media (max-width: 720px) {
  .control-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .control-card .button {
    grid-column: 1 / -1;
    width: 100%;
  }
}
</style>
