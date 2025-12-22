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
        
        <div v-if="devices.length === 0" class="no-devices">
          <p>{{ t('mainServer.devices.none', 'No devices connected') }}</p>
        </div>
        
        <div v-else class="devices-list">
          <table class="devices-table">
            <thead>
              <tr>
                <th>{{ t('mainServer.devices.deviceName', 'Device Name') }}</th>
                <th>{{ t('mainServer.devices.deviceIP', 'IP Address') }}</th>
                <th>{{ t('mainServer.devices.deviceStatus', 'Status') }}</th>
                <th>{{ t('mainServer.devices.actions', 'Actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="device in devices" :key="device.id">
                <td>{{ device.name }}</td>
                <td>{{ device.ip }}</td>
                <td>
                  <span :class="['status-badge', device.status]">
                    {{ device.status === 'online' 
                       ? t('mainServer.devices.online', 'Online') 
                       : t('mainServer.devices.offline', 'Offline') }}
                  </span>
                </td>
                <td>
                  <button @click="openDeployDialog(device.id)" class="btn-small">
                    {{ t('mainServer.devices.deployTo', 'Deploy to Device') }}
                  </button>
                </td>
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
import { ref, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

const { t } = useI18n();

// State
const availableUpdates = ref<any[]>([]);
const devices = ref<any[]>([]);
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
onMounted(() => {
  loadAvailableUpdates();
  loadDevices();
  loadSettings();
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

// Load connected devices
const loadDevices = async () => {
  try {
    const response = await http.get('/api/main-server/devices');
    devices.value = response.data.devices || [];
  } catch (error) {
    console.error('Failed to load devices:', error);
  }
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

.updates-section, .devices-section, .settings-section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--surface-1);
  border-radius: 8px;
}

.updates-section h2, .devices-section h2, .settings-section h2 {
  margin-bottom: 1rem;
  color: var(--text-primary);
}

.no-updates, .no-devices {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
  background: var(--surface-2);
  border-radius: 6px;
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