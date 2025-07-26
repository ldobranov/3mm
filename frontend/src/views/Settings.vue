<template>
  <div class="container py-5">
    <!-- Page Header -->
    <header class="text-center mb-5">
      <h1 class="display-4">Settings</h1>
      <p class="lead text-muted">Manage your backend settings and menu items</p>
    </header>

    <div v-if="settings" class="row">
      <!-- Backend Settings Section -->
      <div class="col-md-6">
        <div class="card shadow-sm mb-4">
          <div class="card-body">
            <h5 class="card-title">Backend Settings</h5>
            <ul class="list-group">
              <li v-for="(value, key) in settings.data" :key="key" class="list-group-item">
                <strong>{{ key }}:</strong>
                <span v-if="Array.isArray(value) || typeof value === 'object'">
                  {{ Array.isArray(value) ? value.join(', ') : JSON.stringify(value, null, 2) }}
                </span>
                <span v-else>{{ value }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="card shadow-sm mb-4">
          <div class="card-body">
            <h5 class="card-title">Update Settings</h5>
            <form @submit.prevent="updateSettings">
              <div class="mb-3">
                <label for="language" class="form-label">Language</label>
                <input v-model="settings.language" id="language" type="text" class="form-control" />
              </div>
              <div class="mb-3">
                <label for="name" class="form-label">Name</label>
                <input v-model="settings.name" id="name" type="text" class="form-control" />
              </div>
              <button type="submit" class="btn btn-primary w-100">Save Settings</button>
            </form>
          </div>
        </div>
      </div>

      <!-- Menu Editor Section -->
      <div class="col-md-6">
        <div class="card shadow-sm mb-4">
          <div class="card-body">
            <h5 class="card-title">Menu Editor</h5>
            <MenuEditor />
          </div>
        </div>
      </div>
    </div>

    <div v-else class="text-center">
      <p>Loading settings...</p>
    </div>

    <div v-if="errorMessage" class="alert alert-danger text-center mt-3">{{ errorMessage }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';
import MenuEditor from './MenuEditor.vue';

export default defineComponent({
  name: 'Settings',
  components: { MenuEditor },
  setup() {
    const settings = ref<any>(null);
    const errorMessage = ref('');

    const fetchSettings = async () => {
      try {
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/settings/read`);
        settings.value = response.data.items[0];
      } catch (error) {
        errorMessage.value = 'Failed to fetch settings.';
        console.error(error);
      }
    };

    const updateSettings = async () => {
      try {
        await axios.put(`${import.meta.env.VITE_API_BASE_URL}/settings/update`, settings.value);
        errorMessage.value = '';
      } catch (error) {
        errorMessage.value = 'Failed to update settings.';
        console.error(error);
      }
    };

    onMounted(() => {
      console.log('Settings component mounted');
      fetchSettings();
    });

    return { settings, updateSettings, errorMessage };
  },
});
</script>

<style scoped>
/* Custom styles for better appearance */
header {
  background-color: #f8f9fa;
  padding: 20px;
  border-radius: 10px;
}
.card {
  border-radius: 10px;
}
.list-group-item {
  border-radius: 5px;
}
</style>
