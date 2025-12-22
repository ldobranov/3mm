<template>
  <div class="settings-section">
    <div class="section-header">
      <h3 class="section-title">{{ t('settings.networkConfiguration', 'Network Configuration') }}</h3>
      <p class="section-description">
        {{ t('settings.networkDescription', 'Configure how the frontend connects to the backend server. This is useful when deploying to different environments or using external IP addresses.') }}
      </p>
    </div>

    <div class="network-config-container">
      <!-- Auto-detection section -->
      <div class="auto-detect-section">
        <h4>{{ t('settings.autoDetection', 'Auto-Detection') }}</h4>
        <p class="text-muted">
          {{ t('settings.autoDetectionDescription', 'Automatically detect the correct URLs based on your current location.') }}
        </p>
        
        <div class="detected-info" v-if="detectedConfig">
          <div class="info-row">
            <strong>{{ t('settings.detectedBackendUrl', 'Detected Backend URL') }}:</strong>
            <code>{{ detectedConfig.backend_url }}</code>
          </div>
          <div class="info-row">
            <strong>{{ t('settings.detectedFrontendUrl', 'Detected Frontend URL') }}:</strong>
            <code>{{ detectedConfig.frontend_url }}</code>
          </div>
          <div class="info-row" v-if="detectedConfig.detected_ip">
            <strong>{{ t('settings.detectedIP', 'Detected IP') }}:</strong>
            <code>{{ detectedConfig.detected_ip }}</code>
          </div>
        </div>

        <button 
          @click="detectConfiguration" 
          :disabled="detecting"
          class="btn btn-outline-primary"
        >
          <span v-if="detecting" class="spinner-border spinner-border-sm me-2"></span>
          {{ t('settings.detectConfiguration', 'Detect Configuration') }}
        </button>

        <button 
          v-if="detectedConfig && !isCurrentConfigDetected"
          @click="applyDetectedConfiguration" 
          :disabled="applying"
          class="btn btn-primary ms-2"
        >
          <span v-if="applying" class="spinner-border spinner-border-sm me-2"></span>
          {{ t('settings.applyDetected', 'Apply Detected Configuration') }}
        </button>
      </div>

      <hr>

      <!-- Manual configuration section -->
      <div class="manual-config-section">
        <h4>{{ t('settings.manualConfiguration', 'Manual Configuration') }}</h4>
        <p class="text-muted">
          {{ t('settings.manualDescription', 'Manually specify the backend URL if auto-detection does not work correctly.') }}
        </p>

        <form @submit.prevent="saveConfiguration">
          <div class="form-group">
            <label for="backendUrl" class="form-label">
              {{ t('settings.backendUrl', 'Backend URL') }}
              <span class="required">*</span>
            </label>
            <input
              id="backendUrl"
              v-model="configForm.backend_url"
              type="url"
              required
              class="form-control"
              :placeholder="t('settings.backendUrlPlaceholder', defaultBackendUrl)"
            />
            <div class="form-text">
              {{ t('settings.backendUrlHelp', 'The full URL to your backend server including protocol and port.') }}
            </div>
          </div>

          <div class="form-group">
            <label for="frontendUrl" class="form-label">
              {{ t('settings.frontendUrl', 'Frontend URL') }}
            </label>
            <input
              id="frontendUrl"
              v-model="configForm.frontend_url"
              type="url"
              class="form-control"
              :placeholder="t('settings.frontendUrlPlaceholder', 'http://localhost:5173')"
            />
            <div class="form-text">
              {{ t('settings.frontendUrlHelp', 'Optional: The URL where this frontend is hosted.') }}
            </div>
          </div>

          <div class="form-group">
            <label for="description" class="form-label">
              {{ t('settings.description', 'Description') }}
            </label>
            <textarea
              id="description"
              v-model="configForm.description"
              class="form-control"
              rows="2"
              :placeholder="t('settings.descriptionPlaceholder', 'Configuration description (optional)')"
            ></textarea>
          </div>

          <!-- Current configuration display -->
          <div class="current-config" v-if="currentConfig">
            <h5>{{ t('settings.currentConfiguration', 'Current Configuration') }}</h5>
            <div class="config-details">
              <div class="config-item">
                <strong>{{ t('settings.backendUrl', 'Backend URL') }}:</strong>
                <code>{{ currentConfig.backend_url }}</code>
                <span v-if="currentConfig.is_default" class="badge bg-secondary">{{ t('settings.default', 'Default') }}</span>
              </div>
              <div class="config-item" v-if="currentConfig.frontend_url">
                <strong>{{ t('settings.frontendUrl', 'Frontend URL') }}:</strong>
                <code>{{ currentConfig.frontend_url }}</code>
              </div>
              <div class="config-item" v-if="currentConfig.description">
                <strong>{{ t('settings.description', 'Description') }}:</strong>
                <span>{{ currentConfig.description }}</span>
              </div>
            </div>
          </div>

          <div class="action-buttons">
            <button 
              type="submit" 
              :disabled="saving || !configForm.backend_url"
              class="btn btn-primary"
            >
              <span v-if="saving" class="spinner-border spinner-border-sm me-2"></span>
              {{ t('settings.saveConfiguration', 'Save Configuration') }}
            </button>

            <button 
              type="button"
              @click="resetToDefaults"
              :disabled="saving"
              class="btn btn-outline-secondary"
            >
              {{ t('settings.resetToDefaults', 'Reset to Defaults') }}
            </button>

            <button 
              type="button"
              @click="testConnection"
              :disabled="saving || testing || !configForm.backend_url"
              class="btn btn-outline-info"
            >
              <span v-if="testing" class="spinner-border spinner-border-sm me-2"></span>
              {{ t('settings.testConnection', 'Test Connection') }}
            </button>
          </div>
        </form>
      </div>

      <!-- Connection test result -->
      <div v-if="connectionTest" class="connection-test-result" :class="connectionTest.success ? 'alert alert-success' : 'alert alert-danger'">
        <strong>{{ connectionTest.success ? t('settings.connectionSuccessful', 'Connection Successful!') : t('settings.connectionFailed', 'Connection Failed!') }}</strong>
        <p v-if="connectionTest.message" class="mb-0">{{ connectionTest.message }}</p>
        <p v-if="connectionTest.error" class="mb-0 text-danger">{{ connectionTest.error }}</p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, computed } from 'vue';
import http from '@/utils/dynamic-http';
import { useI18n } from '@/utils/i18n';

interface ConfigForm {
  backend_url: string;
  frontend_url: string;
  description: string;
}

interface ConfigResponse {
  backend_url: string;
  frontend_url?: string;
  description?: string;
  is_default?: boolean;
}

interface DetectedConfig {
  frontend_url: string;
  backend_url: string;
  detected_ip: string;
  host?: string;
}

interface ConnectionTestResult {
  success: boolean;
  message?: string;
  error?: string;
}

export default defineComponent({
  name: 'NetworkConfigurationSection',
  emits: ['config-updated'],
  setup(props, { emit }) {
    const { t } = useI18n();

    // Get config values from global constants
    const defaultBackendUrl = (globalThis as any).__BACKEND_URL__ || 'http://localhost:8887';
    const defaultFrontendUrl = (globalThis as any).__FRONTEND_URL__ || 'http://localhost:5173';
    
    const saving = ref(false);
    const detecting = ref(false);
    const applying = ref(false);
    const testing = ref(false);
    
    const currentConfig = ref<ConfigResponse | null>(null);
    const detectedConfig = ref<DetectedConfig | null>(null);
    const connectionTest = ref<ConnectionTestResult | null>(null);
    
    const configForm = reactive<ConfigForm>({
      backend_url: '',
      frontend_url: '',
      description: ''
    });

    // Load current configuration
    const loadCurrentConfiguration = async () => {
      try {
        const response = await http.get('/frontend-config');
        currentConfig.value = response.data;
        
        // Populate form with current values
        configForm.backend_url = response.data.backend_url;
        configForm.frontend_url = response.data.frontend_url || '';
        configForm.description = response.data.description || '';
      } catch (error) {
        console.error('Failed to load current configuration:', error);
        // Set default values
        configForm.backend_url = defaultBackendUrl;
        configForm.frontend_url = defaultFrontendUrl;
      }
    };

    // Auto-detect configuration
    const detectConfiguration = async () => {
      detecting.value = true;
      detectedConfig.value = null;
      
      try {
        const response = await http.post('/frontend-config/detect');
        detectedConfig.value = response.data;
        
        // Auto-apply if no current config exists
        if (!currentConfig.value || currentConfig.value.is_default) {
          await applyDetectedConfiguration();
        }
      } catch (error) {
        console.error('Failed to detect configuration:', error);
      } finally {
        detecting.value = false;
      }
    };

    // Apply detected configuration
    const applyDetectedConfiguration = async () => {
      if (!detectedConfig.value) return;
      
      applying.value = true;
      
      try {
        const response = await http.post('/settings/auto-configure');
        
        // Update current config
        let backendUrl = response.data.backend_url;
        let frontendUrl = response.data.frontend_url;

        // Check if the backend URL is a JSON string (new format)
        try {
          const parsedConfig = JSON.parse(backendUrl);
          backendUrl = parsedConfig.backend_url;
          frontendUrl = parsedConfig.frontend_url || frontendUrl;
        } catch (e) {
          // Not JSON, use as-is (old format)
        }

        currentConfig.value = {
          backend_url: backendUrl,
          frontend_url: frontendUrl,
          description: 'Auto-configured frontend backend URL'
        };
        
        // Update form
        configForm.backend_url = backendUrl;
        configForm.frontend_url = frontendUrl;
        configForm.description = currentConfig.value.description || '';

        // Apply to the running app immediately (no reload)
        await http.setBackendUrlOverride(backendUrl);
        
        // Emit event to parent
        emit('config-updated', currentConfig.value);
        
        // Clear detected config since it's now applied
        detectedConfig.value = null;
        
      } catch (error) {
        console.error('Failed to apply detected configuration:', error);
      } finally {
        applying.value = false;
      }
    };

    // Check if current config matches detected config
    const isCurrentConfigDetected = computed(() => {
      if (!currentConfig.value || !detectedConfig.value) return false;
      return currentConfig.value.backend_url === detectedConfig.value.backend_url;
    });

    // Save configuration
    const saveConfiguration = async () => {
      saving.value = true;
      connectionTest.value = null;
      
      try {
        const configData = {
          backend_url: configForm.backend_url,
          frontend_url: configForm.frontend_url || undefined,
          description: configForm.description || 'Frontend backend URL configuration'
        };
        
        const response = await http.post('/frontend-config', configData);
        
        // Update current config - parse the JSON response properly
        let backendUrl = response.data.config.value;
        let frontendUrl = configForm.frontend_url || undefined;

        // Check if the backend URL is a JSON string (new format)
        try {
          const parsedConfig = JSON.parse(backendUrl);
          backendUrl = parsedConfig.backend_url;
          frontendUrl = parsedConfig.frontend_url || frontendUrl;
        } catch (e) {
          // Not JSON, use as-is (old format)
        }

        currentConfig.value = {
          backend_url: backendUrl,
          frontend_url: frontendUrl,
          description: response.data.config.description,
          is_default: false
        };

        // Apply to the running app immediately (no reload)
        await http.setBackendUrlOverride(backendUrl);
        
        // Emit event to parent
        emit('config-updated', currentConfig.value);
        
      } catch (error) {
        console.error('Failed to save configuration:', error);
        connectionTest.value = {
          success: false,
          error: 'Failed to save configuration'
        };
      } finally {
        saving.value = false;
      }
    };

    // Reset to defaults
    const resetToDefaults = async () => {
      if (!confirm(t('settings.confirmReset', 'Are you sure you want to reset to default configuration?'))) {
        return;
      }
      
      saving.value = true;
      
      try {
        // Remove any persistent override so the app returns to normal detection/default logic
        await http.clearBackendUrlOverride();

        // Update form to default values
        configForm.backend_url = defaultBackendUrl;
        configForm.frontend_url = defaultFrontendUrl;
        configForm.description = '';
        
        // Clear current config to trigger default loading
        currentConfig.value = null;
        
        // Reload to get default configuration
        await loadCurrentConfiguration();
        
        emit('config-updated', currentConfig.value);
        
      } catch (error) {
        console.error('Failed to reset to defaults:', error);
      } finally {
        saving.value = false;
      }
    };

    // Test connection
    const testConnection = async () => {
      testing.value = true;
      connectionTest.value = null;
      
      try {
        // Try to connect to the backend
        const testUrl = configForm.backend_url.replace(/\/$/, '') + '/settings/read';
        
        const response = await http.get(testUrl, { timeout: 5000 });
        
        connectionTest.value = {
          success: true,
          message: `Successfully connected to ${configForm.backend_url}`
        };
        
      } catch (error: any) {
        let errorMessage = 'Connection failed';
        
        if (error.code === 'ECONNREFUSED') {
          errorMessage = 'Connection refused - is the backend server running?';
        } else if (error.code === 'NETWORK_ERROR') {
          errorMessage = 'Network error - check the URL and firewall settings';
        } else if (error.response?.status === 404) {
          errorMessage = 'Backend server is running but endpoint not found';
        } else if (error.response?.status >= 500) {
          errorMessage = 'Backend server error (status ' + error.response.status + ')';
        }
        
        connectionTest.value = {
          success: false,
          error: errorMessage
        };
      } finally {
        testing.value = false;
      }
    };

    onMounted(() => {
      loadCurrentConfiguration();
    });

    return {
      // State
      saving,
      detecting,
      applying,
      testing,
      currentConfig,
      detectedConfig,
      connectionTest,
      configForm,

      // Config defaults
      defaultBackendUrl,
      defaultFrontendUrl,

      // Computed
      isCurrentConfigDetected,

      // Methods
      detectConfiguration,
      applyDetectedConfiguration,
      saveConfiguration,
      resetToDefaults,
      testConnection,

      // i18n
      t
    };
  }
});
</script>

<style scoped>
.settings-section {
  background: var(--card-bg, #ffffff);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.section-header {
  margin-bottom: 1.5rem;
}

.section-title {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
  font-size: 1.25rem;
  font-weight: 600;
}

.section-description {
  margin: 0;
  color: var(--text-secondary, #666666);
  font-size: 0.9rem;
}

.network-config-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.auto-detect-section,
.manual-config-section {
  padding: 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
}

.auto-detect-section h4,
.manual-config-section h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-primary, #222222);
  font-size: 1.1rem;
}

.detected-info {
  background: var(--panel-bg, #f8f9fa);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  padding: 1rem;
  margin: 1rem 0;
}

.info-row {
  display: flex;
  align-items: center;
  margin-bottom: 0.5rem;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row strong {
  margin-right: 0.5rem;
  min-width: 120px;
}

.info-row code {
  background: var(--content-bg, #f8f9fa);
  padding: 0.2rem 0.4rem;
  border-radius: 3px;
  font-size: 0.85rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-label {
  display: block;
  margin-bottom: 0.25rem;
  font-weight: 500;
  color: var(--text-primary, #222222);
}

.form-label .required {
  color: #dc3545;
  margin-left: 0.2rem;
}

.form-control {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--input-bg, #ffffff);
  color: var(--text-primary, #222222);
  font-size: 0.9rem;
}

.form-control:focus {
  outline: none;
  border-color: var(--button-primary-bg, #007bff);
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.form-text {
  font-size: 0.8rem;
  color: var(--text-muted, #999999);
  margin-top: 0.25rem;
}

.current-config {
  background: var(--panel-bg, #f8f9fa);
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  padding: 1rem;
  margin: 1rem 0;
}

.current-config h5 {
  margin: 0 0 1rem 0;
  color: var(--text-primary, #222222);
  font-size: 1rem;
}

.config-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.config-item strong {
  min-width: 100px;
  font-size: 0.9rem;
}

.config-item code {
  background: var(--content-bg, #f8f9fa);
  padding: 0.2rem 0.4rem;
  border-radius: 3px;
  font-size: 0.85rem;
  flex: 1;
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
  margin-top: 1.5rem;
  flex-wrap: wrap;
}

.btn {
  padding: 0.5rem 1rem;
  border: 1px solid transparent;
  border-radius: var(--border-radius-sm, 4px);
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s ease-in-out;
  display: inline-flex;
  align-items: center;
}

.btn-primary {
  background: var(--button-primary-bg, #007bff);
  border-color: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.btn-primary:hover {
  background: var(--button-primary-hover, #0056b3);
  border-color: var(--button-primary-hover, #0056b3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-outline-primary {
  background: transparent;
  border-color: var(--button-primary-bg, #007bff);
  color: var(--button-primary-bg, #007bff);
}

.btn-outline-primary:hover {
  background: var(--button-primary-bg, #007bff);
  color: var(--button-primary-text, #ffffff);
}

.btn-outline-secondary {
  background: transparent;
  border-color: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-bg, #6c757d);
}

.btn-outline-secondary:hover {
  background: var(--button-secondary-bg, #6c757d);
  color: var(--button-secondary-text, #ffffff);
}

.btn-outline-info {
  background: transparent;
  border-color: #17a2b8;
  color: #17a2b8;
}

.btn-outline-info:hover {
  background: #17a2b8;
  color: #ffffff;
}

.connection-test-result {
  margin-top: 1rem;
  padding: 1rem;
  border-radius: var(--border-radius-sm, 4px);
}

.alert {
  padding: 0.75rem;
  margin-bottom: 1rem;
  border: 1px solid transparent;
  border-radius: var(--border-radius-sm, 4px);
}

.alert-success {
  color: #155724;
  background-color: #d4edda;
  border-color: #c3e6cb;
}

.alert-danger {
  color: #721c24;
  background-color: #f8d7da;
  border-color: #f5c6cb;
}

.text-muted {
  color: var(--text-muted, #999999);
  font-size: 0.9rem;
}

.badge {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 0.25rem;
}

.bg-secondary {
  background-color: #6c757d !important;
  color: #ffffff;
}

.spinner-border {
  width: 1rem;
  height: 1rem;
}

.spinner-border-sm {
  width: 0.75rem;
  height: 0.75rem;
}

/* Dark theme adjustments */
:root[data-theme="dark"] .settings-section,
.dark .settings-section {
  background: var(--card-bg, #374151);
  border-color: var(--card-border, #4b5563);
}

:root[data-theme="dark"] .section-title,
.dark .section-title {
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .section-description,
.dark .section-description {
  color: var(--text-secondary, #9ca3af);
}

:root[data-theme="dark"] .auto-detect-section,
.dark .auto-detect-section,
:root[data-theme="dark"] .manual-config-section,
.dark .manual-config-section {
  border-color: var(--card-border, #4b5563);
}

:root[data-theme="dark"] .auto-detect-section h4,
.dark .auto-detect-section h4,
:root[data-theme="dark"] .manual-config-section h4,
.dark .manual-config-section h4 {
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .detected-info,
.dark .detected-info,
:root[data-theme="dark"] .current-config,
.dark .current-config {
  background: var(--panel-bg, #374151);
  border-color: var(--card-border, #4b5563);
}

:root[data-theme="dark"] .form-control,
.dark .form-control {
  background: var(--input-bg, #374151);
  border-color: var(--input-border, #4b5563);
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .form-label,
.dark .form-label {
  color: var(--text-primary, #e5e7eb);
}

:root[data-theme="dark"] .form-text,
.dark .form-text {
  color: var(--text-muted, #6b7280);
}

:root[data-theme="dark"] .config-item code,
.dark .config-item code,
:root[data-theme="dark"] .info-row code,
.dark .info-row code {
  background: var(--panel-bg, #374151);
  color: var(--text-primary, #e5e7eb);
}
</style>
