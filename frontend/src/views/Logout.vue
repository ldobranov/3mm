<script setup>
import { onMounted } from 'vue';
import http from '@/utils/dynamic-http';

onMounted(async () => {
  const token = localStorage.getItem('authToken');
  if (token) {
    await http.post('/api/user/logout', {}, {
      headers: { Authorization: `Bearer ${token}` }
    });
  }
  localStorage.clear(); // This removes all keys for your app
  window.location.replace('/user/login');
});
</script>

<template>
  <div>Logging out...</div>
</template>
