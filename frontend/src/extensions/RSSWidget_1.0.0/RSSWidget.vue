<script setup lang="ts">
type RSSConfig = { feed_url?: string; items_limit?: number };
const { config } = defineProps<{ config: RSSConfig }>();
</script>

<template>
  <div class="rss-widget">
    <div class="rss-header">
      <i class="bi bi-rss"></i>
      <span>RSS Feed</span>
    </div>
    <div class="rss-content">
      {{ config?.feed_url || 'No feed configured' }}
    </div>
    <div class="rss-placeholder" v-if="!config?.feed_url">
      (placeholder)
    </div>
  </div>
</template>

<style scoped>
.rss-widget {
  color: var(--text-primary);
  font-size: 0.875rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.rss-header {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-weight: 500;
}

.rss-header i {
  color: var(--text-secondary);
}

.rss-content {
  word-break: break-all;
  font-size: 0.75rem;
}

.rss-placeholder {
  opacity: 0.7;
  font-style: italic;
}
</style>