<template>
  <div class="view">
    <div v-if="page" class="view-header">
      <h1 class="view-title">{{ page.title }}</h1>
    </div>

    <div v-if="page" class="card" style="max-width: 800px; margin: 2rem auto;">
      <div style="padding: 2rem;">
        <div v-html="page.content" style="line-height: 1.6;"></div>
      </div>
    </div>

    <div v-if="errorMessage" class="alert alert-danger" style="margin: 2rem auto; max-width: 600px;">
      {{ errorMessage }}
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, onMounted, ref } from 'vue';
import http from '@/utils/http';

export default defineComponent({
  props: {
    slug: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    const page = ref<{ title: string; content: string } | null>(null);
    const errorMessage = ref('');

    const fetchPage = async () => {
      try {
        const token = localStorage.getItem('authToken') || '';
        const response = await http.get(`${import.meta.env.VITE_API_BASE_URL}/pages/${props.slug}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        page.value = response.data;
        errorMessage.value = '';
      } catch (error) {
        console.error('Error fetching page:', error);
        errorMessage.value = 'Failed to fetch page content.';
      }
    };

    onMounted(fetchPage);

    return { page, errorMessage };
  },
});
</script>

<style scoped>
/* PageView-specific styles if needed */
</style>
