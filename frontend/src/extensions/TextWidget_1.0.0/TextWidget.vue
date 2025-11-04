<script setup lang="ts">
import { computed, withDefaults } from 'vue';

/**
 * Configuration interface for the TextWidget component.
 * Defines optional properties for customizing text display.
 */
interface TextConfig {
  /** The text content to display */
  content?: string;
  /** Text color (CSS color value or CSS custom property) */
  color?: string;
  /** Font size in pixels */
  fontSize?: number;
  /** Text alignment */
  align?: 'left' | 'center' | 'right' | 'justify';
}

/**
 * Props for TextWidget component.
 * config is optional with sensible defaults.
 */
const props = withDefaults(defineProps<{
  config?: TextConfig;
}>(), {
  config: () => ({})
});

/**
 * Computed style object for the text widget.
 * Applies configuration with fallbacks and basic validation.
 */
const widgetStyle = computed(() => {
  const fontSize = Math.max(8, Math.min(72, props.config?.fontSize ?? 16)); // Clamp font size between 8-72px

  return {
    color: props.config?.color || 'var(--text-primary)',
    fontSize: `${fontSize}px`,
    textAlign: props.config?.align || 'left',
    whiteSpace: 'pre-wrap',
    lineHeight: '1.4'
  };
});
</script>

<template>
  <div
    class="text-widget"
    :style="widgetStyle"
    role="text"
    :aria-label="props.config?.content ? undefined : 'Default text widget'"
  >
    {{ props.config?.content || 'TEXT' }}
  </div>
</template>

<style scoped>
.text-widget {
  min-height: 1.4em;
  word-wrap: break-word;
  /* Ensure text is selectable for accessibility */
  user-select: text;
  /* Prevent text selection issues on mobile */
  -webkit-user-select: text;
  -moz-user-select: text;
  -ms-user-select: text;
}
</style>