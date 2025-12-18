<script setup>
import http from '@/utils/dynamic-http';

async function logout() {
  await http.post(`/user/logout`);
  localStorage.removeItem('authToken');
  window.location.href = '/user/login';
}
</script>

<template>
  <button @click="logout">Logout</button>
</template>