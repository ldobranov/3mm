<template>
  <div>
    <h1>{{ page.title }}</h1>
    <div v-html="page.content"></div>
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
    const page = ref({ title: '', content: '' });

    onMounted(async () => {
      try {
        const response = await axios.get(`/pages/${props.slug}`); // Corrected the endpoint
        page.value = response.data;
      } catch (error) {
        console.error('Failed to fetch page:', error);
      }
    });

    return { page };
  },
});
</script>

<style scoped>
/* Add any specific styles for the page view here */
</style>
