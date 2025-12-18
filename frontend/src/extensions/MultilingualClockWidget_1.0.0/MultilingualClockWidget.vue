<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import { useI18n } from '@/utils/i18n';

dayjs.extend(utc);
dayjs.extend(timezone);

type ClockConfig = {
  timezone?: string;
  format?: string;
  showCustomMessage?: boolean;
  customMessage?: string;
};

const props = defineProps<{ config: ClockConfig }>();
const { t } = useI18n();

const now = ref<string>('');
let timer: number | null = null;

function formatTime() {
  const tz = props.config?.timezone || 'UTC';
  const fmt = props.config?.format || 'HH:mm:ss';
  now.value = dayjs().tz(tz).format(fmt);
}

onMounted(() => {
  formatTime();
  timer = window.setInterval(formatTime, 1000);
});

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});

watch(() => props.config, formatTime, { deep: true });
</script>

<template>
  <div class="multilingual-clock-widget">
    <div class="time-display">
      <div class="time-label">{{ t('extensions.multilingualclockwidget.messages.currentTime') }}</div>
      <div class="time-value">{{ now || '...' }}</div>
    </div>

    <div v-if="config?.showCustomMessage && config?.customMessage" class="custom-message">
      <div class="message-label">{{ t('extensions.multilingualclockwidget.messages.customMessage') }}</div>
      <div class="message-value">{{ config.customMessage }}</div>
    </div>
  </div>
</template>

<style scoped>
.multilingual-clock-widget {
  color: var(--text-primary);
  font-family: 'Courier New', monospace;
  text-align: center;
  padding: 1rem;
}

.time-display {
  margin-bottom: 1rem;
}

.time-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

.time-value {
  font-size: 2rem;
  font-weight: 600;
  color: var(--text-primary);
}

.custom-message {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.message-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 0.25rem;
}

.message-value {
  font-size: 1rem;
  color: var(--text-primary);
  font-style: italic;
}
</style>