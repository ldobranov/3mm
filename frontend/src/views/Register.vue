<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Register</h1>
    </div>

    <div class="card" style="max-width: 400px; margin: 2rem auto;">
      <div style="padding: 2rem;">
        <form @submit.prevent="register" style="display: grid; gap: 1rem;">
          <div>
            <label class="form-label">Username</label>
            <input
              v-model="username"
              type="text"
              class="input"
              placeholder="Choose a username"
              required
            />
          </div>

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
              placeholder="Create a password"
              required
            />
          </div>

          <div>
            <label class="form-label">Confirm Password</label>
            <input
              v-model="confirmPassword"
              type="password"
              class="input"
              placeholder="Confirm your password"
              required
            />
          </div>

          <button type="submit" class="button button-primary" style="width: 100%;">
            <i class="bi bi-person-plus" style="margin-right: 0.5rem;"></i>Register
          </button>
        </form>

        <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">
          {{ errorMessage }}
        </div>

        <div v-if="successMessage" class="alert alert-success" style="margin-top: 1rem;">
          {{ successMessage }}
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue';
import { useRouter } from 'vue-router';
import http from '@/utils/http';
import type { AxiosError } from 'axios';

export default defineComponent({
  setup() {
    const username = ref('');
    const email = ref('');
    const password = ref('');
    const confirmPassword = ref('');
    const errorMessage = ref('');
    const successMessage = ref('');
    const router = useRouter();

    const register = async () => {
      if (password.value !== confirmPassword.value) {
        errorMessage.value = 'Passwords do not match';
        return;
      }

      try {
        // Register the user
        const response = await http.post('/user/register', {
          username: username.value,
          email: email.value,
          password: password.value,
        });
        
        successMessage.value = 'Registration successful! Logging you in...';
        errorMessage.value = '';
        
        // Try to automatically log in the user
        try {
          const loginResponse = await http.post('/user/login', {
            email: email.value,
            password: password.value,
          });
          
          const token = loginResponse.data.token;
          if (token) {
            localStorage.setItem('authToken', token);
            
            // Fetch profile to get role and username
            try {
              const profileRes = await http.get('/user/profile');
              const role = profileRes.data?.role ?? '';
              const username = profileRes.data?.username ?? '';
              localStorage.setItem('role', role);
              localStorage.setItem('username', username);
            } catch (e) {
              console.error('Failed to fetch profile after registration', e);
            }
            
            // Trigger menu refresh
            if ((window as any).refreshMenu) {
              (window as any).refreshMenu();
            }
            window.dispatchEvent(new Event('menu-refresh'));
            
            // Navigate to profile
            router.push('/user/profile');
          }
        } catch (loginErr) {
          // If auto-login fails, redirect to login page
          setTimeout(() => {
            router.push('/user/login');
          }, 2000);
        }
      } catch (err) {
        const error = err as AxiosError<any>;
        const status = error.response?.status;
        if (status === 422) {
          errorMessage.value = 'Invalid input. Please check your details.';
        } else if (status === 409) {
          errorMessage.value = 'User with this email or username already exists.';
        } else {
          errorMessage.value = error.response?.data?.detail || 'An error occurred. Please try again.';
        }
        successMessage.value = '';
      }
    };

    return { username, email, password, confirmPassword, register, errorMessage, successMessage };
  },
});
</script>

<style scoped>
/* Register-specific styles if needed */
</style>