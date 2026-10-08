<script setup lang="ts">
import { ref, onMounted, computed, useId } from 'vue';
import { useDisplaysStore } from '@/stores/displays';
import { useSettingsStore } from '@/stores/settings';
import { useI18n } from '@/utils/i18n';
import { useUiLabels } from '@/utils/ui-labels';
import UiButton from '@/components/ui/UiButton.vue';
import UiDialog from '@/components/ui/UiDialog.vue';
import http from '@/utils/dynamic-http';

const { t, currentLanguage } = useI18n();

const store = useDisplaysStore();
const settingsStore = useSettingsStore();
const label = useUiLabels();
const formId = useId();
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

// Preserve the former backdrop dismissal while using the shared native dialog.
function closeOnBackdrop(event: MouseEvent, close: () => void) {
  const dialog = event.currentTarget as HTMLDialogElement;
  if (event.target !== dialog) return;
  const bounds = dialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom) close();
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
    alert(t('dashboard.createError', 'Failed to create dashboard. Please try again.'));
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
    alert(t('dashboard.deleteError', 'Failed to delete dashboard. Please try again.'));
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
  <div class="view dashboard-view ui-v2" :key="currentLanguage"
    :data-card="settingsStore.uiDesign.components.card"
    :data-button="settingsStore.uiDesign.components.button">
    <header class="view-header dashboard-heading">
      <h1 class="view-title">{{ t('dashboard.title', 'Dashboard Management') }}</h1>
      <UiButton variant="primary" class="dashboard-create" @click="openCreateModal">
        <i class="bi bi-plus-lg" aria-hidden="true"></i>{{ t('dashboard.createNew', 'Create New Dashboard') }}
      </UiButton>
    </header>

    <div class="dashboard-section-heading">
      <h2>{{ t('dashboard.existingDashboards', 'Existing Dashboards') }}</h2>
      <span class="ui-badge">{{ allDisplays.length }}</span>
    </div>

    <div v-if="allDisplays.length === 0" class="ui-section dashboard-empty" role="status">
      <i class="bi bi-grid-1x2" aria-hidden="true"></i>
      <p class="ui-muted">{{ t('dashboard.noDashboards', 'No dashboards available. Create your first dashboard using the button above!') }}</p>
    </div>

    <div v-else class="dashboard-grid">
      <article v-for="d in allDisplays" :key="d.id" class="ui-section dashboard-card">
        <div class="dashboard-meta ui-row">
          <span class="ui-badge">
            <i :class="d.is_public ? 'bi bi-globe2' : 'bi bi-lock'" aria-hidden="true"></i>
            {{ d.is_public ? t('dashboard.public', 'Public') : t('dashboard.private', 'Private') }}
          </span>
          <span v-if="!isOwner(d)" class="ui-badge shared-indicator">
            <i class="bi bi-people" aria-hidden="true"></i>{{ t('dashboard.sharedWithYou', 'Shared with you') }}
          </span>
        </div>
        <h3 class="dashboard-title">{{ d.title || d.name }}</h3>
        <dl class="dashboard-details">
          <div><dt>{{ label('owner') }}</dt><dd>{{ getOwnerUsername(d) }}</dd></div>
          <div><dt>{{ t('dashboard.slug', 'Slug') }}</dt><dd class="dashboard-slug">/{{ d.slug }}</dd></div>
        </dl>
        <div class="dashboard-actions">
          <router-link
            v-if="d.slug"
            class="ui-button ui-button--secondary"
            :to="{ name: 'PublicDisplay', params: { username: getOwnerUsername(d), slug: d.slug } }"
          >
            <i class="bi bi-eye" aria-hidden="true"></i>{{ t('dashboard.preview', 'Preview') }}
          </router-link>
          <router-link
            class="ui-button ui-button--secondary"
            :to="`/dashboard/${d.id}/edit`"
          >
            <i class="bi bi-pencil" aria-hidden="true"></i>{{ isOwner(d) ? t('dashboard.edit', 'Edit') : t('dashboard.view', 'View') }}
          </router-link>
          <UiButton v-if="isOwner(d)" variant="danger" class="dashboard-delete"
            :title="t('dashboard.delete', 'Delete')" :aria-label="t('dashboard.delete', 'Delete')" @click="confirmDelete(d)">
            <i class="bi bi-trash" aria-hidden="true"></i><span class="visually-hidden">{{ t('dashboard.delete', 'Delete') }}</span>
          </UiButton>
        </div>
      </article>
    </div>

    <UiDialog v-if="showModal" :open="showModal"
      :title="t('dashboard.createNew', 'Create New Dashboard')" :close-label="label('close')"
      @update:open="!$event && closeModal()" @click="closeOnBackdrop($event, closeModal)">
      <form :id="formId" @submit.prevent="createDisplay" class="modal-form ui-stack">
        <label class="ui-field">
          <span>{{ t('dashboard.titleLabel', 'Title') }}</span>
          <input type="text" class="ui-control" v-model="title" autofocus
            :placeholder="t('dashboard.titlePlaceholder', 'Dashboard title')" required />
        </label>
        <label class="ui-field">
          <span>{{ t('dashboard.slugLabel', 'Slug') }}</span>
          <input type="text" class="ui-control" v-model="slug"
            :placeholder="t('dashboard.slugPlaceholder', 'dashboard-slug')" :aria-describedby="`${formId}-url`" required />
        </label>
        <p :id="`${formId}-url`" class="ui-help dashboard-url">{{ t('dashboard.urlLabel', 'URL') }}: /@{{ currentUsername }}/{{ slug || 'dashboard-slug' }}</p>
        <label class="ui-check"><input type="checkbox" v-model="isPublic" />
          <span>{{ t('dashboard.makePublic', 'Make dashboard public') }}</span>
        </label>
      </form>
      <template #actions>
        <UiButton @click="closeModal">{{ t('common.cancel', 'Cancel') }}</UiButton>
        <UiButton variant="primary" type="submit" :form="formId">
          <i class="bi bi-plus-lg" aria-hidden="true"></i>{{ t('dashboard.create', 'Create') }}
        </UiButton>
      </template>
    </UiDialog>

    <UiDialog v-if="showDeleteModal" v-model:open="showDeleteModal"
      :title="t('dashboard.confirmDelete', 'Confirm Delete')" :close-label="label('close')"
      @click="closeOnBackdrop($event, () => { showDeleteModal = false })">
      <div class="ui-stack">
        <p class="dashboard-delete-message">{{ t('dashboard.confirmDeleteMessage', 'Are you sure you want to delete the dashboard') }} "{{ dashboardToDelete?.title || dashboardToDelete?.name }}"?</p>
        <p class="dashboard-warning"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
          {{ t('dashboard.deleteWarning', 'This action cannot be undone. All widgets in this dashboard will be deleted.') }}
        </p>
      </div>
      <template #actions>
        <UiButton autofocus @click="showDeleteModal = false">{{ t('common.cancel', 'Cancel') }}</UiButton>
        <UiButton variant="danger" @click="deleteDisplay">
          <i class="bi bi-trash" aria-hidden="true"></i>{{ t('dashboard.delete', 'Delete') }}
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<style scoped>
.dashboard-view { background: transparent; }
.dashboard-heading { gap: calc(var(--ui-space) * 4); margin-bottom: calc(var(--ui-space) * 8); padding: 0; text-align: left; }
.dashboard-heading h1 { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.dashboard-create { flex-shrink: 0; }
.dashboard-section-heading { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); margin-bottom: calc(var(--ui-space) * 4); }
.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: calc(var(--ui-space) * 5);
}
.dashboard-card {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ui-space) * 4);
}
.dashboard-title {
  margin: 0;
  font-size: 1.15em;
  line-height: 1.4;
  font-weight: 650;
  color: var(--ui-text);
  overflow-wrap: anywhere;
}
.dashboard-details { display: grid; gap: calc(var(--ui-space) * 2); margin: 0; }
.dashboard-details > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: calc(var(--ui-space) * 3); }
.dashboard-details dt { color: var(--ui-text-muted); font-weight: 400; font-size: .9em; }
.dashboard-details dd { margin: 0; color: var(--ui-text-secondary); font-size: .9em; overflow-wrap: anywhere; }
.dashboard-slug { font-family: ui-monospace, Consolas, monospace; }
.dashboard-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr)) auto;
  gap: calc(var(--ui-space) * 2);
  margin-top: auto;
  padding-top: calc(var(--ui-space) * 4);
  border-top: 1px solid var(--ui-border);
}
.dashboard-actions > .ui-button { min-width: 0; padding-inline: calc(var(--ui-space) * 2); overflow-wrap: anywhere; }
.dashboard-actions > .dashboard-delete { min-width: var(--ui-control-height); }
.dashboard-empty { display: grid; justify-items: center; gap: calc(var(--ui-space) * 4); text-align: center; padding-block: calc(var(--ui-space) * 12); }
.dashboard-empty > i { font-size: 2rem; color: var(--ui-accent); }
.dashboard-warning { color: var(--ui-danger); }
.dashboard-url, .dashboard-delete-message { overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .dashboard-heading { align-items: stretch; flex-direction: column; }
  .dashboard-actions > a .bi { display: none; }
  .dashboard-actions > .dashboard-delete { min-width: 44px; }
}
</style>
