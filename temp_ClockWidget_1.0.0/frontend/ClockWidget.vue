<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue';
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

type ClockConfig = { timezone?: string; format?: string };
const props = defineProps<{ config: ClockConfig }>();

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
  <div class="clock-widget">
    {{ now || '...' }}
  </div>
</template>

<style scoped>
.clock-widget {
  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 600;
  text-align: center;
  font-family: 'Courier New', monospace;
}
</style>