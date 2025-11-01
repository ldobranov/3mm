<template>
  <div>
    <h1>Edit Settings</h1>
    <form @submit.prevent="updateSettings">
      <label for="name">Name:</label>
      <input v-model="settings.name" id="name" type="text" required />

      <label for="language">Language:</label>
      <input v-model="settings.language" id="language" type="text" required />

      <label for="data">Data:</label>
      <textarea v-model="settings.data" id="data" required></textarea>

      <button type="submit">Update Settings</button>
    </form>
    <div v-if="successMessage" class="success-message">
      {{ successMessage }}
    </div>
    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
    </div>
  </div>
</template>

<script>
import http from '@/utils/http';

export default {
  data() {
    return {
      settings: {
        id: 1, // Default ID for testing
        name: '',
        language: '',
        data: '{}',
      },
      successMessage: '',
      errorMessage: '',
    };
  },
  methods: {
    async updateSettings() {
      try {
        const parsedData = JSON.parse(this.settings.data);
        const response = await http.put(`${import.meta.env.VITE_API_BASE_URL}/settings/update`, {
          id: this.settings.id,
          name: this.settings.name,
          language: this.settings.language,
          data: parsedData,
        });
        this.successMessage = response.data.message;
        this.errorMessage = '';
      } catch (error) {
        this.errorMessage = error.response?.data?.detail || 'Failed to update settings.';
        console.error(error);
      }
    },
  },
};
</script>

<style scoped>
.success-message {
  color: green;
}

.error-message {
  color: red;
}
</style>
