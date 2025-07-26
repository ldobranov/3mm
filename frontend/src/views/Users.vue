<template>
  <div class="users">
    <h1>Users</h1>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <ul v-if="users.length">
      <li v-for="user in users" :key="user.id">
        <div v-if="editingUserId === user.id">
          <input v-model="user.username" placeholder="Username" />
          <input v-model="user.email" placeholder="Email" />
          <select v-model="user.role">
            <option value="admin">Admin</option>
            <option value="user">User</option>
          </select>
          <button @click="saveUser(user)">Save</button>
          <button @click="cancelEdit">Cancel</button>
        </div>
        <div v-else>
          {{ user.username }} ({{ user.email }})
          <button @click="editUser(user.id)">Edit</button>
        </div>
      </li>
    </ul>
    <p v-else>No users found.</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import axios from 'axios';

interface User {
  id: number;
  username: string;
  email: string;
  role: string;
}

export default defineComponent({
  name: 'Users',
  setup() {
    const users = ref<User[]>([]);
    const errorMessage = ref('');
    const editingUserId = ref<number | null>(null);

    const fetchUsers = async () => {
      try {
        const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/user/read`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
        });
        users.value = response.data.items || [];
      } catch (error) {
        errorMessage.value = 'Failed to fetch users. Please try again later.';
      }
    };

    const editUser = (userId: number) => {
      editingUserId.value = userId;
    };

    const cancelEdit = () => {
      editingUserId.value = null;
    };

    const saveUser = async (user: User) => {
      try {
        const payload = {
          id: user.id,
          username: user.username,
          email: user.email,
          role: user.role, // Send only required fields
        };
        await axios.put(`${import.meta.env.VITE_API_BASE_URL}/user/update`, payload, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
        });
        editingUserId.value = null;
        fetchUsers();
      } catch (error) {
        errorMessage.value = 'Failed to save user. Please try again later.';
      }
    };

    onMounted(() => {
      console.log('Users component mounted');
      fetchUsers();
    });

    return { users, errorMessage, editingUserId, editUser, cancelEdit, saveUser };
  },
});
</script>

<style scoped>
.users {
  padding: 20px;
}
.error {
  color: red;
}
</style>