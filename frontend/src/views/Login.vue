<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Login</h1>
    </div>

    <div class="auth-container">
      <div class="card auth-card card-hover">
        <div class="card-content">
          <form @submit.prevent="login" class="auth-form">
            <div class="form-group">
              <label class="form-label">Email</label>
              <input
                v-model="email"
                type="email"
                class="input"
                placeholder="Enter your email"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label">Password</label>
              <input
                v-model="password"
                type="password"
                class="input"
                placeholder="Enter your password"
                required
              />
            </div>

            <button
              type="submit"
              class="button button-primary auth-button"
            >
              <i class="bi bi-box-arrow-in-right auth-icon"></i>Login
            </button>
          </form>

          <div v-if="errorMessage" class="alert alert-danger auth-alert">
            {{ errorMessage }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useSettingsStore } from '@/stores/settings';
import http from '@/utils/http';

export default defineComponent({
  setup() {
    const settingsStore = useSettingsStore();
    const styleSettings = computed(() => settingsStore.styleSettings);
    
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

    return {
      email,
      password,
      login,
      errorMessage,
      styleSettings
    };
  },
});
</script>

<style scoped>
/* Auth container - shared styling that uses CSS variables */
.auth-container {
  max-width: 400px;
  margin: 2rem auto;
}

.auth-card {
  background-color: var(--card-bg);
  color: var(--text-primary);
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.auth-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.card-content {
  padding: 2rem;
}

.auth-form {
  display: grid;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.input {
  padding: 0.5rem;
  border: 1px solid var(--input-border);
  border-radius: var(--border-radius-sm);
  background-color: var(--input-bg);
  color: var(--text-primary);
  font-size: 0.875rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.input:focus {
  outline: none;
  border-color: var(--input-focus-border);
  box-shadow: 0 0 0 1px var(--input-focus-border);
}

.auth-button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background-color: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: 1px solid var(--button-primary-bg);
  border-radius: var(--border-radius-sm);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.auth-button:hover {
  background-color: var(--button-primary-hover);
  border-color: var(--button-primary-hover);
  opacity: 0.9;
  transform: translateY(-1px);
}

.auth-button:active {
  transform: translateY(0);
}

.auth-icon {
  font-size: 1rem;
}

.auth-alert {
  margin-top: 1rem;
}

/* Alert styling using CSS variables */
.alert-danger {
  background-color: var(--color-background-soft);
  color: var(--danger);
  border: 1px solid var(--color-border);
}

.alert-success {
  background-color: var(--color-background-soft);
  color: var(--accent);
  border: 1px solid var(--color-border);
}

@media (max-width: 480px) {
  .auth-container {
    max-width: 100%;
    margin: 1rem;
  }
  
  .card-content {
    padding: 1.5rem;
  }
}
</style>