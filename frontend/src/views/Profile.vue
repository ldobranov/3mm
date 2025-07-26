<template>
  <div class="profile">
    <h1>Profile</h1>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <div v-if="user">
      <p><strong>Username:</strong> {{ user.username }}</p>
      <p><strong>Email:</strong> {{ user.email }}</p>
      <p><strong>Role:</strong> {{ user.role }}</p>
      <form @submit.prevent="updateProfile">
        <label>
          Username:
          <input v-model="updatedUser.username" type="text" />
        </label>
        <label>
          Email:
          <input v-model="updatedUser.email" type="email" />
        </label>
        <label>
          Password:
          <input v-model="updatedUser.password" type="password" />
        </label>
        <button type="submit">Update Profile</button>
      </form>
    </div>
    <p v-else>Loading profile...</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';

interface User {
  username: string;
  email: string;
  role: string;
}

export default defineComponent({
  name: 'Profile',
  setup() {
    const user = ref<User | null>(null);
    const updatedUser = ref({ username: '', email: '', password: '' });
    const errorMessage = ref('');

    const fetchProfile = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          errorMessage.value = 'No token found. Please log in again.';
          return;
        }
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/user/profile`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        user.value = response.data;
        updatedUser.value.username = response.data.username;
        updatedUser.value.email = response.data.email;
      } catch (error) {
        errorMessage.value = 'Failed to fetch profile. Please try again later.';
      }
    };

    const updateProfile = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          errorMessage.value = 'No token found. Please log in again.';
          return;
        }
        await axios.put(`${import.meta.env.VITE_API_BASE_URL}/user/profile/update`, updatedUser.value, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        errorMessage.value = 'Profile updated successfully!';
        fetchProfile();
      } catch (error) {
        errorMessage.value = 'Failed to update profile. Please try again later.';
      }
    };

    onMounted(() => {
      console.log('Profile component mounted');
      fetchProfile();
    });

    return { user, updatedUser, errorMessage, updateProfile };
  },
});
</script>

<style scoped>
.profile {
  padding: 20px;
}
.error {
  color: red;
}
</style>
