<script setup lang="ts">
import { computed } from 'vue';

type TextConfig = {
  content?: string;
  color?: string;
  fontSize?: number;
  align?: 'left' | 'center' | 'right' | 'justify';
};
const { config } = defineProps<{ config: TextConfig }>();

const widgetStyle = computed(() => ({
  color: config?.color || 'var(--text-primary)',
  fontSize: (config?.fontSize ?? 16) + 'px',
  textAlign: config?.align || 'left',
  whiteSpace: 'pre-wrap',
  lineHeight: '1.4'
}));
</script>

<template>
  <div class="text-widget" :style="widgetStyle">
    {{ config?.content || 'TEXT' }}
  </div>
</template>

<style scoped>
.text-widget {
  min-height: 1.4em;
  word-wrap: break-word;
}
</style>