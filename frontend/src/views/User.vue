<script setup>
import http from '@/utils/http';

async function logout() {
  const token = localStorage.getItem('authToken');
  await http.post(`${import.meta.env.VITE_API_BASE_URL}/user/logout`, {}, {
    headers: { Authorization: `Bearer ${token}` }
  });
  localStorage.removeItem('authToken');
  window.location.href = '/user/login';
}
</script>

<template>
  <button @click="logout">Logout</button>
</template>