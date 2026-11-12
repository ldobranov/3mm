<script setup lang="ts">
import { product } from '@/utils/product'
</script>

<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">About</h1>
    </div>

    <div class="card" style="max-width: 600px; margin: 2rem auto;">
      <div style="padding: 2rem; text-align: center;">
        <h2 style="color: var(--color-text); margin-bottom: 1rem;">{{ product.welcome_message }}</h2>
        <p style="color: var(--color-text); opacity: 0.8; line-height: 1.6;">
          {{ product.description }}
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* About-specific styles if needed */
</style>
