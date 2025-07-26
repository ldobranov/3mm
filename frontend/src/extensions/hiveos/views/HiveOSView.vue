<template>
  <div>
    <h1>HiveOS Extension</h1>

    <div>
      <label for="apiKey">HIVEOS API Key:</label>
      <input id="apiKey" v-model="apiKey" placeholder="Enter your HiveOS API Key" />
      <button @click="saveApiKey">Save</button>
      <button @click="revokeApiKey">Revoke</button>
    </div>

    <div v-if="farms.length">
      <label for="farmSelector">Select Farm:</label>
      <select id="farmSelector" v-model="selectedFarmId" @change="saveSelectedFarm">
        <option v-for="farm in farms" :key="farm.id" :value="farm.id">
          {{ farm.name }}
        </option>
      </select>
    </div>

    <form @submit.prevent="authenticate">
      <label for="apiKey">API Key:</label>
      <input id="apiKey" v-model="apiKey" placeholder="Enter your HiveOS API Key" />
      <button type="submit">Authenticate</button>
    </form>

    <div v-if="farms.length">
      <label for="farmSelector">Select Farm:</label>
      <select id="farmSelector" v-model="selectedFarmId" @change="fetchWorkers">
        <option v-for="farm in farms" :key="farm.id" :value="farm.id">
          {{ farm.name }}
        </option>
      </select>
    </div>

    <div v-if="workers.length">
      <h2>Workers</h2>
      <ul>
        <li v-for="worker in workers" :key="worker.id">
          <strong>ID:</strong> {{ worker.id }} <br>
          <strong>Name:</strong> {{ worker.name }} <br>
          <strong>Status:</strong> {{ worker.status }} <br>
          <button @click="sendCommand(worker.id, 'start')">Start</button>
          <button @click="sendCommand(worker.id, 'stop')">Stop</button>
          <button @click="sendRigAction('reboot')">Reboot</button>
          <button @click="sendRigAction('shutdown')">Shutdown</button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  data() {
    return {
      apiKey: '',
      farms: [],
      selectedFarmId: null,
      workers: [],
      loading: false,
      error: ''
    };
  },
  methods: {
    async authenticate() {
      try {
        const response = await axios.post('/extensions/hiveos/api/authenticate', {
          api_key: this.apiKey
        });

        // Save the backend token for future requests
        const backendToken = response.headers['authorization-token'];
        if (backendToken) {
          localStorage.setItem('backendToken', backendToken);
          // console.log('Backend token saved for future requests:', backendToken);

          // Fetch farms immediately after authentication
          await this.fetchFarms();
        } else {
          console.warn('No backend token received during authentication.');
        }

        // alert('Authenticated successfully!');
      } catch (error) {
        console.error('Authentication failed:', error.response?.data || error.message);
        alert('Authentication failed!');
      }
    },
    async fetchFarms() {
      try {
        const backendToken = localStorage.getItem('backendToken');
        if (!backendToken) {
          console.error('No backend token found in localStorage. Please authenticate first.');
          alert('Please authenticate first.');
          return;
        }

        const response = await axios.get('/extensions/hiveos/api/farms', {
          headers: { Authorization: `Bearer ${backendToken}` }
        });
        this.farms = response.data;
        console.log('Farms fetched successfully:', this.farms);
      } catch (error) {
        console.error('Error fetching farms:', error.response?.data || error.message);
        alert('Failed to fetch farms!');
      }
    },
    async saveApiKey() {
      try {
        const response = await axios.post(`/extensions/hiveos/api/save-api-key`, null, {
          params: { api_key: this.apiKey }
        });
        alert('API Key saved successfully!');
        await this.fetchFarms();
      } catch (error) {
        console.error('Error saving API Key:', error.response?.data || error.message);
        alert('Failed to save API Key!');
      }
    },
    async revokeApiKey() {
      try {
        await axios.post('/extensions/hiveos/api/revoke-api-key');
        this.apiKey = '';
        this.farms = [];
        this.selectedFarmId = null;
        alert('API Key revoked successfully!');
      } catch (error) {
        console.error('Error revoking API Key:', error.response?.data || error.message);
        alert('Failed to revoke API Key!');
      }
    },
    async saveSelectedFarm() {
      try {
        await axios.post('/extensions/hiveos/api/save-selected-farm', { farm_id: this.selectedFarmId });
        alert('Selected farm saved successfully!');
      } catch (error) {
        console.error('Error saving selected farm:', error.response?.data || error.message);
        alert('Failed to save selected farm!');
      }
    },
    async fetchWorkers() {
      if (!this.selectedFarmId) return;
      try {
        const backendToken = localStorage.getItem('backendToken');
        const response = await axios.get(`/extensions/hiveos/api/farms/${this.selectedFarmId}/workers`, {
          headers: { Authorization: `Bearer ${backendToken}` }
        });
        this.workers = response.data;
      } catch (error) {
        console.error('Error fetching workers:', error.response?.data || error.message);
        alert('Failed to fetch workers!');
      }
    },
    async sendCommand(workerId, action) {
      try {
        const backendToken = localStorage.getItem('backendToken');
        const payload = {
          worker_ids: [workerId],
          action: action // Corrected field name
        };

        console.log('Payload being sent:', payload); // Debugging log

        await axios.post(
          `/extensions/hiveos/api/farms/${this.selectedFarmId}/workers/command`,
          payload,
          {
            headers: { Authorization: `Bearer ${backendToken}` }
          }
        );

        // alert(`Action '${action}' sent to worker ${workerId}!`);
        this.fetchWorkers(); // Refresh workers to reflect the updated state
      } catch (error) {
        console.error('Error sending action:', error.response?.data || error.message);
        if (error.response?.status === 403) {
          alert('Permission denied: Please check your API key permissions.');
        } else {
          alert(`Failed to send action '${action}': ${JSON.stringify(error.response?.data?.detail || error.message)}`);
        }
      }
    },
    async sendRigAction(action) {
      this.loading = true;
      this.error = '';
      const payload = {
        worker_ids: this.workers.map(worker => worker.id),
        action
      };
      console.log('[HiveOSView] Sending rig action:', action, 'Payload:', payload);
      try {
        const backendToken = localStorage.getItem('backendToken');
        const response = await axios.post(`/extensions/hiveos/api/farms/${this.selectedFarmId}/workers/command`, payload, {
          headers: { Authorization: `Bearer ${backendToken}` }
        });
        await this.fetchWorkers(); // Refresh workers to reflect the updated state
      } catch (error) {
        console.error('Failed to send rig action:', error.response?.data || error.message);
        this.error = error.response?.data?.detail || error.message;
        alert(`Failed to send action '${action}': ${this.error}`);
      } finally {
        this.loading = false;
      }
    }
  }
};
</script>
