<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useDisplaysStore } from '@/stores/displays';
import { useSettingsStore } from '@/stores/settings';
import http from '@/utils/http';

const store = useDisplaysStore();
const settingsStore = useSettingsStore();
const styleSettings = computed(() => settingsStore.styleSettings);
const title = ref('');
const slug = ref('');
const isPublic = ref(false);
const allDisplays = ref<any[]>([]);
const users = ref<Map<number, string>>(new Map());
const showModal = ref(false);
const showDeleteModal = ref(false);
const dashboardToDelete = ref<any>(null);

// Get username and user ID from localStorage
const currentUsername = computed(() => localStorage.getItem('username') || '');
const currentUserId = computed(() => {
  const id = localStorage.getItem('user_id');
  return id ? parseInt(id) : null;
});

onMounted(async () => { 
  await loadDisplays();
});

async function loadDisplays() {
  // Fetch all displays (including those with permissions)
  try {
    const response = await http.get('/display/read');
    allDisplays.value = response.data.items || [];
    
    // Fetch user information for display owners
    const uniqueUserIds = [...new Set(allDisplays.value.map(d => d.user_id))];
    for (const userId of uniqueUserIds) {
      try {
        // Try to get user info - we might need to create an endpoint for this
        // For now, we'll use the current user's username for their own displays
        if (userId === currentUserId.value) {
          users.value.set(userId, currentUsername.value);
        }
      } catch (error) {
        console.error(`Failed to fetch user ${userId}:`, error);
      }
    }
  } catch (error) {
    console.error('Failed to fetch displays:', error);
    // Fallback to user's own displays
    await store.fetchMy();
    allDisplays.value = store.myDisplays;
  }
}

function openCreateModal() {
  title.value = '';
  slug.value = '';
  isPublic.value = false;
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  title.value = '';
  slug.value = '';
  isPublic.value = false;
}

async function createDisplay() {
  if (!title.value || !slug.value) return;
  
  try {
    await store.create({ title: title.value, slug: slug.value, is_public: isPublic.value });
    closeModal();
    // Refresh the list
    await loadDisplays();
  } catch (error) {
    console.error('Failed to create display:', error);
    alert('Failed to create dashboard. Please try again.');
  }
}

function confirmDelete(display: any) {
  dashboardToDelete.value = display;
  showDeleteModal.value = true;
}

async function deleteDisplay() {
  if (!dashboardToDelete.value) return;
  
  try {
    await store.remove(dashboardToDelete.value.id);
    showDeleteModal.value = false;
    dashboardToDelete.value = null;
    // Refresh the list
    await loadDisplays();
  } catch (error) {
    console.error('Failed to delete display:', error);
    alert('Failed to delete dashboard. Please try again.');
  }
}

// Check if user owns the display
function isOwner(display: any): boolean {
  return display.user_id === currentUserId.value;
}

// Get the owner's username for a display
function getOwnerUsername(display: any): string {
  // Use the owner_username from the backend response
  if (display.owner_username) {
    return display.owner_username;
  }
  // Fallback to current user's username for their own displays
  if (display.user_id === currentUserId.value) {
    return currentUsername.value;
  }
  // Final fallback
  return 'unknown';
}
</script>

<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">Dashboard Management</h1>
      <button 
        class="button button-primary"
        @click="openCreateModal"
      >
        <i class="bi bi-plus-circle" style="margin-right: 0.5rem;"></i>Create New Dashboard
      </button>
    </div>

    <h2 class="view-subtitle">Existing Dashboards</h2>
    <div v-if="allDisplays.length === 0" class="alert alert-info">
      <i class="bi bi-info-circle" style="margin-right: 0.5rem;"></i>
      No dashboards available. Create your first dashboard using the button above!
    </div>
    
    <div v-else class="grid">
      <div v-for="d in allDisplays" :key="d.id" class="card dashboard-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <h3 class="dashboard-title">
          {{ d.title || d.name }}
          <span v-if="!isOwner(d)" class="shared-indicator">
            (Shared with you)
          </span>
        </h3>
        <div class="dashboard-meta">
          <span class="chip" :class="d.is_public ? 'chip-public' : 'chip-private'">
            {{ d.is_public ? 'Public' : 'Private' }}
          </span>
        </div>
        <div class="dashboard-slug">Slug: /{{ d.slug }}</div>
        <div class="dashboard-actions">
          <router-link
            v-if="d.slug"
            class="button button-outline button-sm"
            :to="{ name: 'PublicDisplay', params: { username: getOwnerUsername(d), slug: d.slug } }"
          >
            <i class="bi bi-eye"></i>Preview
          </router-link>
          <router-link
            class="button button-outline button-sm"
            :to="`/dashboard/${d.id}/edit`"
          >
            <i class="bi bi-pencil"></i>{{ isOwner(d) ? 'Edit' : 'View' }}
          </router-link>
          <button
            v-if="isOwner(d)"
            class="button button-outline button-sm button-danger"
            @click="confirmDelete(d)"
          >
            <i class="bi bi-trash"></i>Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create Dashboard Modal -->
    <teleport to="body">
      <div v-if="showModal">
        <div class="modal-backdrop" @click="closeModal"></div>
        
        <div class="modal-container">
          <div class="modal-surface modal-lg" role="dialog" aria-modal="true" @click.stop :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
            <div style="display:flex; align-items:center; justify-content:space-between; padding-bottom:0.5rem; border-bottom:1px solid var(--card-border);">
              <h5 class="view-subtitle" style="margin:0;">Create New Dashboard</h5>
              <button type="button" class="button button-outline button-sm" @click="closeModal">×</button>
            </div>
  
            <form @submit.prevent="createDisplay" class="modal-form">
              <div class="form-group">
                <label class="form-label">Title</label>
                <input
                  type="text"
                  class="input"
                  v-model="title"
                  placeholder="Dashboard title"
                  required
                />
              </div>
  
              <div class="form-group">
                <label class="form-label">Slug</label>
                <input
                  type="text"
                  class="input"
                  v-model="slug"
                  placeholder="dashboard-slug"
                  required
                />
                <div class="form-help">URL: /@{{ currentUsername }}/{{ slug || 'dashboard-slug' }}</div>
              </div>
  
              <div class="form-group">
                <label class="checkbox-label">
                  <input
                    type="checkbox"
                    class="input"
                    id="isPublic"
                    v-model="isPublic"
                  />
                  <span>Make dashboard public</span>
                </label>
              </div>
  
              <div class="modal-actions">
                <button type="button" class="button button-secondary" @click="closeModal">
                  Cancel
                </button>
                <button type="submit" class="button button-primary">
                  <i class="bi bi-save"></i>Create
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
            <div class="modal-content">
              <p>Are you sure you want to delete the dashboard "{{ dashboardToDelete?.title || dashboardToDelete?.name }}"?</p>
              <p class="warning-text">
                <i class="bi bi-exclamation-triangle"></i>
                This action cannot be undone. All widgets in this dashboard will be deleted.
              </p>
            </div>
            <div class="modal-actions">
              <button class="button button-secondary" @click="showDeleteModal = false">
                Cancel
              </button>
              <button class="button button-danger" @click="deleteDisplay">
                <i class="bi bi-trash"></i>Delete
              </button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
/* Dashboard List styles */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.dashboard-card {
  padding: 1.5rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.dashboard-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.dashboard-title {
  margin: 0 0 0.75rem 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.shared-indicator {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: normal;
}

.dashboard-meta {
  margin-bottom: 0.75rem;
}

.chip {
  padding: 0.25rem 0.5rem;
  border-radius: var(--border-radius-sm);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.chip-public {
  background-color: rgba(25, 135, 84, 0.15);
  color: #198754;
}

.chip-private {
  background-color: rgba(108, 117, 125, 0.15);
  color: #6c757d;
}

.dashboard-slug {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
}

.dashboard-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.modal-form {
  padding-top: 1rem;
  display: grid;
  gap: 0.75rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.form-help {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: 0.25rem;
}

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  color: var(--text-primary);
}

.modal-content {
  padding-top: 0.75rem;
}

.warning-text {
  color: var(--button-danger-text);
  margin: 0.5rem 0 0 0;
}

.warning-text i {
  margin-right: 0.25rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  border-top: 1px solid var(--card-border);
  padding-top: 0.5rem;
}
</style>