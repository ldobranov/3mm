<template>
  <div class="extensions-view">
    <div class="container">
      <h1>Extensions</h1>

      <!-- Upload Section -->
      <div class="upload-section">
        <h2>Upload Extension</h2>
        <form @submit.prevent="uploadExtension" class="upload-form">
          <div class="form-group">
            <label for="extension-file">Extension File (.zip)</label>
            <input
              id="extension-file"
              type="file"
              accept=".zip"
              @change="handleFileSelect"
              required
            />
          </div>
          <button type="submit" :disabled="!selectedFile || uploading" class="upload-btn">
            {{ uploading ? 'Uploading...' : 'Upload Extension' }}
          </button>
        </form>
        <div v-if="uploadError" class="error-message">{{ uploadError }}</div>
        <div v-if="uploadSuccess" class="success-message">{{ uploadSuccess }}</div>
      </div>

      <!-- Extensions List -->
      <div class="extensions-list">
        <h2>Installed Extensions</h2>
        <div v-if="loading" class="loading">Loading extensions...</div>
        <div v-else-if="extensions.length === 0" class="no-extensions">
          No extensions installed yet.
        </div>
        <div v-else class="extensions-grid">
          <div
            v-for="ext in extensions"
            :key="ext.id"
            class="extension-card"
          >
            <div class="extension-header">
              <h3>{{ ext.name }}</h3>
              <span class="extension-version">v{{ ext.version }}</span>
            </div>
            <div class="extension-meta">
              <span class="extension-type">{{ ext.type }}</span>
              <span v-if="ext.author" class="extension-author">by {{ ext.author }}</span>
            </div>
            <p v-if="ext.description" class="extension-description">{{ ext.description }}</p>
            <div class="extension-status">
              <span :class="['status-badge', ext.status]">
                {{ ext.status }}
              </span>
              <label class="toggle-switch">
                <input
                  type="checkbox"
                  :checked="ext.is_enabled"
                  @change="toggleExtension(ext.id, $event)"
                />
                <span class="slider"></span>
              </label>
            </div>
            <div class="extension-actions">
              <button @click="deleteExtension(ext.id)" class="delete-btn">
                Delete
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import http from '@/utils/http';

interface Extension {
  id: number;
  name: string;
  type: string;
  version: string;
  description?: string;
  author?: string;
  status: string;
  is_enabled: boolean;
  created_at: string;
}

const extensions = ref<Extension[]>([]);
const loading = ref(false);
const uploading = ref(false);
const selectedFile = ref<File | null>(null);
const uploadError = ref('');
const uploadSuccess = ref('');

const authHeaders = () => {
  const token = localStorage.getItem('authToken') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const loadExtensions = async () => {
  loading.value = true;
  try {
    const res = await http.get('/api/extensions');
    extensions.value = res.data.items || [];
  } catch (error) {
    console.error('Failed to load extensions:', error);
  } finally {
    loading.value = false;
  }
};

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  selectedFile.value = target.files?.[0] || null;
  uploadError.value = '';
  uploadSuccess.value = '';
};

const uploadExtension = async () => {
  if (!selectedFile.value) return;

  uploading.value = true;
  uploadError.value = '';
  uploadSuccess.value = '';

  const formData = new FormData();
  formData.append('file', selectedFile.value);

  try {
    const res = await http.post(
      '/api/extensions/upload',
      formData
    );

    uploadSuccess.value = `Extension "${res.data.name}" uploaded successfully!`;
    selectedFile.value = null;
    // Reset file input
    const fileInput = document.getElementById('extension-file') as HTMLInputElement;
    if (fileInput) fileInput.value = '';

    // Reload extensions list
    await loadExtensions();
  } catch (error: any) {
    uploadError.value = error.response?.data?.detail || 'Failed to upload extension';
  } finally {
    uploading.value = false;
  }
};

const toggleExtension = async (extensionId: number, event: Event) => {
  const target = event.target as HTMLInputElement;
  const isEnabled = target.checked;

  try {
    await http.patch(
      `/api/extensions/${extensionId}`,
      { is_enabled: isEnabled }
    );

    // Update local state
    const ext = extensions.value.find(e => e.id === extensionId);
    if (ext) {
      ext.is_enabled = isEnabled;
      ext.status = isEnabled ? 'active' : 'inactive';
    }
  } catch (error) {
    console.error('Failed to toggle extension:', error);
    // Revert checkbox
    target.checked = !isEnabled;
  }
};

const deleteExtension = async (extensionId: number) => {
  if (!confirm('Are you sure you want to delete this extension?')) return;

  try {
    await http.delete(`/api/extensions/${extensionId}`);

    // Remove from local state
    extensions.value = extensions.value.filter(e => e.id !== extensionId);
  } catch (error) {
    console.error('Failed to delete extension:', error);
  }
};

onMounted(() => {
  loadExtensions();
});
</script>

<style scoped>
.extensions-view {
  padding: 2rem;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
}

h1 {
  color: var(--text-primary);
  margin-bottom: 2rem;
}

.upload-section {
  background-color: var(--card-bg);
  padding: 2rem;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--card-shadow);
  margin-bottom: 2rem;
}

.upload-form {
  display: flex;
  gap: 1rem;
  align-items: end;
}

.form-group {
  flex: 1;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.form-group input[type="file"] {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-md);
  background-color: var(--input-bg);
  color: var(--text-primary);
}

.upload-btn {
  padding: 0.75rem 1.5rem;
  background-color: var(--button-primary-bg);
  color: var(--button-primary-text);
  border: none;
  border-radius: var(--border-radius-md);
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

.upload-btn:hover:not(:disabled) {
  background-color: var(--button-primary-hover);
}

.upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-message {
  color: var(--error-color);
  margin-top: 1rem;
  padding: 0.75rem;
  background-color: var(--error-bg);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--error-border);
}

.success-message {
  color: var(--success-color);
  margin-top: 1rem;
  padding: 0.75rem;
  background-color: var(--success-bg);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--success-border);
}

.extensions-list {
  background-color: var(--card-bg);
  padding: 2rem;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--card-shadow);
}

.extensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.extension-card {
  background-color: var(--bg-secondary);
  padding: 1.5rem;
  border-radius: var(--border-radius-md);
  border: 1px solid var(--border-color);
}

.extension-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.extension-header h3 {
  margin: 0;
  color: var(--text-primary);
}

.extension-version {
  font-size: 0.875rem;
  color: var(--text-secondary);
  background-color: var(--bg-tertiary);
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
}

.extension-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.extension-description {
  color: var(--text-secondary);
  margin-bottom: 1rem;
  font-size: 0.875rem;
}

.extension-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.status-badge.active {
  background-color: var(--success-bg);
  color: var(--success-color);
}

.status-badge.inactive {
  background-color: var(--warning-bg);
  color: var(--warning-color);
}

.status-badge.error {
  background-color: var(--error-bg);
  color: var(--error-color);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 24px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-tertiary);
  transition: 0.4s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--success-color);
}

input:checked + .slider:before {
  transform: translateX(26px);
}

.extension-actions {
  display: flex;
  justify-content: flex-end;
}

.delete-btn {
  padding: 0.5rem 1rem;
  background-color: var(--error-bg);
  color: var(--error-color);
  border: 1px solid var(--error-border);
  border-radius: var(--border-radius-md);
  cursor: pointer;
  font-size: 0.875rem;
  transition: background-color 0.2s;
}

.delete-btn:hover {
  background-color: var(--error-color);
  color: white;
}

.loading, .no-extensions {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}
</style>