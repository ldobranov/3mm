<template>
  <div class="devices-view">
    <div class="extension-header">
      <h1>{{ t('mainServer.title', 'Devices') }}</h1>
      <p>{{ t('mainServer.description', 'Pair, inspect and manage devices') }}</p>
    </div>

    <div class="extension-content">
      <FleetPairing @approved="loadDevices" @registry-refresh="loadDevices" />
      <!-- Dashboard Overview -->
      <div class="dashboard-overview">
        <h2>{{ t('mainServer.dashboard.overview', 'System Overview') }}</h2>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ devices.length }}</div>
            <div class="stat-label">{{ t('mainServer.dashboard.totalDevices', 'Total Devices') }}</div>
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
                <td>{{ device.display_name || inventoryText(device.latest_inventory, 'hostname') || device.device_id }}</td>
                <td><code>{{ device.device_id }}</code></td>
                <td>{{ device.role }}</td>
                <td>{{ inventoryText(device.latest_inventory, 'model') || inventoryText(device.latest_inventory, 'architecture') || '-' }}</td>
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
              <DeviceInventorySummary :inventory="selectedDiagnosticsDevice.latest_inventory" :translate="inventoryLabel" />
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
          <h4>Recent device events</h4>
          <ul class="diagnostics-events">
            <li v-for="event in selectedDeviceEvents" :key="event.event_id">
              <strong>{{ event.event_type }}</strong> · {{ formatTimestamp(event.occurred_at) }}
              · {{ formatResult(event.payload) }}
            </li>
            <li v-if="selectedDeviceEvents.length === 0">No events recorded.</li>
          </ul>
        </div>
      </div>

      <div class="gpio-section">
        <div class="section-title-row">
          <div>
            <h2>Mock GPIO</h2>
            <p class="section-description">Capability-driven controls from enabled modules.</p>
          </div>
          <button class="btn-secondary" @click="loadGpioCapabilities">Reload</button>
        </div>
        <p v-if="gpioMessage" class="command-message">{{ gpioMessage }}</p>
        <p v-if="!gpioDevices.length" class="no-devices">No enabled GPIO capability is installed.</p>
        <div v-else class="gpio-grid">
          <section v-for="item in gpioDevices" :key="item.deviceId" class="gpio-card">
            <h3>{{ deviceName(item.deviceId) }}</h3>
            <p class="text-muted-theme">{{ item.capability.capability_id }}</p>
            <div class="gpio-control">
              <span>Output</span>
              <strong>{{ gpioOutput(item.deviceId) ? 'On' : 'Off' }}</strong>
              <button class="btn-primary" :disabled="gpioPendingDeviceId === item.deviceId" @click="setGpioOutput(item.deviceId, item.capability.capability_id, !gpioOutput(item.deviceId))">
                {{ gpioPendingDeviceId === item.deviceId ? 'Queueing…' : gpioOutput(item.deviceId) ? 'Turn off' : 'Turn on' }}
              </button>
            </div>
          </section>
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

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import FleetPairing from '@/components/FleetPairing.vue';
import DeviceInventorySummary from '@/components/DeviceInventorySummary.vue';
import { inventoryText, type DeviceInventory } from '@/utils/device-inventory';

const { t } = useI18n();

// State
const inventoryLabel = (key: string, fallback: string) => t(`mainServer.inventory.${key}`, fallback);

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

interface DeviceEvent {
  event_id: string;
  device_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  received_at: string;
}

interface DeviceStateSummary {
  desired: { revision: number; state: Record<string, unknown>; updated_at: string };
  reported_revision: number;
  reported_state: Record<string, unknown>;
  reported_at: string | null;
  synchronized: boolean;
}
interface DeviceCapability { capability_id: string; module_id: string; version: string; metadata: Record<string, unknown>; }

const devices = ref<RegistryDevice[]>([]);
const isLoadingDevices = ref(false);
const devicesError = ref(false);
const commands = ref<DeviceCommand[]>([]);
const deviceEvents = ref<DeviceEvent[]>([]);
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
const selectedDeviceEvents = computed(() =>
  deviceEvents.value.filter((event) => event.device_id === selectedDiagnosticsDeviceId.value).slice(0, 10)
);
const deviceCapabilities = ref<Record<string, DeviceCapability[]>>({});
const gpioStates = ref<Record<string, boolean>>({});
const gpioPendingDeviceId = ref('');
const gpioMessage = ref('');
const gpioDevices = computed(() => devices.value.flatMap((device) =>
  (deviceCapabilities.value[device.device_id] || [])
    .filter((capability) => capability.capability_id === 'gpio.digital.control')
    .map((capability) => ({ deviceId: device.device_id, capability }))
));
// Fetch data on mount
onMounted(async () => {
  await loadDevices();
  await loadDeviceStates();
  await loadCommands();
  await loadDeviceEvents();
  await loadGpioCapabilities();
});

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
    for (const command of commands.value.filter((item) => item.command_type === 'capability.invoke' && item.status === 'succeeded')) {
      const outputs = command.result?.outputs;
      if (outputs && typeof outputs === 'object') {
        const value = Object.values(outputs as Record<string, unknown>)[0];
        if (typeof value === 'boolean') gpioStates.value[command.device_id] = value;
      }
    }
  } catch (error) {
    console.error('Failed to load command history:', error);
    commandsError.value = true;
  }
};

const loadDeviceEvents = async () => {
  const histories = await Promise.all(
    devices.value.map(async (device) => {
      try {
        const response = await http.get(`/api/v1/devices/${device.device_id}/events`);
        return response.data as DeviceEvent[];
      } catch {
        return [] as DeviceEvent[];
      }
    })
  );
  deviceEvents.value = histories
    .flat()
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at));
};

const loadGpioCapabilities = async () => {
  const entries = await Promise.all(devices.value.map(async (device) => {
    try {
      const response = await http.get(`/api/v1/devices/${device.device_id}/capabilities`);
      return [device.device_id, response.data as DeviceCapability[]] as const;
    } catch {
      return [device.device_id, []] as const;
    }
  }));
  deviceCapabilities.value = Object.fromEntries(entries);
};

const gpioOutput = (deviceId: string) => gpioStates.value[deviceId] === true;

const setGpioOutput = async (deviceId: string, capabilityId: string, value: boolean) => {
  gpioPendingDeviceId.value = deviceId;
  gpioMessage.value = '';
  try {
    await http.post(`/api/v1/devices/${deviceId}/capabilities/invoke`, {
      capability_id: capabilityId,
      action: 'set_output',
      arguments: { capability_id: 'gpio.output.1', value },
    });
    gpioMessage.value = `GPIO output command queued for ${deviceName(deviceId)}`;
    await loadCommands();
  } catch (error) {
    console.error('Failed to queue GPIO command:', error);
    gpioMessage.value = 'GPIO command could not be queued';
  } finally {
    gpioPendingDeviceId.value = '';
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
    const response = await http.get('/api/v1/devices?inventory_schema_version=2');
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

</script>

<style scoped>
.devices-view {
  width: min(100% - 2rem, 1200px);
  margin: 0 auto;
  padding: 2rem 0 3rem;
  color: var(--text-primary);
}

.extension-header {
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--surface-border);
}

.extension-header h1 {
  color: var(--text-primary);
  font-size: clamp(1.6rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: -0.035em;
}

.extension-header p {
  color: var(--text-secondary);
}

.dashboard-overview {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--surface-1);
  border: 1px solid var(--surface-border);
  border-radius: var(--border-radius-lg);
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
  border: 1px solid var(--surface-border);
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

.updates-section, .devices-section, .commands-section, .settings-section, .gpio-section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--surface-1);
  border: 1px solid var(--surface-border);
  border-radius: var(--border-radius-lg);
  overflow-x: auto;
}

.section-description { color: var(--text-secondary); margin: 0.25rem 0 0; }
.gpio-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }
.gpio-card { padding: 1rem; border: 1px solid var(--surface-border); border-radius: var(--border-radius-md); background: var(--surface-2); }
.gpio-card h3 { margin: 0; color: var(--text-primary); }
.gpio-control { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
.gpio-control strong { color: var(--text-primary); min-width: 2rem; }

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
  color: var(--text-primary);
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

@media (max-width: 768px) {
  .devices-view {
    width: min(100% - 1.25rem, 1200px);
    padding-top: 1.25rem;
  }

  .dashboard-overview,
  .updates-section,
  .devices-section,
  .commands-section,
  .settings-section {
    padding: 1rem;
  }
}
</style>
