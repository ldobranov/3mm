<template>
  <div>
    <h1 v-if="page">{{ page.title }}</h1>
    <div v-if="page" v-html="page.content"></div>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, onMounted, ref } from 'vue';
import axios from 'axios';

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
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/pages/${props.slug}`);
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
.error {
  color: red;
  font-weight: bold;
}
/* Add any specific styles for the page view here */
</style>
