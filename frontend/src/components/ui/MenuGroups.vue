<script setup lang="ts">
import type { NavigationItem } from '@/utils/menu-navigation'
import { useUiLabels } from '@/utils/ui-labels'
defineProps<{
  groups: { id: number; name?: string; items: NavigationItem[] }[]
  itemLabel: (item: NavigationItem) => string
  horizontal?: boolean
}>()
defineEmits<{ navigate: [] }>()
const label = useUiLabels()
</script>

<template>
  <div class="ui-menu-groups" :class="{ 'ui-menu-groups--horizontal': horizontal }">
    <nav v-for="group in groups" :key="group.id" :data-menu-id="group.id" :aria-label="group.name || label('navigation')"
      :class="horizontal ? 'ui-top-navigation' : 'ui-navigation'">
      <span v-if="groups.length > 1 && group.name" class="ui-menu-group-name">{{ group.name }}</span>
      <RouterLink v-for="(item, index) in group.items" :key="`${item.path}-${index}`" :to="item.path" class="ui-nav-item" @click="$emit('navigate')">
        {{ itemLabel(item) }}
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.ui-menu-groups { display: grid; gap: 16px; min-width: 0; }
.ui-navigation { display: grid; gap: 4px; min-width: 0; }
.ui-menu-groups--horizontal, .ui-top-navigation { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; min-width: 0; }
.ui-menu-groups--horizontal { gap: 16px; }
.ui-menu-group-name { color: var(--ui-text-muted); padding: 8px 12px; font-size: .85em; font-weight: 600; overflow-wrap: anywhere; }
.ui-nav-item { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 9px 12px; margin: 0; color: var(--ui-text-secondary); border-radius: var(--ui-radius-sm); text-decoration: none; overflow-wrap: anywhere; line-height: 1.35; }
.ui-nav-item:hover { background: var(--ui-surface-alt); text-decoration: none; }
.ui-nav-item.router-link-active { color: var(--ui-accent); background: var(--ui-surface-alt); font-weight: 600; }
</style>
