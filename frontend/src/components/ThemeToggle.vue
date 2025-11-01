<template>
  <button 
    @click="toggleTheme" 
    class="theme-toggle"
    :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
    aria-label="Toggle theme"
  >
    <i :class="isDark ? 'bi bi-sun-fill' : 'bi bi-moon-fill'"></i>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

const isDark = computed(() => themeStore.isDark())

const toggleTheme = () => {
  themeStore.toggleTheme()
}
</script>

<style scoped>
.theme-toggle {
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  color: var(--color-text);
  font-size: 18px;
}

.theme-toggle:hover {
  background: var(--color-background-soft);
  border-color: var(--color-border-hover);
  transform: scale(1.05);
}

.theme-toggle:active {
  transform: scale(0.95);
}

.theme-toggle i {
  transition: transform 0.3s ease;
}

.theme-toggle:hover i {
  transform: rotate(20deg);
}

/* Dark mode specific styles */
.dark-mode .theme-toggle {
  border-color: var(--color-border);
}

.dark-mode .theme-toggle:hover {
  background: var(--color-background-soft);
  border-color: var(--color-border-hover);
}
</style>
