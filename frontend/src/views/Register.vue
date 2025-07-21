<template>
  <div class="register">
    <h1>Register</h1>
    <form @submit.prevent="register">
      <input v-model="username" type="text" placeholder="Username" required />
      <input v-model="email" type="email" placeholder="Email" required />
      <input v-model="password" type="password" placeholder="Password" required />
      <input v-model="confirmPassword" type="password" placeholder="Confirm Password" required />
      <button type="submit">Register</button>
    </form>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="success">{{ successMessage }}</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue';
import axios from 'axios';

export default defineComponent({
  setup() {
    const username = ref('');
    const email = ref('');
    const password = ref('');
    const confirmPassword = ref('');
    const errorMessage = ref('');
    const successMessage = ref('');

    const register = async () => {
      if (password.value !== confirmPassword.value) {
        errorMessage.value = 'Passwords do not match';
        return;
      }

      try {
        const response = await axios.post(`${import.meta.env.VITE_API_BASE_URL}/register`, {
          username: username.value,
          email: email.value,
          password: password.value,
        });
        successMessage.value = 'Registration successful! You can now log in.';
        errorMessage.value = '';
      } catch (error) {
        if (error.response && error.response.status === 422) {
          errorMessage.value = 'Invalid input. Please check your details.';
        } else {
          errorMessage.value = 'An error occurred. Please try again.';
        }
      }
    };

    return { username, email, password, confirmPassword, register, errorMessage, successMessage };
  },
});
</script>

<style scoped>
.error {
  color: red;
}
.success {
  color: green;
}
</style>