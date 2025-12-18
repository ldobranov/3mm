<template>
  <div class="view" :key="currentLanguage">
    <div class="view-header">
      <h1 class="view-title">{{ t('register.title', 'Register') }}</h1>
    </div>

    <div class="auth-container">
      <div class="card auth-card card-hover">
        <div class="card-content">
          <form @submit.prevent="register" class="auth-form">
            <div class="form-group">
              <label class="form-label">{{ t('register.username', 'Username') }}</label>
              <input
                v-model="username"
                type="text"
                class="input"
                :placeholder="t('register.usernamePlaceholder', 'Choose a username')"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('register.email', 'Email') }}</label>
              <input
                v-model="email"
                type="email"
                class="input"
                :placeholder="t('register.emailPlaceholder', 'Enter your email')"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('register.password', 'Password') }}</label>
              <input
                v-model="password"
                type="password"
                class="input"
                :placeholder="t('register.passwordPlaceholder', 'Create a password')"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('register.confirmPassword', 'Confirm Password') }}</label>
              <input
                v-model="confirmPassword"
                type="password"
                class="input"
                :placeholder="t('register.confirmPasswordPlaceholder', 'Confirm your password')"
                required
              />
            </div>

            <button type="submit" class="button button-primary auth-button">
              <i class="bi bi-person-plus auth-icon"></i>{{ t('register.register', 'Register') }}
            </button>
          </form>

          <div v-if="errorMessage" class="alert alert-danger auth-alert">
            {{ errorMessage }}
          </div>

          <div v-if="successMessage" class="alert alert-success auth-alert">
            {{ successMessage }}
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
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import type { AxiosError } from 'axios';

export default defineComponent({
  setup() {
    const settingsStore = useSettingsStore();
    const { t, currentLanguage } = useI18n();
    const styleSettings = computed(() => settingsStore.styleSettings);
    
    const username = ref('');
    const email = ref('');
    const password = ref('');
    const confirmPassword = ref('');
    const errorMessage = ref('');
    const successMessage = ref('');
    const router = useRouter();

    const register = async () => {
      if (password.value !== confirmPassword.value) {
        errorMessage.value = t('register.passwordsDoNotMatch', 'Passwords do not match');
        return;
      }

      try {
        // Register the user
        const response = await http.post('/api/user/register', {
          username: username.value,
          email: email.value,
          password: password.value,
        });

        successMessage.value = t('register.registrationSuccessful', 'Registration successful! Logging you in...');
        errorMessage.value = '';
        
        // Try to automatically log in the user
        try {
          const loginResponse = await http.post('/api/user/login', {
            email: email.value,
            password: password.value,
          });
          
          const token = loginResponse.data.token;
          if (token) {
            localStorage.setItem('authToken', token);
            
            // Fetch profile to get role and username
            try {
              const profileRes = await http.get('/api/user/profile');
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
          errorMessage.value = t('register.invalidInput', 'Invalid input. Please check your details.');
        } else if (status === 409) {
          errorMessage.value = t('register.userExists', 'User with this email or username already exists.');
        } else {
          errorMessage.value = error.response?.data?.detail || t('register.errorOccurred', 'An error occurred. Please try again.');
        }
        successMessage.value = '';
      }
    };

    return {
      username,
      email,
      password,
      confirmPassword,
      register,
      errorMessage,
      successMessage,
      styleSettings,
      currentLanguage,
      t
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