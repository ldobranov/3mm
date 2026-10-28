<script setup lang="ts" generic="Row extends object">
import UiButton from '../components/ui/UiButton.vue'
import UiState from './UiState.vue'
withDefaults(defineProps<{
  rows: ReadonlyArray<Row>; columns: ReadonlyArray<{ key: string; label: string }>
  rowKey: (row: Row) => string | number; caption: string; emptyLabel: string
  busy?: boolean; hasPrevious?: boolean; hasNext?: boolean
  previousLabel?: string; nextLabel?: string; paginationLabel?: string
}>(), { busy: false, hasPrevious: false, hasNext: false,
  previousLabel: 'Previous page', nextLabel: 'Next page', paginationLabel: 'Page navigation' })
const emit = defineEmits<{ previous: []; next: [] }>()
const valueAt = (row: Row, key: string): unknown => Reflect.get(row, key)
const text = (value: unknown): string => value === null || value === undefined ? '—' : String(value)
</script>

<template>
  <div class="ui-data-table" :aria-busy="busy || undefined">
    <div class="ui-table-wrap" role="region" :aria-label="caption" tabindex="0">
      <table v-if="rows.length" class="ui-table">
        <caption>{{ caption }}</caption>
        <thead><tr><th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="rowKey(row)">
          <td v-for="column in columns" :key="column.key"><slot name="cell" :row="row" :column="column" :value="valueAt(row, column.key)">{{ text(valueAt(row, column.key)) }}</slot></td>
        </tr></tbody>
      </table>
      <UiState v-else kind="empty" :message="emptyLabel" />
    </div>
    <nav v-if="hasPrevious || hasNext" class="ui-table-pagination" :aria-label="paginationLabel">
      <UiButton :disabled="busy || !hasPrevious" @click="!busy && hasPrevious && emit('previous')">{{ previousLabel }}</UiButton>
      <UiButton :disabled="busy || !hasNext" @click="!busy && hasNext && emit('next')">{{ nextLabel }}</UiButton>
    </nav>
  </div>
</template>
