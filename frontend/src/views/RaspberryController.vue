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

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8887';

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
      try {
        const response = await axios.post(`${BASE_URL}/src/extensions/raspberry_pi_controller/configure`, {
          broker: this.broker,
          port: this.port,
          username: this.username,
          password: this.password
        });
        console.log(response.data.message);
      } catch (error) {
        console.error('Error configuring MQTT:', error);
      }
    },
    async sendCommand() {
      try {
        const response = await axios.post(`${BASE_URL}/src/extensions/raspberry_pi_controller/send`, {
          topic: this.topic,
          payload: this.payload
        });
        console.log(response.data.message);
      } catch (error) {
        console.error('Error sending command:', error);
      }
    },
    async fetchStatus() {
      try {
        const response = await axios.get(`${BASE_URL}/src/extensions/raspberry_pi_controller/status`);
        this.status = response.data.status;
      } catch (error) {
        console.error('Error fetching status:', error);
      }
    }
  },
  mounted() {
    this.fetchStatus();
  }
};
</script>
