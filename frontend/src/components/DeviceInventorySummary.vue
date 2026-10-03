<template>
  <dl v-if="rows.length" class="device-inventory-summary">
    <div v-for="row in rows" :key="row.key">
      <dt>{{ translate ? translate(row.key, row.label) : row.label }}</dt>
      <dd>{{ row.value }}</dd>
    </div>
  </dl>
  <p v-else class="device-inventory-empty">
    {{ translate ? translate('unavailable', 'Inventory unavailable') : 'Inventory unavailable' }}
  </p>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { inventoryRows, type DeviceInventory } from '@/utils/device-inventory'

const props = defineProps<{
  inventory: DeviceInventory | null
  translate?: (key: string, fallback: string) => string
}>()
const rows = computed(() => inventoryRows(props.inventory))
</script>

<style scoped>
.device-inventory-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
  gap: 0.85rem 1.25rem;
  margin: 0 0 1rem;
  color: var(--text-primary);
}
.device-inventory-summary > div { min-width: 0; }
.device-inventory-summary dt {
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
}
.device-inventory-summary dd { margin: 0.2rem 0 0; overflow-wrap: anywhere; }
.device-inventory-empty { color: var(--text-secondary); }
</style>
