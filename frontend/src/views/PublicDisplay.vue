<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import http from '@/utils/http';
import DisplayCanvas from '@/components/DisplayCanvas.vue';

const route = useRoute();
const data = ref<{ display: any; widgets: any[] } | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    const res = await http.get(`${import.meta.env.VITE_API_BASE_URL}/api/public/@${route.params.username}/${route.params.slug}`);
    data.value = res.data;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load';
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="view" style="padding: 0;">
    <div v-if="loading" class="text-center" style="padding: 2rem;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>
    <div v-else-if="error" class="alert alert-danger" style="margin: 2rem;">
      {{ error }}
    </div>
    <div v-else>
      <DisplayCanvas :widgets="data!.widgets" />
    </div>
  </div>
</template>