<template>
  <div class="settings-section">
    <div class="section-header">
      <h3 class="section-title">{{ t('settings.networkConfiguration', 'Network Configuration') }}</h3>
      <p class="section-description">
        {{ t('settings.networkDescription', 'Configure how the frontend connects to the backend server. This is useful when deploying to different environments or using external IP addresses.') }}
      </p>
    </div>

    <div class="network-config-container">
      <section class="device-recovery-section" aria-labelledby="device-recovery-title">
        <div class="recovery-heading">
          <div class="recovery-icon" aria-hidden="true"><i class="bi bi-wifi"></i></div>
          <div>
            <h4 id="device-recovery-title">
              {{ t('networkRecovery.title', 'Device network recovery') }}
            </h4>
            <p>
              {{ t('networkRecovery.description', 'Move this device to another Wi-Fi network or recover access when its local network is unavailable.') }}
            </p>
          </div>
        </div>

        <div v-if="recoveryStatus" class="link-status" :data-state="recoveryStatus.local_link_state">
          <span class="status-dot" aria-hidden="true"></span>
          {{ recoveryLinkLabel }}
        </div>

        <div v-if="recoveryStatus" class="local-access-card">
          <div>
            <strong>{{ t('networkRecovery.localAddressTitle', 'Local device address') }}</strong>
            <a
              class="local-access-link"
              :href="recoveryStatus.local_url"
              target="_blank"
              rel="noopener noreferrer"
            >{{ recoveryStatus.local_url }}</a>
            <small>
              {{ t('networkRecovery.localAddressHelp', 'Available on this local network through the device hostname. Port 8080 remains supported.') }}
            </small>
          </div>
          <button type="button" class="btn btn-outline-primary" @click="useLocalHostname">
            {{ t('networkRecovery.useLocalAddress', 'Use this hostname') }}
          </button>
        </div>

        <label class="recovery-toggle">
          <input
            :checked="recoveryStatus?.automatic_setup_enabled ?? true"
            :disabled="loadingRecovery || savingRecovery || startingSetup"
            type="checkbox"
            @change="saveRecoveryPolicy"
          />
          <span>
            <strong>{{ t('networkRecovery.automaticTitle', 'Automatically start setup Wi-Fi after 5 minutes offline') }}</strong>
            <small>
              {{ t('networkRecovery.automaticHelp', 'Enabled by default. The timer runs only while both Wi-Fi and Ethernet are disconnected; Internet access is not tested.') }}
            </small>
          </span>
        </label>

        <div class="recovery-actions">
          <div>
            <strong>{{ t('networkRecovery.manualTitle', 'Configure another Wi-Fi network') }}</strong>
            <p>
              {{ t('networkRecovery.manualHelp', 'Starts the open setup network manually. This setting works even when automatic recovery is turned off.') }}
            </p>
          </div>
          <button
            type="button"
            class="btn btn-warning recovery-button"
            :disabled="loadingRecovery || savingRecovery || startingSetup || recoveryStatus?.setup_active"
            @click="startSetupMode"
          >
            <span v-if="startingSetup" class="spinner-border spinner-border-sm me-2"></span>
            {{ recoveryStatus?.setup_active
              ? t('networkRecovery.setupActive', 'Setup mode active')
              : t('networkRecovery.startSetup', 'Start setup Wi-Fi') }}
          </button>
        </div>

        <div v-if="recoveryMessage" class="recovery-notice" :class="{ error: recoveryError }" role="status">
          {{ recoveryMessage }}
        </div>
      </section>

      <hr>

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
          {{ t('settings.manualDescription', 'Configure the URLs used by the browser. A hostname may be entered with or without http://.') }}
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
              type="text"
              inputmode="url"
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
              type="text"
              inputmode="url"
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

interface NetworkRecoveryStatus {
  automatic_setup_enabled: boolean;
  offline_after_seconds: number;
  local_link_state: 'connected' | 'disconnected' | 'unknown';
  wifi_connected: boolean | null;
  ethernet_connected: boolean | null;
  setup_active: boolean;
  setup_network: string;
  setup_url: string;
  device_hostname: string;
  local_url: string;
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
    const loadingRecovery = ref(true);
    const savingRecovery = ref(false);
    const startingSetup = ref(false);
    
    const currentConfig = ref<ConfigResponse | null>(null);
    const detectedConfig = ref<DetectedConfig | null>(null);
    const connectionTest = ref<ConnectionTestResult | null>(null);
    const recoveryStatus = ref<NetworkRecoveryStatus | null>(null);
    const recoveryMessage = ref('');
    const recoveryError = ref(false);
    
    const configForm = reactive<ConfigForm>({
      backend_url: '',
      frontend_url: '',
      description: ''
    });

    const recoveryLinkLabel = computed(() => {
      if (!recoveryStatus.value || recoveryStatus.value.local_link_state === 'unknown') {
        return t('networkRecovery.linkUnknown', 'Local link status unavailable');
      }
      if (recoveryStatus.value.local_link_state === 'disconnected') {
        return t('networkRecovery.linkDisconnected', 'Wi-Fi and Ethernet disconnected');
      }
      if (recoveryStatus.value.wifi_connected && recoveryStatus.value.ethernet_connected) {
        return t('networkRecovery.linkBoth', 'Wi-Fi and Ethernet connected');
      }
      return recoveryStatus.value.wifi_connected
        ? t('networkRecovery.linkWifi', 'Wi-Fi connected')
        : t('networkRecovery.linkEthernet', 'Ethernet connected');
    });

    const normalizeServiceUrl = (value: string, defaultPort?: string) => {
      const trimmed = value.trim();
      if (!trimmed) return '';
      const candidate = /^[a-z][a-z\d+.-]*:\/\//i.test(trimmed)
        ? trimmed
        : `http://${trimmed}`;
      const parsed = new URL(candidate);
      if (defaultPort && !parsed.port) parsed.port = defaultPort;
      return parsed.toString().replace(/\/$/, '');
    };

    const useLocalHostname = () => {
      if (!recoveryStatus.value) return;
      const localHost = `${recoveryStatus.value.device_hostname}.local`;
      configForm.backend_url = `http://${localHost}:8887`;
      configForm.frontend_url = recoveryStatus.value.local_url;
      connectionTest.value = null;
    };

    const loadRecoveryStatus = async () => {
      loadingRecovery.value = true;
      try {
        const response = await http.get('/api/v1/network-recovery/status');
        recoveryStatus.value = response.data;
        recoveryError.value = false;
      } catch (error) {
        console.error('Failed to load network recovery status:', error);
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.loadFailed', 'Network recovery settings could not be loaded.');
      } finally {
        loadingRecovery.value = false;
      }
    };

    const saveRecoveryPolicy = async (event: Event) => {
      const enabled = (event.target as HTMLInputElement).checked;
      savingRecovery.value = true;
      recoveryMessage.value = '';
      try {
        const response = await http.put('/api/v1/network-recovery/policy', {
          automatic_setup_enabled: enabled
        });
        recoveryStatus.value = response.data;
        recoveryError.value = false;
        recoveryMessage.value = enabled
          ? t('networkRecovery.enabled', 'Automatic network recovery is enabled.')
          : t('networkRecovery.disabled', 'Automatic network recovery is disabled. Manual setup remains available.');
      } catch (error) {
        console.error('Failed to save network recovery policy:', error);
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.saveFailed', 'The recovery setting could not be saved.');
        await loadRecoveryStatus();
      } finally {
        savingRecovery.value = false;
      }
    };

    const startSetupMode = async () => {
      const confirmed = window.confirm(t(
        'networkRecovery.confirmStart',
        'Start setup Wi-Fi now? This application will disconnect. Connect your phone to the open 3mm Setup network to continue.'
      ));
      if (!confirmed) return;
      startingSetup.value = true;
      recoveryMessage.value = '';
      try {
        const response = await http.post('/api/v1/network-recovery/setup', {
          confirmation: 'START SETUP'
        });
        recoveryError.value = false;
        recoveryMessage.value = t(
          'networkRecovery.queued',
          'Setup is starting. Connect to {network} and open {url}.',
          {
            network: response.data.setup_network,
            url: response.data.setup_url
          }
        );
      } catch (error) {
        console.error('Failed to start setup mode:', error);
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.startFailed', 'Setup Wi-Fi could not be started.');
        startingSetup.value = false;
      }
    };

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
        const backendUrlInput = normalizeServiceUrl(configForm.backend_url, '8887');
        const frontendUrlInput = normalizeServiceUrl(configForm.frontend_url);
        configForm.backend_url = backendUrlInput;
        configForm.frontend_url = frontendUrlInput;
        const configData = {
          backend_url: backendUrlInput,
          frontend_url: frontendUrlInput || undefined,
          description: configForm.description || 'Frontend backend URL configuration'
        };
        
        const response = await http.post('/frontend-config', configData);
        
        // Update current config - parse the JSON response properly
        let backendUrl = response.data.config.value;
        let frontendUrl = frontendUrlInput || undefined;

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
        // Remove the saved backend URL configuration first so the app can fall back to defaults.
        await http.delete('/frontend-config');

        // Remove any persistent override so the app returns to normal detection/default logic
        await http.clearBackendUrlOverride();

        // Update form to default values
        configForm.backend_url = defaultBackendUrl;
        configForm.frontend_url = defaultFrontendUrl;
        configForm.description = '';
        
        // Clear current config to trigger default loading
        currentConfig.value = null;
        
        // Reload to get default configuration from the server
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
        configForm.backend_url = normalizeServiceUrl(configForm.backend_url, '8887');
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
      loadRecoveryStatus();
    });

    return {
      // State
      saving,
      detecting,
      applying,
      testing,
      loadingRecovery,
      savingRecovery,
      startingSetup,
      currentConfig,
      detectedConfig,
      connectionTest,
      configForm,
      recoveryStatus,
      recoveryMessage,
      recoveryError,

      // Config defaults
      defaultBackendUrl,
      defaultFrontendUrl,

      // Computed
      isCurrentConfigDetected,
      recoveryLinkLabel,

      // Methods
      detectConfiguration,
      applyDetectedConfiguration,
      saveConfiguration,
      resetToDefaults,
      testConnection,
      saveRecoveryPolicy,
      startSetupMode,
      useLocalHostname,

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
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
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
  min-width: 0;
  max-width: 100%;
}

.device-recovery-section {
  display: grid;
  gap: 1rem;
  padding: 1.1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--panel-bg, #f8f9fa);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.recovery-heading {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  min-width: 0;
}

.recovery-heading > div:last-child,
.recovery-actions > div,
.recovery-toggle span {
  min-width: 0;
}

.recovery-heading h4,
.recovery-actions strong {
  color: var(--text-primary, #222222);
}

.recovery-heading h4 {
  margin: 0 0 0.25rem;
  font-size: 1.05rem;
}

.recovery-heading p,
.recovery-actions p {
  margin: 0;
  color: var(--text-secondary, #666666);
  font-size: 0.88rem;
}

.recovery-icon {
  display: grid;
  flex: 0 0 2.25rem;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border-radius: 0.65rem;
  color: var(--button-primary-bg, #2563eb);
  background: color-mix(in srgb, var(--button-primary-bg, #2563eb) 12%, transparent);
}

.link-status {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  width: fit-content;
  color: var(--text-secondary, #666666);
  font-size: 0.85rem;
}

.status-dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: #94a3b8;
}

.link-status[data-state="connected"] .status-dot {
  background: #16a34a;
}

.link-status[data-state="disconnected"] .status-dot {
  background: #dc2626;
}

.local-access-card {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding: 0.9rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--card-bg, #ffffff);
}

.local-access-card > div {
  display: grid;
  gap: 0.25rem;
  min-width: 0;
}

.local-access-link {
  color: var(--button-primary-bg, #2563eb);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}

.local-access-card small {
  color: var(--text-secondary, #666666);
  line-height: 1.4;
}

.recovery-toggle {
  display: flex;
  gap: 0.8rem;
  align-items: flex-start;
  padding: 0.9rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--card-bg, #ffffff);
  cursor: pointer;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.recovery-toggle input {
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.1rem;
  accent-color: var(--button-primary-bg, #2563eb);
}

.recovery-toggle span {
  display: grid;
  gap: 0.25rem;
}

.recovery-toggle strong {
  color: var(--text-primary, #222222);
  font-size: 0.92rem;
}

.recovery-toggle small {
  color: var(--text-secondary, #666666);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.recovery-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
}

.recovery-button {
  flex: 0 0 auto;
}

.btn-warning {
  border-color: #d97706;
  color: #ffffff;
  background: #d97706;
}

.btn-warning:hover:not(:disabled) {
  border-color: #b45309;
  background: #b45309;
}

.recovery-notice {
  padding: 0.75rem 0.85rem;
  border: 1px solid color-mix(in srgb, #16a34a 35%, transparent);
  border-radius: var(--border-radius-sm, 4px);
  color: #166534;
  background: color-mix(in srgb, #16a34a 10%, transparent);
  font-size: 0.86rem;
}

.recovery-notice.error {
  border-color: color-mix(in srgb, #dc2626 35%, transparent);
  color: #991b1b;
  background: color-mix(in srgb, #dc2626 10%, transparent);
}

.auto-detect-section,
.manual-config-section {
  padding: 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-sm, 4px);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
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
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
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
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
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
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
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

:root[data-theme="dark"] .device-recovery-section,
.dark .device-recovery-section {
  background: var(--panel-bg, #1f2937);
  border-color: var(--card-border, #4b5563);
}

:root[data-theme="dark"] .recovery-toggle,
.dark .recovery-toggle,
:root[data-theme="dark"] .local-access-card,
.dark .local-access-card {
  background: var(--card-bg, #111827);
  border-color: var(--card-border, #4b5563);
}

:root[data-theme="dark"] .recovery-notice,
.dark .recovery-notice {
  color: #86efac;
}

:root[data-theme="dark"] .recovery-notice.error,
.dark .recovery-notice.error {
  color: #fca5a5;
}

@media (max-width: 640px) {
  .settings-section {
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .section-header {
    margin-bottom: 1rem;
  }

  .network-config-container {
    gap: 1rem;
  }

  .device-recovery-section,
  .auto-detect-section,
  .manual-config-section {
    padding: 0.85rem;
  }

  .recovery-heading {
    gap: 0.7rem;
  }

  .recovery-toggle {
    gap: 0.65rem;
    padding: 0.75rem;
  }

  .recovery-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .local-access-card {
    align-items: stretch;
    flex-direction: column;
  }

  .local-access-card .btn {
    justify-content: center;
    width: 100%;
  }

  .recovery-button {
    justify-content: center;
    width: 100%;
  }

  .info-row,
  .config-item {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.25rem;
  }

  .info-row strong,
  .config-item strong {
    min-width: 0;
  }

  .auto-detect-section > .btn,
  .action-buttons .btn {
    justify-content: center;
    width: 100%;
  }

  .auto-detect-section > .btn.ms-2 {
    margin-top: 0.5rem;
    margin-left: 0 !important;
  }
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
