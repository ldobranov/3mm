<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">User Management</h1>
      <button 
        class="button button-primary"
        @click="openCreateModal"
      >
        <i class="bi bi-person-plus" style="margin-right: 0.5rem;"></i>Create New User
      </button>
    </div>

    <div v-if="errorMessage" class="alert mt-2" style="border-color: var(--danger); color: var(--danger);">
      {{ errorMessage }}
      <button type="button" class="button button-outline button-sm" @click="errorMessage = ''" aria-label="Close" style="position: absolute; right: 0.5rem; top: 0.5rem;">×</button>
    </div>

    <div v-if="successMessage" class="alert mt-2" style="border-color: var(--accent); color: var(--color-text);">
      {{ successMessage }}
      <button type="button" class="button button-outline button-sm" @click="successMessage = ''" aria-label="Close" style="position: absolute; right: 0.5rem; top: 0.5rem;">×</button>
    </div>

    <div v-if="loading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else-if="users.length === 0" class="alert alert-info">
      <i class="bi bi-info-circle" style="margin-right: 0.5rem;"></i>
      No users found. Create your first user using the button above!
    </div>

    <div v-else class="grid">
      <div v-for="user in users" :key="user.id" class="card user-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="user-header">
          <div class="user-avatar">
            <i class="bi bi-person-circle"></i>
          </div>
          <div class="user-info">
            <h3 class="user-name">{{ user.username }}</h3>
            <p class="user-email">
              <i class="bi bi-envelope"></i>
              {{ user.email }}
            </p>
          </div>
        </div>

        <div class="user-meta">
          <span class="chip" :class="user.role === 'admin' ? 'chip-admin' : 'chip-user'">
            <i class="bi bi-shield-check"></i>
            {{ user.role || 'User' }}
          </span>
          <span class="user-joined">
            <i class="bi bi-calendar"></i>
            Joined: {{ formatDate(user.created_at) }}
          </span>
        </div>

        <div class="user-actions">
          <button
            class="button button-outline button-sm"
            @click="openEditModal(user)"
          >
            <i class="bi bi-pencil"></i>Edit
          </button>
          <button
            class="button button-outline button-sm"
            :class="{ 'button-danger': true }"
            @click="confirmDelete(user)"
            :disabled="user.id === currentUserId"
          >
            <i class="bi bi-trash"></i>Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create/Edit User Modal -->
    <teleport to="body">
      <div v-if="showModal">
        <div class="modal-backdrop" @click="closeModal"></div>
        
        <div class="modal-container">
          <div class="modal-surface modal-lg" role="dialog" aria-modal="true" @click.stop :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
            <div style="display:flex; align-items:center; justify-content:space-between; padding-bottom:0.5rem; border-bottom:1px solid var(--card-border);">
              <h5 class="view-subtitle" style="margin:0;">
                {{ editingUser ? 'Edit User' : 'Create New User' }}
              </h5>
              <button type="button" class="button button-outline button-sm" @click="closeModal">×</button>
            </div>

            <form @submit.prevent="saveUser" style="padding-top: 1rem; display: grid; gap: 1rem;">
              <div>
                <label class="text-sm" style="display: block; margin-bottom: 0.25rem; color: var(--color-text);">Username</label>
                <input 
                  type="text"
                  class="input"
                  v-model="formData.username"
                  placeholder="Enter username"
                  required
                />
              </div>

              <div>
                <label class="text-sm" style="display: block; margin-bottom: 0.25rem; color: var(--color-text);">Email</label>
                <input 
                  type="email"
                  class="input"
                  v-model="formData.email"
                  placeholder="Enter email"
                  required
                />
              </div>

              <div v-if="!editingUser">
                <label class="text-sm" style="display: block; margin-bottom: 0.25rem; color: var(--color-text);">Password</label>
                <input 
                  type="password"
                  class="input"
                  v-model="formData.password"
                  placeholder="Enter password"
                  :required="!editingUser"
                />
              </div>

              <div>
                <label class="text-sm" style="display: block; margin-bottom: 0.25rem; color: var(--color-text);">Role</label>
                <select class="select" v-model="formData.role">
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              <div class="actions-row" style="justify-content: end; gap: 0.5rem;">
                <button type="button" class="button button-secondary" @click="closeModal">
                  Cancel
                </button>
                <button type="submit" class="button button-primary">
                  <i class="bi bi-save" style="margin-right: 0.25rem;"></i>
                  {{ editingUser ? 'Update' : 'Create' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </teleport>

    <!-- Delete Confirmation Modal -->
    <teleport to="body">
      <div v-if="showDeleteModal">
        <div class="modal-backdrop" @click="showDeleteModal = false"></div>
        
        <div class="modal-container">
          <div class="modal-surface modal-sm" role="dialog" aria-modal="true" @click.stop :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
            <div style="display:flex; align-items:center; justify-content:space-between; padding-bottom:0.5rem; border-bottom:1px solid var(--card-border);">
              <h5 class="view-subtitle" style="margin:0;">Confirm Delete</h5>
              <button type="button" class="button button-outline button-sm" @click="showDeleteModal = false">×</button>
            </div>
            <div style="padding-top: 0.75rem;">
              <p>Are you sure you want to delete the user "{{ userToDelete?.username }}"?</p>
              <p style="color: var(--button-danger-text);">
                <i class="bi bi-exclamation-triangle" style="margin-right: 0.25rem;"></i>
                This action cannot be undone.
              </p>
            </div>
            <div class="actions-row" style="justify-content: end; border-top: 1px solid var(--card-border); padding-top: 0.5rem;">
              <button class="button button-secondary" @click="showDeleteModal = false">
                Cancel
              </button>
              <button class="button button-danger" @click="deleteUser">
                <i class="bi bi-trash" style="margin-right: 0.25rem;"></i>Delete
              </button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed } from 'vue';
import http from '@/utils/http';
import { useSettingsStore } from '@/stores/settings';

interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  created_at?: string;
}

export default defineComponent({
  name: 'Users',
  setup() {
    const settingsStore = useSettingsStore();
    const styleSettings = computed(() => settingsStore.styleSettings);
    const users = ref<User[]>([]);
    const loading = ref(false);
    const errorMessage = ref('');
    const successMessage = ref('');
    const showModal = ref(false);
    const showDeleteModal = ref(false);
    const editingUser = ref<User | null>(null);
    const userToDelete = ref<User | null>(null);
    
    const currentUserId = computed(() => {
      const id = localStorage.getItem('user_id');
      return id ? parseInt(id) : null;
    });

    const formData = ref({
      username: '',
      email: '',
      password: '',
      role: 'user'
    });

    const fetchUsers = async () => {
      loading.value = true;
      try {
        const response = await http.get('/user/read');
        users.value = response.data.items || [];
      } catch (error) {
        errorMessage.value = 'Failed to fetch users. Please try again later.';
      } finally {
        loading.value = false;
      }
    };

    const openCreateModal = () => {
      editingUser.value = null;
      formData.value = {
        username: '',
        email: '',
        password: '',
        role: 'user'
      };
      showModal.value = true;
    };

    const openEditModal = (user: User) => {
      editingUser.value = user;
      formData.value = {
        username: user.username,
        email: user.email,
        password: '',
        role: user.role || 'user'
      };
      showModal.value = true;
    };

    const closeModal = () => {
      showModal.value = false;
      editingUser.value = null;
      formData.value = {
        username: '',
        email: '',
        password: '',
        role: 'user'
      };
    };

    const saveUser = async () => {
      try {
        if (editingUser.value) {
          // Update existing user
          const payload = {
            id: editingUser.value.id,
            username: formData.value.username,
            email: formData.value.email,
            role: formData.value.role
          };
          await http.put('/user/update', payload);
          successMessage.value = 'User updated successfully!';
        } else {
          // Create new user
          await http.post('/user/register', {
            username: formData.value.username,
            email: formData.value.email,
            password: formData.value.password
          });
          successMessage.value = 'User created successfully!';
        }
        closeModal();
        fetchUsers();
      } catch (error: any) {
        errorMessage.value = error.response?.data?.detail || 'Failed to save user. Please try again.';
      }
    };

    const confirmDelete = (user: User) => {
      userToDelete.value = user;
      showDeleteModal.value = true;
    };

    const deleteUser = async () => {
      if (!userToDelete.value) return;
      
      try {
        await http.delete(`/user/delete/${userToDelete.value.id}`);
        successMessage.value = 'User deleted successfully!';
        showDeleteModal.value = false;
        userToDelete.value = null;
        fetchUsers();
      } catch (error) {
        errorMessage.value = 'Failed to delete user. Please try again.';
      }
    };

    const formatDate = (dateString?: string) => {
      if (!dateString) return 'Unknown';
      const date = new Date(dateString);
      return date.toLocaleDateString();
    };

    const getRoleBadgeClass = (role: string) => {
      return role === 'admin' ? 'bg-danger' : 'bg-primary';
    };

    onMounted(() => {
      fetchUsers();
    });

    return {
      users,
      loading,
      errorMessage,
      successMessage,
      showModal,
      showDeleteModal,
      editingUser,
      userToDelete,
      currentUserId,
      formData,
      styleSettings,
      fetchUsers,
      openCreateModal,
      openEditModal,
      closeModal,
      saveUser,
      confirmDelete,
      deleteUser,
      formatDate,
      getRoleBadgeClass
    };
  },
});
</script>

<style scoped>
/* Users grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.user-card {
  padding: 1.5rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.user-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.user-header {
  display: flex;
  align-items: center;
  margin-bottom: 1rem;
}

.user-avatar {
  font-size: 3rem;
  color: var(--text-secondary);
  margin-right: 1rem;
}

.user-info {
  flex: 1;
}

.user-name {
  margin: 0 0 0.25rem 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.user-email {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.user-email i {
  margin-right: 0.25rem;
}

.user-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--card-border);
  border-bottom: 1px solid var(--card-border);
}

.chip {
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.chip-admin {
  background-color: rgba(220, 53, 69, 0.15);
  color: var(--button-danger-text);
}

.chip-user {
  background-color: rgba(0, 123, 255, 0.15);
  color: var(--button-primary-text);
}

.user-joined {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.user-joined i {
  margin-right: 0.25rem;
}

.user-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.actions-row {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-start;
}
</style>