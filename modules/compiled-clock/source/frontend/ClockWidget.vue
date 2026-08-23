<template>
  <time class="clock" :datetime="isoTime">{{ displayTime }}</time>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

const now = ref(new Date())
const timer = window.setInterval(() => {
  now.value = new Date()
}, 1000)

const displayTime = computed(() => now.value.toLocaleTimeString([], { hour12: false }))
const isoTime = computed(() => now.value.toISOString())

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<style scoped>
.clock {
  display: grid;
  min-height: 100%;
  place-items: center;
  font: 600 clamp(2rem, 8vw, 6rem) / 1 ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
</style>
