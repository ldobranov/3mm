<template>
  <div class="login">
    <h1>Login</h1>
    <form @submit.prevent="login">
      <input v-model="email" type="email" placeholder="Email" required />
      <input v-model="password" type="password" placeholder="Password" required />
      <button type="submit">Login</button>
    </form>
    <button @click="logout" type="button">Logout</button>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue';
import axios from 'axios';

export default defineComponent({
  setup() {
    const email = ref('');
    const password = ref('');
    const errorMessage = ref('');

    const login = async () => {
      try {
        const response = await axios.post(`${import.meta.env.VITE_API_BASE_URL}/user/login`, {
          email: email.value,
          password: password.value,
        });

        // Store the token and user role in localStorage
        if (response.data.token) {
          localStorage.setItem('token', response.data.token);
          console.log('Token stored successfully:', response.data.token);
        } else {
          console.error('No token received from server');
        }
        localStorage.setItem('role', response.data.role);

        // Debugging: Log the token to confirm storage
        console.log('Token stored in localStorage:', response.data.token);

        errorMessage.value = '';
        alert('Login successful!');

        // Redirect user based on role
        if (response.data.role === 'admin') {
          window.location.href = '/dashboard';
        } else {
          window.location.href = '/profile';
        }
      } catch (err) {
        const error = err as any; // Explicitly type the error
        if (error.response && error.response.status === 422) {
          errorMessage.value = 'Invalid email or password';
        } else {
          errorMessage.value = 'An error occurred. Please try again.';
        }
      }
    };

    const logout = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          alert('No token found. You are already logged out.');
          return;
        }

        await axios.post(`${import.meta.env.VITE_API_BASE_URL}/user/logout`, {}, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        localStorage.removeItem('token');
        localStorage.removeItem('role');
        alert('Logout successful!');
        window.location.href = '/login';
      } catch (err) {
        console.error('Error during logout:', err);
        alert('An error occurred during logout. Please try again.');
      }
    };

    return { email, password, login, logout, errorMessage };
  },
});
</script>

<style scoped>
.error {
  color: red;
}
</style>