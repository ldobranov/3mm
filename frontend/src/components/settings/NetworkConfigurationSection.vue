<template>
  <SettingsSection class="settings-section" :title="t('settings.networkConfiguration', 'Network Configuration')">
    <div class="section-header">
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
          <button type="button" class="ui-button" @click="useLocalHostname">
            {{ t('networkRecovery.useLocalAddress', 'Use this hostname') }}
          </button>
        </div>

        <label class="recovery-toggle ui-check">
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
            class="ui-button ui-button--primary recovery-button"
            :disabled="loadingRecovery || savingRecovery || startingSetup || recoveryStatus?.setup_active"
            @click="startSetupMode"
          >
            <span v-if="startingSetup" class="ui-spinner" aria-hidden="true"></span>
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
        <p class="network-help">
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
          class="ui-button"
        >
          <span v-if="detecting" class="ui-spinner" aria-hidden="true"></span>
          {{ t('settings.detectConfiguration', 'Detect Configuration') }}
        </button>

        <button 
          v-if="detectedConfig && !isCurrentConfigDetected"
          @click="applyDetectedConfiguration" 
          :disabled="applying"
          class="ui-button ui-button--primary detect-apply"
        >
          <span v-if="applying" class="ui-spinner" aria-hidden="true"></span>
          {{ t('settings.applyDetected', 'Apply Detected Configuration') }}
        </button>
      </div>

      <hr>

      <!-- Manual configuration section -->
      <div class="manual-config-section">
        <h4>{{ t('settings.manualConfiguration', 'Manual Configuration') }}</h4>
        <p class="network-help">
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
              class="ui-control"
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
              class="ui-control"
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
              class="ui-control"
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
                <span v-if="currentConfig.is_default" class="ui-badge">{{ t('settings.default', 'Default') }}</span>
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
              class="ui-button ui-button--primary"
            >
              <span v-if="saving" class="ui-spinner" aria-hidden="true"></span>
              {{ t('settings.saveConfiguration', 'Save Configuration') }}
            </button>

            <button 
              type="button"
              @click="resetToDefaults"
              :disabled="saving"
              class="ui-button"
            >
              {{ t('settings.resetToDefaults', 'Reset to Defaults') }}
            </button>

            <button 
              type="button"
              @click="testConnection"
              :disabled="saving || testing || !configForm.backend_url"
              class="ui-button"
            >
              <span v-if="testing" class="ui-spinner" aria-hidden="true"></span>
              {{ t('settings.testConnection', 'Test Connection') }}
            </button>
          </div>
        </form>
      </div>

      <!-- Connection test result -->
      <div v-if="connectionTest" class="connection-test-result" :class="connectionTest.success ? 'result-success' : 'result-error'" role="status">
        <strong>{{ connectionTest.success ? t('settings.connectionSuccessful', 'Connection Successful!') : t('settings.connectionFailed', 'Connection Failed!') }}</strong>
        <p v-if="connectionTest.message" >{{ connectionTest.message }}</p>
        <p v-if="connectionTest.error" >{{ connectionTest.error }}</p>
      </div>
    </div>
  </SettingsSection>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, computed } from 'vue';
import http from '@/utils/dynamic-http';
import { useI18n } from '@/utils/i18n';
import SettingsSection from '@/components/SettingsSection.vue';

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
  components: { SettingsSection },
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
.section-header { margin-bottom: calc(var(--ui-space) * 5); }
.section-description, .network-help, .recovery-heading p, .recovery-actions p, .local-access-card small, .recovery-toggle small { color: var(--ui-text-secondary); font-size: .9em; }
.network-config-container { display: grid; gap: calc(var(--ui-space) * 5); min-width: 0; }
.network-config-container hr { display: none; }
.device-recovery-section, .auto-detect-section, .manual-config-section { display: grid; gap: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); min-width: 0; }
.device-recovery-section { background: var(--ui-surface-alt); }
.recovery-heading { display: flex; gap: calc(var(--ui-space) * 3); align-items: flex-start; }
.recovery-heading > div:last-child, .recovery-actions > div, .recovery-toggle span { min-width: 0; }
.recovery-heading h4, .auto-detect-section h4, .manual-config-section h4 { margin: 0; font-size: 1rem; color: var(--ui-text); }
.recovery-icon { display: grid; flex: 0 0 2.25rem; height: 2.25rem; place-items: center; border-radius: var(--ui-radius-sm); color: var(--ui-accent); background: var(--ui-surface); }
.link-status { display: flex; align-items: center; gap: calc(var(--ui-space) * 2); color: var(--ui-text-secondary); font-size: .9em; }
.status-dot { flex: 0 0 .6rem; height: .6rem; border-radius: 50%; background: var(--ui-text-muted); }
.link-status[data-state="connected"] .status-dot { background: var(--ui-success); }
.link-status[data-state="disconnected"] .status-dot { background: var(--ui-danger); }
.local-access-card, .recovery-toggle { padding: calc(var(--ui-space) * 4); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface); }
.local-access-card, .recovery-actions { display: flex; align-items: center; justify-content: space-between; gap: calc(var(--ui-space) * 4); }
.local-access-card > div, .recovery-toggle span { display: grid; gap: var(--ui-space); min-width: 0; }
.local-access-link { overflow-wrap: anywhere; font-family: ui-monospace, monospace; }
.recovery-toggle { margin: 0; }
.recovery-notice, .connection-test-result { padding: calc(var(--ui-space) * 3); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; }
.recovery-notice { color: var(--ui-success); }
.recovery-notice.error, .result-error { color: var(--ui-danger); }
.result-success { color: var(--ui-success); }
.detect-apply { justify-self: start; }
.auto-detect-section > .ui-button { justify-self: start; }
.detected-info, .current-config { padding: calc(var(--ui-space) * 4); background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); display: grid; gap: calc(var(--ui-space) * 3); }
.current-config h5 { margin: 0; font-size: 1rem; }
.info-row, .config-item { display: flex; align-items: baseline; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); min-width: 0; }
.info-row strong, .config-item strong { flex: 0 0 auto; }
.info-row code, .config-item code { color: var(--ui-text-secondary); min-width: 0; overflow-wrap: anywhere; }
.config-details, .manual-config-section form { display: grid; gap: calc(var(--ui-space) * 4); min-width: 0; }
.form-group { display: grid; gap: calc(var(--ui-space) * 2); margin: 0; min-width: 0; }
.form-label { margin: 0; color: var(--ui-text); }
.required { color: var(--ui-danger); }
.form-text { margin: 0; font-size: .85em; color: var(--ui-text-muted); }
.action-buttons { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
@media (max-width: 720px) {
  .local-access-card, .recovery-actions { flex-direction: column; align-items: stretch; }
  .info-row, .config-item { align-items: flex-start; flex-direction: column; }
  .auto-detect-section > .ui-button, .action-buttons .ui-button { width: 100%; }
}
</style>
