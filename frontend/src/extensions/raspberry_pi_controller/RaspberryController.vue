<template>
  <div>
    <h1>Raspberry Pi Controller</h1>
    <form @submit.prevent="configureMQTT">
      <input v-model="broker" placeholder="Broker" />
      <input v-model="port" placeholder="Port" type="number" />
      <input v-model="username" placeholder="Username" />
      <input v-model="password" placeholder="Password" type="password" />
      <button type="submit">Configure MQTT</button>
    </form>

    <form @submit.prevent="sendCommand">
      <input v-model="topic" placeholder="Topic" />
      <input v-model="payload" placeholder="Payload" />
      <button type="submit">Send Command</button>
    </form>

    <div>
      <h2>Status</h2>
      <p>{{ status }}</p>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default {
  data() {
    return {
      broker: '',
      port: 1883,
      username: '',
      password: '',
      topic: '',
      payload: '',
      status: ''
    };
  },
  methods: {
    async configureMQTT() {
      await axios.post(`${API_BASE_URL}/src/extensions/mqtt/configure`, {
        broker: this.broker,
        port: this.port,
        username: this.username,
        password: this.password
      });
    },
    async sendCommand() {
      await axios.post(`${API_BASE_URL}/src/extensions/raspberry_pi_controller/send`, {
        topic: this.topic,
        payload: this.payload
      });
    },
    async fetchStatus() {
      const response = await axios.get(`${API_BASE_URL}/src/extensions/raspberry_pi_controller/status`);
      this.status = response.data.status;
    }
  },
  mounted() {
    this.fetchStatus();
  }
};
</script>
