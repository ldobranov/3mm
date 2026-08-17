<template>
  <div class="view" :key="currentLanguage">
    <div class="view-header">
      <h1 class="view-title">{{ t('extensions.title', 'Extensions') }}</h1>

      <div v-if="isAdmin" class="header-actions">
        <router-link class="ai-builder-link" to="/extensions/ai-builder">
          {{ t('extensions.aiBuilder.open', 'Open AI Builder') }}
        </router-link>
      </div>
    </div>

    <!-- Upload Section -->
    <div v-if="isAdmin" class="card upload-section" :style="{ backgroundColor: settingsStore.styleSettings.cardBg, color: settingsStore.styleSettings.textPrimary, borderColor: settingsStore.styleSettings.cardBorder }">
      <div class="card-content">
        <h2>{{ t('extensions.uploadExtension', 'Upload Extension') }}</h2>
        <form @submit.prevent="uploadExtension" class="upload-form">
          <div class="form-group">
            <label for="extension-file">{{ t('extensions.extensionFile', 'Extension File (.zip)') }}</label>
            <input
              id="extension-file"
              type="file"
              accept=".zip"
              @change="handleFileSelect"
              required
            />
          </div>
          <button type="submit" :disabled="!selectedFile || uploading" class="upload-btn">
            {{ uploading ? t('extensions.uploading', 'Uploading...') : t('extensions.uploadExtensionButton', 'Upload Extension') }}
          </button>
        </form>
        <div v-if="uploadError" class="error-message">{{ uploadError }}</div>
        <div v-if="uploadSuccess" class="success-message">{{ uploadSuccess }}</div>
      </div>
    </div>

    <!-- Extensions List -->
    <div class="card extensions-list" :style="{ backgroundColor: settingsStore.styleSettings.cardBg, color: settingsStore.styleSettings.textPrimary, borderColor: settingsStore.styleSettings.cardBorder }">
      <div class="card-content">
        <h2>{{ t('extensions.installedExtensions', 'Installed Extensions') }}</h2>
        <div v-if="operationError" class="error-message">{{ operationError }}</div>
        <div v-if="loading" class="loading">{{ t('extensions.loadingExtensions', 'Loading extensions...') }}</div>
        <div v-else-if="extensions.length === 0" class="no-extensions">
          {{ t('extensions.noExtensionsInstalled', 'No extensions installed yet.') }}
        </div>
        <div v-else class="extensions-grid">
          <div
            v-for="ext in extensions"
            :key="ext.id"
            class="extension-card"
            :style="{ backgroundColor: settingsStore.styleSettings.cardBg, color: settingsStore.styleSettings.textPrimary, borderColor: settingsStore.styleSettings.cardBorder }"
          >
            <div class="extension-header">
              <h3>{{ ext.name }}</h3>
              <span class="extension-version">{{ t('extensions.version', 'v') }}{{ ext.version }}</span>
            </div>
            <div class="extension-meta">
              <span class="extension-type">{{ ext.type }}</span>
              <span v-if="ext.source === 'runtime'" class="runtime-badge">Runtime</span>
              <span v-if="ext.author" class="extension-author">{{ t('extensions.by', 'by') }} {{ ext.author }}</span>
            </div>
            <p v-if="ext.description" class="extension-description">{{ ext.description }}</p>
            <div class="extension-status">
              <span :class="['status-badge', ext.status]">
                {{ t(`extensions.${ext.status}`, ext.status) }}
              </span>
              <label class="toggle-switch">
                <input
                  type="checkbox"
                  :checked="ext.is_enabled"
                  :disabled="!ext.can_manage || !ext.is_installed || operationBusy === ext.id"
                  @change="toggleExtension(ext, $event)"
                />
                <span class="slider"></span>
              </label>
            </div>
            <div class="extension-actions">
               <div v-if="ext.source === 'runtime' && ext.is_installed" class="version-controls">
                 <label :for="`version-${ext.id}`">{{ t('extensions.version', 'Version') }}</label>
                 <select :id="`version-${ext.id}`" v-model="selectedVersions[ext.id]">
                   <option v-for="version in ext.available_versions" :key="version" :value="version">
                     {{ version }}
                   </option>
                 </select>
                 <button
                   class="version-btn"
                   :disabled="!ext.can_manage || selectedVersions[ext.id] === ext.version || operationBusy === ext.id"
                   @click="activateVersion(ext)"
                 >
                   {{ activatingVersion === ext.id
                     ? t('extensions.activatingVersion', 'Activating...')
                     : t('extensions.activateVersion', 'Activate version') }}
                 </button>
               </div>
               <span v-if="ext.source === 'runtime' && ext.is_installed" class="managed-note">
                 {{ t('extensions.runtimeDataPreserved', 'Data is preserved when disabled') }}
               </span>
               <button
                 v-if="ext.source === 'runtime' && !ext.is_installed && ext.can_manage"
                 class="version-btn"
                 :disabled="operationBusy === ext.id"
                 @click="reinstallExtension(ext)"
               >
                 {{ operationBusy === ext.id
                   ? t('extensions.reinstalling', 'Reinstalling...')
                   : t('extensions.reinstall', 'Reinstall') }}
               </button>
               <button
                 v-if="ext.source === 'legacy' || (ext.is_installed && ext.can_manage)"
                 @click="deleteExtension(ext)"
                 class="delete-btn"
                 :disabled="operationBusy === ext.id"
               >
                 {{ ext.source === 'runtime'
                   ? t('extensions.uninstall', 'Uninstall')
                   : t('extensions.delete', 'Delete') }}
               </button>
             </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Extension Modal -->
    <div v-if="showDeleteModal" class="modal-backdrop" @click="cancelDeleteExtension">
      <div class="modal-container">
        <div class="modal-surface" @click.stop>
          <div class="modal-header">
            <h2>{{ extensionToDelete?.source === 'runtime'
              ? t('extensions.uninstallExtension', 'Uninstall Extension')
              : t('extensions.deleteExtension', 'Delete Extension') }}</h2>
          </div>

          <div class="modal-body">
            <p>{{ extensionToDelete?.source === 'runtime'
              ? t('extensions.uninstallConfirm', 'Uninstall this runtime extension? Its routes and menu entries will be removed.')
              : t('extensions.deleteConfirm', 'Are you sure you want to delete this extension?') }}</p>
            <p><strong>{{ extensionToDelete?.name }} v{{ extensionToDelete?.version }}</strong></p>

            <!-- Database data deletion checkbox - only show if extension has tables -->
            <div v-if="extensionToDelete?.type === 'extension' || extensionToDelete?.source === 'runtime'" class="form-field">
              <label class="checkbox-label">
                <input type="checkbox" v-model="deleteDatabaseData" />
                {{ extensionToDelete?.source === 'runtime'
                  ? t('extensions.deleteRuntimeData', 'Also permanently delete all data created by this extension')
                  : t('extensions.deleteDatabaseData', 'Also delete all database tables and data created by this extension') }}
              </label>
              <small class="help-text">{{ extensionToDelete?.source === 'runtime'
                ? (deleteDatabaseData
                  ? t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All data will be permanently lost.')
                  : t('extensions.preserveRuntimeData', 'Data will be preserved and becomes available after reinstalling the extension.'))
                : t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All selected data will be permanently lost.') }}</small>
            </div>

            <!-- Uploaded files deletion checkbox - only show if extension uploads files -->
            <div v-if="extensionToDelete?.type === 'extension'" class="form-field">
              <label class="checkbox-label">
                <input type="checkbox" v-model="deleteUploadedFiles" />
                {{ t('extensions.deleteUploadedFiles', 'Also delete all uploaded files (images, documents, etc.) for this extension') }}
              </label>
              <small class="help-text">{{ t('extensions.deleteUploadedFilesWarning', 'This will remove all files uploaded by this extension from the server.') }}</small>
            </div>
          </div>

          <div class="modal-footer">
            <button @click="cancelDeleteExtension" class="button button-secondary" :disabled="operationBusy !== null">
              {{ t('extensions.cancel', 'Cancel') }}
            </button>
            <button @click="confirmDeleteExtension" class="button button-danger" :disabled="operationBusy !== null">
              {{ extensionToDelete?.source === 'runtime'
                ? t('extensions.uninstall', 'Uninstall')
                : t('extensions.delete', 'Delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import http from '@/utils/dynamic-http';
import { useI18n, i18n } from '@/utils/i18n';
import { useSettingsStore } from '@/stores/settings';
import { useThemeStore } from '@/stores/theme';
import { useRouter } from 'vue-router';
import { reloadRuntimeExtensionRoutes } from '@/utils/runtime-extensions';

const { t, currentLanguage } = useI18n();
const settingsStore = useSettingsStore();
const themeStore = useThemeStore();
const router = useRouter();


interface Extension {
  id: string;
  source: 'legacy' | 'runtime';
  name: string;
  type: string;
  version: string;
  description?: string;
  author?: string;
  status: string;
  is_enabled: boolean;
  created_at: string;
  can_manage: boolean;
  available_versions: string[];
  package_sha256?: string | null;
  is_installed: boolean;
}

const extensions = ref<Extension[]>([]);
const loading = ref(false);
const uploading = ref(false);
const selectedFile = ref<File | null>(null);
const uploadError = ref('');
const uploadSuccess = ref('');
const showDeleteModal = ref(false);
const extensionToDelete = ref<Extension | null>(null);
const deleteDatabaseData = ref(false);
const deleteUploadedFiles = ref(false);
const selectedVersions = ref<Record<string, string>>({});
const activatingVersion = ref<string | null>(null);
const operationBusy = ref<string | null>(null);
const operationError = ref('');

const isAdmin = computed(() => (localStorage.getItem('role') || '') === 'admin');

const authHeaders = () => {
  const token = localStorage.getItem('authToken') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const loadExtensions = async () => {
  loading.value = true;
  try {
    const res = await http.get('/api/v1/runtime-extensions/catalog', {
      params: { language: currentLanguage.value }
    });
    extensions.value = res.data || [];
    selectedVersions.value = Object.fromEntries(
      extensions.value.map(extension => [extension.id, extension.version])
    );

    // Load translations for enabled extensions
    for (const ext of extensions.value) {
      if (ext.source === 'legacy' && ext.is_enabled) {
        await i18n.loadExtensionTranslationsForExtension(ext.name, currentLanguage.value);
      }
    }
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

    uploadSuccess.value = t('extensions.uploadSuccess', 'Extension "{name}" uploaded successfully!', { name: res.data.name });
    selectedFile.value = null;
    // Reset file input
    const fileInput = document.getElementById('extension-file') as HTMLInputElement;
    if (fileInput) fileInput.value = '';

    // Reload extensions list
    await loadExtensions();
  } catch (error: any) {
    uploadError.value = error.response?.data?.detail || t('extensions.uploadError', 'Failed to upload extension');
  } finally {
    uploading.value = false;
  }
};

const toggleExtension = async (extension: Extension, event: Event) => {
  const target = event.target as HTMLInputElement;
  const isEnabled = target.checked;
  operationBusy.value = extension.id;
  operationError.value = '';

  try {
    if (extension.source === 'runtime') {
      const moduleId = extension.id.replace('runtime:', '');
      await http.patch(
        `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}`,
        { enabled: isEnabled }
      );
      await reloadRuntimeExtensionRoutes(router);
      window.dispatchEvent(new Event('menu-refresh'));
    } else {
      await http.patch(
        `/api/extensions/${extension.id.replace('legacy:', '')}`,
        { is_enabled: isEnabled }
      );
    }

    // Update local state
    const ext = extensions.value.find(e => e.id === extension.id);
    if (ext) {
      ext.is_enabled = isEnabled;
      ext.status = isEnabled ? 'active' : 'inactive';

      // Reload translations if extension was enabled
      if (extension.source === 'legacy' && isEnabled) {
        await i18n.loadExtensionTranslationsForExtension(ext.name, currentLanguage.value);
      }
    }
  } catch (error) {
    console.error('Failed to toggle extension:', error);
    operationError.value = errorMessage(error, t('extensions.toggleError', 'Could not change the extension status.'));
    // Revert checkbox
    target.checked = !isEnabled;
  } finally {
    operationBusy.value = null;
  }
};

const deleteExtension = (extension: Extension) => {
  extensionToDelete.value = extension;
  deleteDatabaseData.value = false;
  deleteUploadedFiles.value = false;
  showDeleteModal.value = true;
};

const activateVersion = async (extension: Extension) => {
  const version = selectedVersions.value[extension.id];
  if (extension.source !== 'runtime' || !version || version === extension.version) return;

  activatingVersion.value = extension.id;
  operationBusy.value = extension.id;
  operationError.value = '';
  try {
    const moduleId = extension.id.replace('runtime:', '');
    await http.post(
      `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}/versions/${encodeURIComponent(version)}/activate`
    );
    await reloadRuntimeExtensionRoutes(router);
    window.dispatchEvent(new Event('menu-refresh'));
    await loadExtensions();
  } catch (error) {
    console.error('Failed to activate runtime extension version:', error);
    operationError.value = errorMessage(error, t('extensions.versionError', 'Could not activate the selected version.'));
  } finally {
    activatingVersion.value = null;
    operationBusy.value = null;
  }
};

const errorMessage = (error: any, fallback: string): string =>
  error?.response?.data?.detail || error?.response?.data?.error || fallback;

const reinstallExtension = async (extension: Extension) => {
  if (!extension.package_sha256 || !extension.can_manage) return;
  operationBusy.value = extension.id;
  operationError.value = '';
  try {
    await http.post(`/api/v1/runtime-extensions/packages/${extension.package_sha256}/activate`);
    await reloadRuntimeExtensionRoutes(router);
    window.dispatchEvent(new Event('menu-refresh'));
    await loadExtensions();
  } catch (error) {
    console.error('Failed to reinstall runtime extension:', error);
    operationError.value = errorMessage(error, t('extensions.reinstallError', 'Could not reinstall the extension.'));
  } finally {
    operationBusy.value = null;
  }
};

const confirmDeleteExtension = async () => {
  if (!extensionToDelete.value) return;
  operationBusy.value = extensionToDelete.value.id;
  operationError.value = '';

  try {
    if (extensionToDelete.value.source === 'runtime') {
      const moduleId = extensionToDelete.value.id.replace('runtime:', '');
      await http.delete(
        `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}`,
        { params: { delete_data: deleteDatabaseData.value } }
      );
      await reloadRuntimeExtensionRoutes(router);
      window.dispatchEvent(new Event('menu-refresh'));
    } else {
      await http.delete(`/api/extensions/${extensionToDelete.value.id.replace('legacy:', '')}`, {
        params: {
          deleteData: deleteDatabaseData.value,
          deleteFiles: deleteUploadedFiles.value
        }
      });
    }

    await loadExtensions();
    showDeleteModal.value = false;
    extensionToDelete.value = null;
  } catch (error) {
    console.error('Failed to delete extension:', error);
    operationError.value = errorMessage(error, t('extensions.uninstallError', 'Could not remove the extension.'));
  } finally {
    operationBusy.value = null;
  }
};

const cancelDeleteExtension = () => {
  showDeleteModal.value = false;
  extensionToDelete.value = null;
  deleteDatabaseData.value = false;
  deleteUploadedFiles.value = false;
};

onMounted(async () => {
  await loadExtensions();

  // Load settings and apply CSS variables
  await settingsStore.loadSettings();
  settingsStore.updateCSSVariables();
});

// Watch for theme changes and update CSS variables
watch(() => themeStore.theme, async () => {
  await settingsStore.loadSettings();
  settingsStore.updateCSSVariables();
});

// Watch for language changes and reload extension translations
watch(currentLanguage, async () => {
  await loadExtensions();
});
</script>

<style scoped>
.upload-section {
  margin-bottom: 2rem;
}

.header-actions {
  margin-top: 0.5rem;
}

.ai-builder-link {
  display: inline-block;
  padding: 0.5rem 0.75rem;
  border-radius: var(--border-radius-md);
  border: 1px solid var(--card-border);
  text-decoration: none;
  color: var(--text-primary);
}

.ai-builder-link:hover {
  opacity: 0.9;
}

.card-content {
  padding: 1.5rem;
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
  margin-top: 2rem;
}

.extensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.extension-card {
  padding: 1.5rem;
  border-radius: var(--border-radius-md);
  border: 1px solid var(--card-border);
  box-shadow: var(--card-shadow);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.extension-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
  gap: 1rem;
}

.extension-header h3 {
  margin: 0;
  color: var(--text-primary);
  word-break: break-word;
  flex: 1;
  min-width: 0;
}

.extension-version {
  font-size: 0.875rem;
  color: var(--text-secondary);
  background-color: var(--card-bg);
  border: 1px solid var(--card-border);
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  flex-shrink: 0;
  white-space: nowrap;
}

.extension-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.runtime-badge {
  padding: 0.125rem 0.5rem;
  border: 1px solid var(--card-border);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.managed-note {
  color: var(--text-secondary);
  font-size: 0.8125rem;
}

.toggle-switch input:disabled + .slider {
  cursor: not-allowed;
  opacity: 0.7;
}

.extension-description {
  color: var(--text-secondary);
  margin-bottom: 1rem;
  font-size: 0.875rem;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.extension-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  gap: 1rem;
  flex-wrap: wrap;
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
  background-color: var(--card-border);
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
  background-color: var(--text-primary);
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
  align-items: end;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.version-controls {
  display: flex;
  align-items: end;
  gap: 0.5rem;
  margin-right: auto;
}

.version-controls label {
  align-self: center;
  color: var(--text-secondary);
  font-size: 0.8125rem;
}

.version-controls select,
.version-btn {
  min-height: 2.25rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--input-bg);
  color: var(--text-primary);
  padding: 0.375rem 0.625rem;
}

.version-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
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
