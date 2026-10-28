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
              {{ t('networkRecovery.description', 'Keep local services running while recovering device access.') }}
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

        <label v-if="recoveryStatus?.automatic_setup_available" class="recovery-toggle ui-check">
          <input
            :checked="recoveryStatus?.automatic_setup_enabled ?? true"
            :disabled="loadingRecovery || savingRecovery || startingSetup || !recoveryStatus?.automatic_setup_available"
            type="checkbox"
            @change="saveRecoveryPolicy"
          />
          <span>
            <strong>{{ t('networkRecovery.automaticTitle', 'Open local recovery after 5 minutes without a network link') }}</strong>
            <small>
              {{ t('networkRecovery.automaticHelp', 'Available when 3mm manages networking. The timer checks local links, not Internet access. Host-managed networking remains under OS control.') }}
            </small>
          </span>
        </label>
        <p v-else-if="recoveryStatus" class="automatic-recovery-unavailable" role="status">
          {{ t('networkRecovery.automaticUnavailable', 'Automatic recovery is off for this network choice. The operating system manages this connection; setup remains available manually.') }}
        </p>

        <div class="recovery-actions">
          <div>
            <strong>{{ t('networkRecovery.manualTitle', 'Device setup') }}</strong>
            <p>
              {{ t('networkRecovery.manualHelp', 'Opens setup on the local network while recovery is active. Existing services keep running.') }}
            </p>
          </div>
          <button
            type="button"
            class="ui-button ui-button--primary recovery-button"
            :disabled="loadingRecovery || savingRecovery || startingSetup"
            @click="startSetupMode"
          >
            <span v-if="startingSetup" class="ui-spinner" aria-hidden="true"></span>
            {{ recoveryStatus?.setup_active
              ? t('networkRecovery.setupActive', 'Local recovery active')
              : t('networkRecovery.startSetup', 'Open local recovery') }}
          </button>
        </div>

        <div class="temporary-ap" v-if="apInterfaces.length || apBusy || recoveryStatus?.access_point?.state === 'failed'">
          <h4>{{ t('networkRecovery.ap.title', 'Temporary Wi-Fi access point') }}</h4>
          <p>{{ t('networkRecovery.ap.help', 'Temporarily switches the selected Wi-Fi adapter to a setup AP. Core keeps running. The AP stops after 5 minutes and returns to the previous connection if it is available.') }}</p>
          <label v-if="apInterfaces.length > 1">
            {{ t('networkRecovery.ap.adapter', 'Wi-Fi adapter') }}
            <select class="ui-control" v-model="apInterface"><option value="">{{ t('networkRecovery.ap.select', 'Select an adapter') }}</option><option v-for="name in apInterfaces" :key="name" :value="name">{{ name }}</option></select>
          </label>
          <p v-if="apBusy">{{ t('networkRecovery.ap.active', 'Temporary AP is starting or active. Its independent timer will stop it automatically.') }}</p>
          <p v-if="recoveryStatus?.access_point?.state === 'failed'" role="alert">{{ t('networkRecovery.ap.unconfirmed', 'AP recovery was not confirmed. Check the current connection before trying again.') }}</p>
          <div class="recovery-actions">
            <button class="ui-button ui-button--primary ap-start" :disabled="startingSetup || startingAP || apBusy || !apInterface" @click="startAccessPoint">{{ t('networkRecovery.ap.start', 'Start temporary AP') }}</button>
            <button v-if="apBusy" class="ui-button ui-button--secondary ap-stop" :disabled="startingAP" @click="stopAccessPoint">{{ t('networkRecovery.ap.stop', 'Stop AP and return') }}</button>
          </div>
        </div>

        <div v-if="recoveryMessage" class="recovery-notice" :class="{ error: recoveryError }" role="status">
          {{ recoveryMessage }}
          <a v-if="recoveryAccessLink" :href="recoveryAccessLink" target="_blank" rel="noopener noreferrer">{{ t('networkRecovery.openSetup', 'Open setup') }}</a>
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
import { defineComponent, ref, reactive, onMounted, onUnmounted, computed } from 'vue';
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
  automatic_setup_available: boolean;
  offline_after_seconds: number;
  local_link_state: 'connected' | 'disconnected' | 'unknown';
  wifi_connected: boolean | null;
  ethernet_connected: boolean | null;
  setup_active: boolean;
  setup_network: string | null;
  setup_url: string;
  device_hostname: string;
  local_url: string;
  access_point: { state: string; id: string | null; interface: string | null; interfaces: string[]; expires_at: number | null; network: string | null };
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
    const startingAP = ref(false);
    const apInterface = ref('');
    const apInterfaces = computed(() => recoveryStatus.value?.access_point?.interfaces || []);
    const apBusy = computed(() => ['starting', 'active', 'restoring'].includes(recoveryStatus.value?.access_point?.state || ''));
    let recoveryPoll: ReturnType<typeof setInterval> | undefined;
    let disposed = false;
    
    const currentConfig = ref<ConfigResponse | null>(null);
    const detectedConfig = ref<DetectedConfig | null>(null);
    const connectionTest = ref<ConnectionTestResult | null>(null);
    const recoveryStatus = ref<NetworkRecoveryStatus | null>(null);
    const recoveryMessage = ref('');
    const recoveryAccessLink = ref('');
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
        if (disposed) return;
        recoveryStatus.value = response.data;
        if (!apInterface.value && response.data.access_point?.interfaces?.length === 1) apInterface.value = response.data.access_point.interfaces[0];
        recoveryError.value = false;
      } catch (error) {
        if (apBusy.value) return; // Keep AP join instructions while its radio link changes.
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
        'Open device setup? Existing services keep running.'
      ));
      if (!confirmed) return;
      startingSetup.value = true;
      recoveryMessage.value = '';
      try {
        const response = await http.post('/api/v1/network-recovery/setup', {
          confirmation: 'START SETUP'
        });
        recoveryError.value = false;
        const setupUrl = new URL(response.data.setup_url);
        recoveryAccessLink.value = setupUrl.toString();
        startingSetup.value = false;
        recoveryMessage.value = t(
          'networkRecovery.queued',
          'Setup is starting at {url}. Open the link below while recovery is active.',
          {
            url: response.data.setup_url
          }
        );
      } catch (error) {
        console.error('Failed to start setup mode:', error);
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.startFailed', 'Local recovery could not be started.');
        startingSetup.value = false;
      }
    };

    const startAccessPoint = async () => {
      if (!apInterface.value || !window.confirm(t('networkRecovery.ap.confirm', 'This switches Wi-Fi to a temporary AP and disconnects clients using that Wi-Fi connection. Join the setup AP from your phone. It stops after 5 minutes. Continue?'))) return;
      startingAP.value = true;
      recoveryMessage.value = '';
      try {
        const { data } = await http.post('/api/v1/network-recovery/access-point', {
          confirmation: 'START ACCESS POINT', interface: apInterface.value, duration_seconds: 300,
        });
        const url = new URL(data.setup_url);
        recoveryAccessLink.value = url.toString();
        recoveryMessage.value = t('networkRecovery.ap.join', 'Join “{network}”, then open the setup link below. Automatic return: 5 minutes.', { network: data.setup_network });
        recoveryError.value = false;
        if (recoveryStatus.value) recoveryStatus.value.access_point = { ...recoveryStatus.value.access_point, state: 'starting', id: data.id };
      } catch {
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.ap.failed', 'The AP request was not confirmed. Refresh device status before retrying.');
      } finally { startingAP.value = false; }
    };
    const stopAccessPoint = async () => {
      const id = recoveryStatus.value?.access_point?.id;
      if (!id) return;
      startingAP.value = true;
      try {
        await http.post('/api/v1/network-recovery/access-point/stop', { confirmation: 'STOP ACCESS POINT', id });
        recoveryMessage.value = t('networkRecovery.ap.stopping', 'AP return is queued. Reconnect to the original network.');
        recoveryError.value = false;
      } catch {
        recoveryError.value = true;
        recoveryMessage.value = t('networkRecovery.ap.failed', 'The AP request was not confirmed. Refresh device status before retrying.');
      } finally { startingAP.value = false; }
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
      recoveryPoll = setInterval(() => { if (apBusy.value && !startingAP.value && !startingSetup.value) loadRecoveryStatus(); }, 10000);
    });
    onUnmounted(() => { disposed = true; if (recoveryPoll) clearInterval(recoveryPoll); });

    return {
      // State
      saving,
      detecting,
      applying,
      testing,
      loadingRecovery,
      savingRecovery,
      startingSetup,
      startingAP, apInterface, apInterfaces, apBusy, startAccessPoint, stopAccessPoint,
      currentConfig,
      detectedConfig,
      connectionTest,
      configForm,
      recoveryStatus,
      recoveryMessage,
      recoveryAccessLink,
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
.temporary-ap { display: grid; gap: calc(var(--ui-space) * 3); padding-top: calc(var(--ui-space) * 4); border-top: 1px solid var(--ui-border); }
.temporary-ap h4 { margin: 0; font-size: 1rem; }
.temporary-ap p, .automatic-recovery-unavailable { margin: 0; color: var(--ui-text-secondary); font-size: .9em; }
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
