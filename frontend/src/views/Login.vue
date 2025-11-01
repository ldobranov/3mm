<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Login</h1>
    </div>

    <div class="card" style="max-width: 400px; margin: 2rem auto;">
      <div style="padding: 2rem;">
        <form @submit.prevent="login" style="display: grid; gap: 1rem;">
          <div>
            <label class="form-label">Email</label>
            <input
              v-model="email"
              type="email"
              class="input"
              placeholder="Enter your email"
              required
            />
          </div>

          <div>
            <label class="form-label">Password</label>
            <input
              v-model="password"
              type="password"
              class="input"
              placeholder="Enter your password"
              required
            />
          </div>

          <button type="submit" class="button button-primary" style="width: 100%;">
            <i class="bi bi-box-arrow-in-right" style="margin-right: 0.5rem;"></i>Login
          </button>
        </form>

        <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">
          {{ errorMessage }}
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue';
import { useRouter } from 'vue-router';
import http from '@/utils/http';

export default defineComponent({
  setup() {
    const email = ref('');
    const password = ref('');
    const errorMessage = ref('');
    const router = useRouter();

    const login = async () => {
      try {
        const response = await http.post('/user/login', {
          email: email.value,
          password: password.value,
        });

        // Store the token first
        const token = response.data.token;
        if (token) {
          localStorage.setItem('authToken', token);
        } else {
          console.error('No token received from server');
          throw new Error('No token received from server');
        }

        // Fetch profile to get role, username, and user_id, then store them
        try {
          const profileRes = await http.get('/user/profile');
          const role = profileRes.data?.role ?? '';
          const username = profileRes.data?.username ?? '';
          const userId = profileRes.data?.id ?? '';
          localStorage.setItem('role', role);
          localStorage.setItem('username', username);
          localStorage.setItem('user_id', String(userId));
        } catch (e) {
          console.error('Failed to fetch profile after login', e);
          localStorage.setItem('role', '');
          localStorage.setItem('username', '');
          localStorage.setItem('user_id', '');
        }

        errorMessage.value = '';
        
        // Trigger menu refresh
        if ((window as any).refreshMenu) {
          (window as any).refreshMenu();
        }
        // Also dispatch a custom event
        window.dispatchEvent(new Event('menu-refresh'));
        
        // Navigate to profile page
        router.push('/user/profile');
      } catch (err) {
        const error = err as any;
        if (error.response && error.response.status === 422) {
          errorMessage.value = 'Invalid email or password';
        } else if (error.response && error.response.status === 401) {
          errorMessage.value = 'Invalid credentials';
        } else {
          errorMessage.value = 'An error occurred. Please try again.';
        }
      }
    };

    return { email, password, login, errorMessage };
  },
});
</script>

<style scoped>
/* Login-specific styles if needed */
</style>