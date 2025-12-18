<template>
  <div class="view">
    <h1 class="view-title">{{ t('profile.title') }}</h1>

    <div v-if="loadError" class="alert mt-2">{{ loadError }}</div>
    <div v-if="saveMessage" class="alert mt-2" :style="{ borderColor: saveIsError ? 'var(--danger)' : 'var(--accent)', color: saveIsError ? 'var(--danger)' : 'var(--color-text)' }">
      {{ saveMessage }}
    </div>

    <div v-if="profileLoading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else-if="user" class="grid">
      <!-- Summary card -->
      <div class="card profile-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-content">
          <h5 class="card-title">{{ t('profile.account') }}</h5>
          <div class="profile-meta">
            <div class="meta-item">
              <span class="meta-label">{{ t('profile.username') }}:</span>
              <strong class="meta-value">{{ user.username }}</strong>
            </div>
            <div class="meta-item">
              <span class="meta-label">{{ t('profile.email') }}:</span>
              <span class="meta-value">{{ user.email }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">{{ t('profile.role') }}:</span>
              <span class="chip" :class="user.role === 'admin' ? 'chip-admin' : 'chip-user'">{{ user.role || 'user' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Edit form -->
      <div class="card profile-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="card-content">
          <h5 class="card-title">{{ t('profile.edit_profile') }}</h5>

          <form @submit.prevent="onSubmit" novalidate style="display:grid; gap: 0.75rem;">
            <div>
              <label class="text-sm" style="display:block; margin-bottom: 0.25rem; color: var(--color-text);">{{ t('profile.username') }}</label>
              <input
                v-model.trim="form.username"
                type="text"
                class="input"
                placeholder="Enter username"
                :disabled="loading"
                required
              />
            </div>

            <div>
              <label class="text-sm" style="display:block; margin-bottom: 0.25rem; color: var(--color-text);">{{ t('profile.email') }}</label>
              <input
                v-model.trim="form.email"
                type="email"
                class="input"
                placeholder="Enter email"
                :disabled="loading"
                required
              />
            </div>

            <div>
              <label class="text-sm" style="display:block; margin-bottom: 0.25rem; color: var(--color-text);">{{ t('profile.new_password') }}</label>
              <input
                v-model="form.password"
                type="password"
                class="input"
                placeholder="••••••••"
                :disabled="loading"
              />
              <div class="text-xs" style="color: var(--color-muted); margin-top: 0.25rem;">Leave empty to keep your current password.</div>
            </div>

            <div class="actions-row" style="justify-content: end;">
              <button type="button" class="button button-secondary" @click="resetForm" :disabled="loading">{{ t('common.cancel') }}</button>
              <button type="submit" class="button button-primary" :disabled="loading">
                <span v-if="loading" class="spinner" role="status" aria-hidden="true" style="width: 1rem; height: 1rem; margin-right: 0.5rem;"></span>
                {{ t('profile.save_changes') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <div v-else class="muted">{{ t('profile.no_data_found') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue';
import http from '@/utils/dynamic-http';
import { useSettingsStore } from '@/stores/settings';
import { useI18n } from '@/utils/i18n';

interface Profile {
  id?: number;
  username: string;
  email: string;
  role?: string;
}

const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);
const { t } = useI18n();
const user = ref<Profile | null>(null);
const form = reactive({ username: '', email: '', password: '' });
const loadError = ref('');
const saveMessage = ref('');
const saveIsError = ref(false);
const loading = ref(false);
const profileLoading = ref(false);

async function fetchProfile() {
  loadError.value = '';
  profileLoading.value = true;
  try {
    // Authorization header is automatically injected by http interceptor
    const res = await http.get('/api/user/profile');
    user.value = res.data as Profile;
    form.username = res.data.username || '';
    form.email = res.data.email || '';
    form.password = '';
  } catch (e) {
    loadError.value = 'Failed to load profile. Please log in again.';
  } finally {
    profileLoading.value = false;
  }
}

async function onSubmit() {
  if (!user.value) return;
  loading.value = true;
  saveMessage.value = '';
  saveIsError.value = false;

  try {
    const payload: Record<string, any> = {
      username: form.username,
      email: form.email,
    };
    if (form.password && form.password.trim().length > 0) {
      payload.password = form.password;
    }

    await http.put('/api/user/profile/update', payload);
    saveMessage.value = 'Profile updated successfully!';
    saveIsError.value = false;
    await fetchProfile();
  } catch (e) {
    saveMessage.value = 'Failed to update profile. Please try again later.';
    saveIsError.value = true;
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  if (!user.value) return;
  form.username = user.value.username || '';
  form.email = user.value.email || '';
  form.password = '';
}

onMounted(() => {
  fetchProfile();
});
</script>

<style scoped>
/* Profile grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.profile-card {
  padding: 1.5rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.profile-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.card-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.profile-meta {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.meta-label {
  font-weight: 500;
  color: var(--text-secondary);
  min-width: 80px;
}

.meta-value {
  color: var(--text-primary);
}

.chip {
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.chip-admin {
  background-color: rgba(220, 53, 69, 0.15);
  color: var(--button-danger-text);
}

.chip-user {
  background-color: rgba(0, 123, 255, 0.15);
  color: var(--button-primary-text);
}

.actions-row {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-start;
}
</style>
