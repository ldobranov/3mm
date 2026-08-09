<template>
  <div class="main-server-extension">
    <div class="extension-header">
      <h1>{{ t('mainServer.title', 'Main Server Extension') }}</h1>
      <p>{{ t('mainServer.description', 'Manage and distribute updates to Raspberry Pi devices') }}</p>
    </div>

    <div class="extension-content">
      <!-- Dashboard Overview -->
      <div class="dashboard-overview">
        <h2>{{ t('mainServer.dashboard.overview', 'System Overview') }}</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ devices.length }}</div>
            <div class="stat-label">{{ t('mainServer.dashboard.totalDevices', 'Total Devices') }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ availableUpdates.length }}</div>
            <div class="stat-label">{{ t('mainServer.dashboard.pendingUpdates', 'Pending Updates') }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">-</div>
            <div class="stat-label">{{ t('mainServer.dashboard.lastUpdate', 'Last Update') }}</div>
          </div>
        </div>
      </div>

      <!-- Available Updates Section -->
      <div class="updates-section">
        <h2>{{ t('mainServer.updates.title', 'Available Updates') }}</h2>
        
        <div v-if="availableUpdates.length === 0" class="no-updates">
          <p>{{ t('mainServer.updates.none', 'No updates available') }}</p>
        </div>
        
        <div v-else class="updates-list">
          <div v-for="update in availableUpdates" :key="update.extension_id" class="update-item">
            <div class="update-info">
              <h3>{{ update.name }} v{{ update.available_version }}</h3>
              <p>{{ t('mainServer.updates.currentVersion', 'Current Version') }}: v{{ update.current_version }}</p>
              <p v-if="update.is_compatible" class="compatible">
                {{ t('mainServer.updates.compatible', 'Compatible') }}
              </p>
              <p v-else class="not-compatible">
                {{ t('mainServer.updates.notCompatible', 'Not Compatible') }}
              </p>
            </div>
            <div class="update-actions">
              <button @click="scheduleUpdate(update.extension_id, update.available_version)" class="btn-primary">
                {{ t('mainServer.updates.schedule', 'Schedule Update') }}
              </button>
              <button @click="deployUpdate(update.extension_id, update.available_version)" class="btn-secondary">
                {{ t('mainServer.updates.deploy', 'Deploy Update') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Connected Devices Section -->
      <div class="devices-section">
        <h2>{{ t('mainServer.devices.title', 'Connected Devices') }}</h2>
        
        <div v-if="isLoadingDevices" class="no-devices">
          <p>{{ t('mainServer.devices.loading', 'Loading devices...') }}</p>
        </div>

        <div v-else-if="devicesError" class="devices-error">
          <p>{{ t('mainServer.devices.loadError', 'Devices could not be loaded') }}</p>
          <button @click="loadDevices" class="btn-secondary">
            {{ t('mainServer.devices.retry', 'Retry') }}
          </button>
        </div>

        <div v-else-if="devices.length === 0" class="no-devices">
          <p>{{ t('mainServer.devices.none', 'No devices connected') }}</p>
        </div>
        
        <div v-else class="devices-list">
          <table class="devices-table">
            <thead>
              <tr>
                <th>{{ t('mainServer.devices.deviceName', 'Device Name') }}</th>
                <th>{{ t('mainServer.devices.deviceId', 'Device ID') }}</th>
                <th>{{ t('mainServer.devices.role', 'Role') }}</th>
                <th>{{ t('mainServer.devices.hardware', 'Hardware') }}</th>
                <th>{{ t('mainServer.devices.deviceStatus', 'Status') }}</th>
                <th>{{ t('mainServer.devices.lastSeen', 'Last seen') }}</th>
                <th>{{ t('mainServer.state.status', 'State') }}</th>
                <th>{{ t('mainServer.state.revisions', 'Revisions') }}</th>
                <th>{{ t('mainServer.devices.actions', 'Actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="device in devices" :key="device.device_id">
                <td>{{ device.display_name || device.latest_inventory?.hostname || device.device_id }}</td>
                <td><code>{{ device.device_id }}</code></td>
                <td>{{ device.role }}</td>
                <td>{{ device.latest_inventory?.model || device.latest_inventory?.architecture || '-' }}</td>
                <td>
                  <span :class="['status-badge', device.online ? 'online' : 'offline']">
                    {{ device.online
                       ? t('mainServer.devices.online', 'Online') 
                       : t('mainServer.devices.offline', 'Offline') }}
                  </span>
                </td>
                <td>{{ formatTimestamp(device.last_seen_at) }}</td>
                <td>
                  <span
                    v-if="deviceStates[device.device_id]"
                    :class="['status-badge', deviceStates[device.device_id].synchronized ? 'succeeded' : 'failed']"
                  >
                    {{ deviceStates[device.device_id].synchronized
                      ? t('mainServer.state.synchronized', 'Synchronized')
                      : t('mainServer.state.drifted', 'Drifted') }}
                  </span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="deviceStates[device.device_id]">
                    {{ deviceStates[device.device_id].reported_revision }} / {{ deviceStates[device.device_id].desired.revision }}
                  </span>
                  <span v-else>-</span>
                </td>
                <td>
                  <button
                    class="btn-small"
                    :disabled="queuedDeviceId === device.device_id"
                    @click="refreshInventory(device.device_id)"
                  >
                    {{ queuedDeviceId === device.device_id
                      ? t('mainServer.commands.queueing', 'Queueing...')
                      : t('mainServer.commands.refreshInventory', 'Refresh inventory') }}
                  </button>
                  <button class="btn-small" @click="selectedDiagnosticsDeviceId = device.device_id">
                    {{ t('mainServer.devices.details', 'Details') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="selectedDiagnosticsDevice" class="diagnostics-panel">
          <div class="section-title-row">
            <h3>{{ selectedDiagnosticsDevice.display_name || selectedDiagnosticsDevice.device_id }}</h3>
            <button class="btn-small" @click="selectedDiagnosticsDeviceId = ''">×</button>
          </div>
          <div class="diagnostics-grid">
            <section>
              <h4>{{ t('mainServer.diagnostics.inventory', 'Latest inventory') }}</h4>
              <pre>{{ prettyJson(selectedDiagnosticsDevice.latest_inventory) }}</pre>
            </section>
            <section>
              <h4>{{ t('mainServer.diagnostics.state', 'Desired / reported state') }}</h4>
              <pre>{{ prettyJson(deviceStates[selectedDiagnosticsDevice.device_id] || null) }}</pre>
            </section>
          </div>
          <h4>{{ t('mainServer.diagnostics.commands', 'Recent commands') }}</h4>
          <ul class="diagnostics-events">
            <li v-for="command in selectedDeviceCommands" :key="command.command_id">
              <strong>{{ command.status }}</strong> · {{ command.command_type }} · {{ formatTimestamp(command.created_at) }}
              <span v-if="command.error"> · {{ command.error }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="commands-section">
        <div class="section-title-row">
          <h2>{{ t('mainServer.commands.title', 'Command History') }}</h2>
          <button class="btn-secondary" @click="loadCommands">
            {{ t('mainServer.commands.reload', 'Reload') }}
          </button>
        </div>
        <p v-if="commandMessage" class="command-message">{{ commandMessage }}</p>
        <p v-if="commandsError" class="devices-error">
          {{ t('mainServer.commands.loadError', 'Command history could not be loaded') }}
        </p>
        <p v-else-if="commands.length === 0" class="no-devices">
          {{ t('mainServer.commands.none', 'No commands yet') }}
        </p>
        <div v-else class="devices-list">
          <table class="devices-table">
            <thead><tr>
              <th>{{ t('mainServer.commands.command', 'Command') }}</th>
              <th>{{ t('mainServer.devices.deviceName', 'Device') }}</th>
              <th>{{ t('mainServer.commands.status', 'Status') }}</th>
              <th>{{ t('mainServer.commands.attempts', 'Attempts') }}</th>
              <th>{{ t('mainServer.commands.created', 'Created') }}</th>
              <th>{{ t('mainServer.commands.result', 'Result') }}</th>
            </tr></thead>
            <tbody>
              <tr v-for="command in commands" :key="command.command_id">
                <td>{{ command.command_type }}</td>
                <td>{{ deviceName(command.device_id) }}</td>
                <td><span :class="['status-badge', command.status]">{{ command.status }}</span></td>
                <td>{{ command.delivery_attempts }}</td>
                <td>{{ formatTimestamp(command.created_at) }}</td>
                <td>{{ command.error || formatResult(command.result) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Deploy Dialog -->
      <div v-if="showDeployDialog" class="deploy-dialog">
        <div class="dialog-overlay" @click="closeDeployDialog"></div>
        <div class="dialog-content">
          <h3>{{ t('mainServer.devices.deployTo', 'Deploy to Device') }}</h3>
          
          <div class="form-group">
            <label>{{ t('mainServer.updates.title', 'Available Updates') }}</label>
            <select v-model="selectedExtensionId">
              <option value="null" disabled>{{ t('mainServer.updates.none', 'Select an update') }}</option>
              <option v-for="update in availableUpdates" :key="update.extension_id" :value="update.extension_id">
                {{ update.name }} (v{{ update.current_version }} → v{{ update.available_version }})
              </option>
            </select>
          </div>
          
          <div class="form-group">
            <label>{{ t('mainServer.updates.availableVersion', 'Version') }}</label>
            <input type="text" v-model="selectedVersion" readonly />
          </div>
          
          <div class="dialog-actions">
            <button @click="closeDeployDialog" class="btn-secondary">
              {{ t('cancel', 'Cancel') }}
            </button>
            <button @click="deployToDevice" class="btn-primary">
              {{ t('mainServer.devices.deployTo', 'Deploy to Device') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Settings Section -->
      <div class="settings-section">
        <h2>{{ t('mainServer.settings.title', 'Update Settings') }}</h2>
        <div class="settings-form">
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="settings.autoUpdate" />
              {{ t('mainServer.settings.autoUpdate', 'Auto Update') }}
            </label>
          </div>
          
          <div class="form-group">
            <label>{{ t('mainServer.settings.updateInterval', 'Update Interval') }}</label>
            <select v-model="settings.updateInterval">
              <option value="daily">{{ t('mainServer.settings.daily', 'Daily') }}</option>
              <option value="weekly">{{ t('mainServer.settings.weekly', 'Weekly') }}</option>
              <option value="monthly">{{ t('mainServer.settings.monthly', 'Monthly') }}</option>
              <option value="never">{{ t('mainServer.settings.never', 'Never') }}</option>
            </select>
          </div>
          
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="settings.notifyDevices" />
              {{ t('mainServer.settings.notifyDevices', 'Notify Devices') }}
            </label>
          </div>
          
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="settings.backupBeforeUpdate" />
              {{ t('mainServer.settings.backupBeforeUpdate', 'Backup Before Update') }}
            </label>
          </div>
          
          <button @click="saveSettings" class="btn-primary">
            {{ t('mainServer.settings.save', 'Save Settings') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// State
const availableUpdates = ref<any[]>([]);
interface DeviceInventory {
  hostname?: string;
  model?: string | null;
  architecture?: string;
}

interface RegistryDevice {
  device_id: string;
  display_name: string | null;
  role: string;
  protocol_version: string;
  approved_at: string;
  revoked_at: string | null;
  online: boolean;
  last_seen_at: string | null;
  latest_inventory: DeviceInventory | null;
}

interface DeviceRegistryResponse {
  items: RegistryDevice[];
  total: number;
}

interface DeviceCommand {
  command_id: string;
  device_id: string;
  command_type: string;
  status: string;
  delivery_attempts: number;
  created_at: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

interface DeviceStateSummary {
  desired: { revision: number; state: Record<string, unknown>; updated_at: string };
  reported_revision: number;
  reported_state: Record<string, unknown>;
  reported_at: string | null;
  synchronized: boolean;
}

const devices = ref<RegistryDevice[]>([]);
const isLoadingDevices = ref(false);
const devicesError = ref(false);
const commands = ref<DeviceCommand[]>([]);
const commandsError = ref(false);
const commandMessage = ref('');
const queuedDeviceId = ref('');
const deviceStates = ref<Record<string, DeviceStateSummary>>({});
const selectedDiagnosticsDeviceId = ref('');
const selectedDiagnosticsDevice = computed(() =>
  devices.value.find((device) => device.device_id === selectedDiagnosticsDeviceId.value) || null
);
const selectedDeviceCommands = computed(() =>
  commands.value.filter((command) => command.device_id === selectedDiagnosticsDeviceId.value).slice(0, 10)
);
const settings = ref({
  autoUpdate: false,
  updateInterval: 'daily',
  notifyDevices: true,
  backupBeforeUpdate: true
});

// Deploy dialog state
const showDeployDialog = ref(false);
const selectedDeviceId = ref('');
const selectedExtensionId = ref<number | null>(null);
const selectedVersion = ref('');

// Fetch data on mount
onMounted(async () => {
  loadAvailableUpdates();
  loadSettings();
  await loadDevices();
  await loadDeviceStates();
  await loadCommands();
});

// Load available updates
const loadAvailableUpdates = async () => {
  try {
    const response = await http.get('/api/main-server/updates');
    availableUpdates.value = response.data.updates || [];
  } catch (error) {
    console.error('Failed to load available updates:', error);
  }
};

const loadCommands = async () => {
  commandsError.value = false;
  try {
    const histories = await Promise.all(
      devices.value.map(async (device) => ({
        deviceId: device.device_id,
        response: await http.get(`/api/v1/devices/${device.device_id}/commands?limit=20`),
      }))
    );
    commands.value = histories
      .flatMap(({ deviceId, response }) =>
        (response.data.items as Omit<DeviceCommand, 'device_id'>[])
          .map((command) => ({ ...command, device_id: deviceId }))
      )
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  } catch (error) {
    console.error('Failed to load command history:', error);
    commandsError.value = true;
  }
};

const loadDeviceStates = async () => {
  const entries = await Promise.all(
    devices.value.map(async (device) => {
      try {
        const response = await http.get(`/api/v1/devices/${device.device_id}/state`);
        return [device.device_id, response.data as DeviceStateSummary] as const;
      } catch (error) {
        console.error(`Failed to load state for ${device.device_id}:`, error);
        return null;
      }
    })
  );
  deviceStates.value = Object.fromEntries(entries.filter((entry) => entry !== null));
};

const refreshInventory = async (deviceId: string) => {
  queuedDeviceId.value = deviceId;
  commandMessage.value = '';
  try {
    const randomBytes = crypto.getRandomValues(new Uint8Array(16));
    const randomId = Array.from(randomBytes, (value) => value.toString(16).padStart(2, '0')).join('');
    const idempotencyKey = `refresh-${deviceId}-${randomId}`;
    await http.post(`/api/v1/devices/${deviceId}/commands`, {
      command_type: 'agent.refresh_inventory',
      payload: {},
      idempotency_key: idempotencyKey,
      ttl_seconds: 300,
    });
    commandMessage.value = t('mainServer.commands.queued', 'Inventory refresh queued');
    await loadCommands();
  } catch (error) {
    console.error('Failed to queue inventory refresh:', error);
    commandMessage.value = t('mainServer.commands.queueError', 'Command could not be queued');
  } finally {
    queuedDeviceId.value = '';
  }
};

const deviceName = (deviceId: string) => {
  const device = devices.value.find((item) => item.device_id === deviceId);
  return device?.display_name || deviceId;
};

const formatResult = (result: Record<string, unknown> | null) => {
  if (!result) return '-';
  return Object.entries(result).map(([key, value]) => `${key}: ${String(value)}`).join(', ');
};

const prettyJson = (value: unknown) => value ? JSON.stringify(value, null, 2) : '-';

// Load connected devices
const loadDevices = async () => {
  isLoadingDevices.value = true;
  devicesError.value = false;
  try {
    const response = await http.get('/api/v1/devices');
    const registry = response.data as DeviceRegistryResponse;
    devices.value = registry.items;
  } catch (error) {
    console.error('Failed to load devices:', error);
    devices.value = [];
    devicesError.value = true;
  } finally {
    isLoadingDevices.value = false;
  }
};

const formatTimestamp = (value: string | null) => {
  if (!value) {
    return t('mainServer.devices.neverSeen', 'Never');
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'medium'
  }).format(new Date(value));
};

// Load settings
const loadSettings = async () => {
  try {
    const response = await http.get('/api/main-server/settings');
    if (response.data.settings) {
      settings.value = response.data.settings;
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
};

// Schedule update
const scheduleUpdate = async (extensionId: number, version: string) => {
  try {
    const response = await http.post('/api/main-server/schedule-update', {
      extension_id: extensionId,
      new_version: version
    });
    alert(t('mainServer.updates.schedule', 'Schedule Update') + ' ' + response.data.message);
  } catch (error) {
    console.error('Failed to schedule update:', error);
    alert('Failed to schedule update');
  }
};

// Deploy update
const deployUpdate = async (extensionId: number, version: string) => {
  try {
    const response = await http.post('/api/main-server/deploy-update', {
      extension_id: extensionId,
      version: version
    });
    alert(t('mainServer.updates.deploy', 'Deploy Update') + ' ' + response.data.message);
  } catch (error) {
    console.error('Failed to deploy update:', error);
    alert('Failed to deploy update');
  }
};

// Open deploy dialog
const openDeployDialog = (deviceId: string) => {
  selectedDeviceId.value = deviceId;
  showDeployDialog.value = true;
};

// Close deploy dialog
const closeDeployDialog = () => {
  showDeployDialog.value = false;
  selectedDeviceId.value = '';
  selectedExtensionId.value = null;
  selectedVersion.value = '';
};

// Deploy to specific device
const deployToDevice = async () => {
  if (!selectedExtensionId.value || !selectedVersion.value) {
    alert('Please select an extension and version');
    return;
  }
  
  try {
    const response = await http.post('/api/main-server/deploy-update', {
      device_id: selectedDeviceId.value,
      extension_id: selectedExtensionId.value,
      version: selectedVersion.value
    });
    alert(t('mainServer.devices.deployTo', 'Deploy to Device') + ' ' + response.data.message);
    closeDeployDialog();
  } catch (error) {
    console.error('Failed to deploy to device:', error);
    alert('Failed to deploy to device');
  }
};

// Save settings
const saveSettings = async () => {
  try {
    const response = await http.post('/api/main-server/settings', settings.value);
    alert(t('mainServer.settings.save', 'Save Settings') + ' ' + response.data.message);
  } catch (error) {
    console.error('Failed to save settings:', error);
    alert('Failed to save settings');
  }
};
</script>

<style scoped>
.main-server-extension {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.extension-header {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #eee;
}

.extension-header h1 {
  color: var(--text-primary);
  font-size: 1.8rem;
}

.extension-header p {
  color: var(--text-secondary);
}

.dashboard-overview {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--surface-1);
  border-radius: 8px;
}

.dashboard-overview h2 {
  margin-bottom: 1rem;
  color: var(--text-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.stat-card {
  padding: 1rem;
  background: var(--surface-2);
  border-radius: 6px;
  text-align: center;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: var(--primary-color);
}

.stat-label {
  margin-top: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.updates-section, .devices-section, .commands-section, .settings-section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--surface-1);
  border-radius: 8px;
}

.updates-section h2, .devices-section h2, .commands-section h2, .settings-section h2 {
  margin-bottom: 1rem;
  color: var(--text-primary);
}

.no-updates, .no-devices, .devices-error {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
  background: var(--surface-2);
  border-radius: 6px;
}

.devices-error {
  color: var(--error-color);
}

.devices-error .btn-secondary {
  margin-top: 0.75rem;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.command-message {
  padding: 0.75rem;
  background: var(--success-surface);
  color: var(--success-color);
  border-radius: 6px;
}

.status-badge.queued, .status-badge.delivered {
  background: var(--surface-3);
  color: var(--text-primary);
}

.status-badge.succeeded {
  background: var(--success-surface);
  color: var(--success-color);
}

.status-badge.failed, .status-badge.expired {
  background: var(--error-surface);
  color: var(--error-color);
}

.diagnostics-panel {
  margin-top: 1rem;
  padding: 1rem;
  background: var(--surface-2);
  border-radius: 6px;
}

.diagnostics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}

.diagnostics-panel pre {
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.diagnostics-events {
  margin: 0;
  padding-left: 1.25rem;
}

.devices-table code {
  font-size: 0.75rem;
  overflow-wrap: anywhere;
}

.updates-list {
  display: grid;
  gap: 1rem;
}

.update-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--surface-2);
  border-radius: 6px;
}

.update-info {
  flex: 1;
}

.update-info h3 {
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.update-info p {
  margin: 0.25rem 0;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.compatible {
  color: var(--success-color);
}

.not-compatible {
  color: var(--error-color);
}

.update-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: 1rem;
}

.devices-table {
  width: 100%;
  border-collapse: collapse;
}

.devices-table th {
  padding: 0.75rem;
  text-align: left;
  background: var(--surface-2);
  color: var(--text-primary);
}

.devices-table td {
  padding: 0.75rem;
  border-bottom: 1px solid var(--surface-border);
}

.devices-table tr:hover {
  background: var(--surface-hover);
}

.status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: bold;
}

.status-badge.online {
  background: var(--success-surface);
  color: var(--success-color);
}

.status-badge.offline {
  background: var(--error-surface);
  color: var(--error-color);
}

.settings-form {
  display: grid;
  gap: 1rem;
  max-width: 500px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-primary);
}

select {
  padding: 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--surface-border);
  background: var(--surface-2);
  color: var(--text-primary);
}

/* Buttons */
.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary:hover {
  background: var(--primary-hover);
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: var(--secondary-color);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-secondary:hover {
  background: var(--secondary-hover);
}

.btn-small {
  padding: 0.25rem 0.5rem;
  background: var(--surface-3);
  color: var(--text-primary);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-small:hover {
  background: var(--surface-hover);
}

/* Deploy Dialog */
.deploy-dialog {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
}

.dialog-content {
  background: var(--surface-1);
  padding: 2rem;
  border-radius: 8px;
  width: 100%;
  max-width: 500px;
  position: relative;
  z-index: 1001;
}

.dialog-content h3 {
  margin-bottom: 1.5rem;
  color: var(--text-primary);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.5rem;
}

input[type="text"], select {
  width: 100%;
  padding: 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--surface-border);
  background: var(--surface-2);
  color: var(--text-primary);
}
</style>
