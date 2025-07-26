<template>
  <nav class="navbar navbar-expand-lg navbar-light bg-light">
    <div class="container-fluid">
      <a class="navbar-brand" href="#">Mega Monitor</a>
      <button
        class="navbar-toggler"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#navbarNav"
        aria-controls="navbarNav"
        aria-expanded="false"
        aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav">
          <li v-for="item in menuItems" :key="item.id" class="nav-item">
            <a :href="item.path" class="nav-link">{{ item.name }}</a>
          </li>
        </ul>
      </div>
      <div v-if="errorMessage" class="alert alert-danger mt-3">{{ errorMessage }}</div>
    </div>
  </nav>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';

export default defineComponent({
  name: 'Menu',
  setup() {
    interface MenuItem {
      id: number | string;
      name: string;
      path: string;
    }
    const menuItems = ref<MenuItem[]>([]);
    const errorMessage = ref('');
    let isFetching = false;

    const fetchMenuItems = async () => {
      if (isFetching) return; // Prevent duplicate API calls
      isFetching = true;
      try {
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/menu/read`);
        menuItems.value = response.data.items.sort((a: { order: number }, b: { order: number }) => a.order - b.order);
        errorMessage.value = '';
      } catch (error) {
        errorMessage.value = 'Failed to fetch menu items.';
        console.error(error);
      } finally {
        isFetching = false;
      }
    };

    onMounted(() => {
      console.log('Menu component mounted');
      fetchMenuItems();
    });

    return { menuItems, errorMessage };
  },
});
</script>

<style scoped>
/* Removed custom styles and replaced with Bootstrap classes */
</style>
