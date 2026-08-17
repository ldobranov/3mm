<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">{{ t('login.title', 'Login') }}</h1>
      <div class="network-recovery">
        <button
          type="button"
          class="button button-secondary network-recovery-button"
          :disabled="resettingNetwork"
          @click="resetNetwork"
        >
          <i class="bi bi-link-45deg network-recovery-icon" aria-hidden="true"></i>
          {{ resettingNetwork
            ? t('login.resetConnectionWorking', 'Resetting…')
            : t('login.resetConnection', 'Reset connection address') }}
        </button>
        <p v-if="resetMessage" class="help-text reset-message">
          {{ resetMessage }}
        </p>
      </div>
    </div>

    <div class="auth-container">
      <div class="card auth-card card-hover">
        <div class="card-content">
          <form @submit.prevent="login" class="auth-form">
            <div class="form-group">
              <label class="form-label">{{ t('login.email', 'Email') }}</label>
              <input
                v-model="email"
                type="email"
                class="input"
                :placeholder="t('login.emailPlaceholder', 'Enter your email')"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label">{{ t('login.password', 'Password') }}</label>
              <input
                v-model="password"
                type="password"
                class="input"
                :placeholder="t('login.passwordPlaceholder', 'Enter your password')"
                required
              />
            </div>

            <button
              type="submit"
              class="button button-primary auth-button"
            >
              <i class="bi bi-box-arrow-in-right auth-icon"></i>{{ t('login.login', 'Login') }}
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
import { defineComponent, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

export default defineComponent({
  setup() {
    const { t } = useI18n();

    const email = ref('');
    const password = ref('');
    const errorMessage = ref('');
    const resetMessage = ref('');
    const resettingNetwork = ref(false);
    const router = useRouter();

    const login = async () => {
      try {
        const response = await http.post('/api/user/login', {
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

        let currentRole = '';

        // Fetch profile to get role, username, and user_id, then store them
        try {
          const profileRes = await http.get('/api/user/profile');
          const role = profileRes.data?.role ?? '';
          currentRole = role;
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
        
        // Notify the application shell that authentication state changed.
        window.dispatchEvent(new Event('menu-refresh'));
        
        const defaultLanding = router.getRoutes().find((route) => {
          if (route.meta?.defaultLanding !== true) return false;
          const requiredRole = route.meta?.requiresRole as string | undefined;
          return !requiredRole || requiredRole === currentRole;
        });
        router.push(defaultLanding?.path || '/user/profile');
      } catch (err) {
        const error = err as any;
        if (error.response && error.response.status === 422) {
          errorMessage.value = t('login.invalidEmailPassword', 'Invalid email or password');
        } else if (error.response && error.response.status === 401) {
          errorMessage.value = t('login.invalidCredentials', 'Invalid credentials');
        } else {
          errorMessage.value = t('login.errorOccurred', 'An error occurred. Please try again.');
        }
      }
    };

    const resetNetwork = async () => {
      resetMessage.value = '';
      resettingNetwork.value = true;
      try {
        await http.clearBackendUrlOverride();
        resetMessage.value = t('login.resetNetworkDone', 'Network override cleared. Reloading…');
        window.setTimeout(() => window.location.reload(), 350);
      } catch (e) {
        console.error('Failed to reset network override:', e);
        resetMessage.value = t('login.resetNetworkFailed', 'Failed to reset network override');
        resettingNetwork.value = false;
      }
    };

    return {
      email,
      password,
      login,
      errorMessage,
      resetMessage,
      resettingNetwork,
      resetNetwork,
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

.network-recovery {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.network-recovery-button {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.network-recovery-icon {
  font-size: 0.95rem;
}

.reset-message {
  margin: 0.5rem 0 0;
  text-align: right;
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

  .network-recovery {
    align-items: stretch;
  }

  .reset-message {
    text-align: left;
  }
}
</style>
