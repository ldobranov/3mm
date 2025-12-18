<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useDisplaysStore } from '../stores/displays';
import { useWidgetsStore, type Widget } from '@/stores/widgets';
import { useSettingsStore } from '@/stores/settings';
import { useI18n } from '@/utils/i18n';
import DisplayCanvas from '@/components/DisplayCanvas.vue';
import WidgetPalette from '@/components/WidgetPalette.vue';
import EditorPanel from '@/components/EditorPanel.vue';

const route = useRoute();
const displayId = Number(route.params.id);
const displays = useDisplaysStore();
const widgets = useWidgetsStore();
const settingsStore = useSettingsStore();
const { t } = useI18n();
const styleSettings = computed(() => settingsStore.styleSettings);

const items = computed(() => widgets.list(displayId));
const loading = ref(true);
const error = ref<string | null>(null);

// Preview route params - use the dashboard owner's username, not the current user's
const previewUsername = computed(() => {
  // Use owner_username from the display data (set by backend)
  if (displays.active?.owner_username) {
    return displays.active.owner_username;
  }
  
  // Fallback to current user's username if owner_username is not available
  const directUsername = localStorage.getItem('username');
  if (directUsername) return directUsername;
  
  // Final fallback to user object if exists
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null');
    if (u && typeof u.username === 'string' && u.username) return u.username;
  } catch {}
  
  return '';
});
const previewSlug = computed(() => displays.active?.slug || '');

// Debug computed to check values
const debugInfo = computed(() => {
  console.log('Preview Debug:', {
    username: previewUsername.value,
    slug: previewSlug.value,
    active: displays.active
  });
  return { username: previewUsername.value, slug: previewSlug.value };
});

const showEditor = ref(false);
const selectedWidget = ref<Widget | null>(null);

// Dashboard settings modal state
const showSettings = ref(false);
const settings = ref<{ title: string; slug: string; is_public: boolean }>({ title: '', slug: '', is_public: false });

function openSettings() {
  const a = displays.active;
  if (!a) return;
  settings.value = { title: a.title || '', slug: a.slug || '', is_public: !!a.is_public };
  showSettings.value = true;
}

async function saveSettings() {
  const a = displays.active;
  if (!a) return;
  await displays.update(a.id, { title: settings.value.title, slug: settings.value.slug, is_public: settings.value.is_public });
  // Refresh active display
  await displays.getById(displayId);
  showSettings.value = false;
}

function handleSettingsKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && showSettings.value) {
    e.stopPropagation();
    showSettings.value = false;
  } else if (e.key === 'Enter' && showSettings.value && !e.shiftKey) {
    // Don't submit if focus is on textarea (for future use)
    const target = e.target as HTMLElement;
    if (target.tagName !== 'TEXTAREA') {
      e.preventDefault();
      saveSettings();
    }
  }
}

// Snapshot original configs to allow cancel
const originalConfigs = new Map<number, any>();

onMounted(async () => {
  try {
    loading.value = true;
    error.value = null;

    // Validate displayId
    if (!displayId || isNaN(displayId) || displayId <= 0) {
      throw new Error(`Invalid display ID: ${route.params.id}`);
    }

    console.log('Loading display:', displayId);
    await displays.getById(displayId);
    console.log('Display loaded, loading widgets...');
    await widgets.fetchForDisplay(displayId);
    console.log('Widgets loaded successfully');
  } catch (err: any) {
    console.error('Error loading display editor:', err);
    error.value = err.message || 'Failed to load display';
  } finally {
    loading.value = false;
  }

  // Add keyboard listener for settings modal
  window.addEventListener('keydown', handleSettingsKeydown);
});

// Clean up event listener
import { onBeforeUnmount } from 'vue';
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleSettingsKeydown);
});

function openEditor(id: number) {
  const w = items.value.find(x => x.id === id) || null;
  selectedWidget.value = w;
  if (w) {
    // Store the current config from the store, not the potentially modified local config
    const currentWidget = widgets.byDisplayId[displayId]?.find(wgt => wgt.id === id);
    originalConfigs.set(w.id, JSON.parse(JSON.stringify(currentWidget?.config || {})));
  }
  showEditor.value = !!w;
}

async function handleLayoutChanged(changes: Array<{ id: number; x: number; y: number; width: number; height: number; z_index: number }>) {
  await widgets.bulkLayout(changes);
}

async function addWidget(type: Widget['type']) {
  // For extension widgets, use default config from extension or empty object
  let config = {};
  if (type.startsWith('extension:')) {
    config = {}; // Extensions can define their own defaults in manifest
  }

  await widgets.create(displayId, { type, config, x: 0, y: 0, width: 3, height: 2, z_index: 1 });
}

async function handleDeleteWidget(id: number) {
  await widgets.remove(id);
  originalConfigs.delete(id);
}

function handleEditWidget(id: number) {
  openEditor(id);
}

// PREVIEW: optimistic local update (no network)
function handlePreview(payload: { id: number; config: any }) {
  const dId = displayId;
  const arr = widgets.byDisplayId[dId] || [];
  const idx = arr.findIndex(w => w.id === payload.id);
  if (idx >= 0) {
    const updated = { ...arr[idx], config: { ...(payload.config || {}) } };
    // create a new array reference
    widgets.byDisplayId[dId] = [
      ...arr.slice(0, idx),
      updated,
      ...arr.slice(idx + 1),
    ];
  }
}

// SAVE: persist to backend
async function handleSaveEdit(payload: { id: number; config: any }) {
  await widgets.update(payload.id, { config: payload.config });
  originalConfigs.delete(payload.id);
}

// CANCEL: restore original config snapshot
function handleCancelEdit(id: number) {
  const orig = originalConfigs.get(id);
  if (orig) {
    handlePreview({ id, config: orig });
  }
  originalConfigs.delete(id);
}

function handleAddFromDrop(payload: { type: Widget['type']; x: number; y: number; width: number; height: number }) {
  // For extension widgets, use default config from extension or empty object
  let config = {};
  if (payload.type.startsWith('extension:')) {
    config = {}; // Extensions can define their own defaults in manifest
  }

  return widgets.create(displayId, {
    type: payload.type,
    x: payload.x,
    y: payload.y,
    width: payload.width,
    height: payload.height,
    z_index: 1,
    config,
  });
}
</script>

<template>
  <div class="view">
    <div v-if="loading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
      {{ t('dashboard.editor.loading') }}
    </div>

    <div v-else-if="error" class="text-center" style="padding: 2rem 0;">
      <div class="alert alert-error">
        <i class="bi bi-exclamation-triangle"></i>
        {{ t('dashboard.editor.errorLoading') }}: {{ error }}
      </div>
    </div>

    <div v-else>
      <!-- Header Section -->
      <div class="card editor-header-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }">
        <div class="header-content">
          <div class="header-info">
            <h1 class="view-title">
              <i class="bi bi-pencil-square"></i>
              {{ t('dashboard.editor.editTitle') }}: {{ displays.active?.title }}
            </h1>
            <div class="header-meta">
              <span class="meta-item">
                <i class="bi bi-link-45deg"></i>
                <strong>{{ t('dashboard.editor.slugLabel') }}</strong> /{{ displays.active?.slug }}
              </span>
              <span class="meta-item">
                <i :class="displays.active?.is_public ? 'bi bi-globe' : 'bi bi-lock'"></i>
                {{ displays.active?.is_public ? t('dashboard.editor.publicLabel') : t('dashboard.editor.privateLabel') }}
              </span>
            </div>
          </div>
          <div class="header-actions">
            <RouterLink
              v-if="previewUsername && previewSlug"
              class="button button-outline"
              :to="{ name: 'PublicDisplay', params: { username: previewUsername, slug: previewSlug } }"
              target="_blank"
            >
              <i class="bi bi-eye"></i>
              {{ t('dashboard.editor.previewButton') }}
            </RouterLink>
            <button
              class="button button-outline"
              @click="openSettings"
            >
              <i class="bi bi-gear"></i>
              {{ t('dashboard.editor.settingsButton') }}
            </button>
          </div>
        </div>
      </div>

    <!-- Widget Palette -->
    <div class="card palette-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }" style="margin-bottom: 1.5rem;">
      <h5 class="card-title">
        <i class="bi bi-plus-square"></i>
        {{ t('dashboard.editor.addWidgetsTitle') }}
      </h5>
      <WidgetPalette @add="addWidget" />
    </div>

    <!-- Canvas Area -->
    <div class="card canvas-card" :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }" style="min-height: 500px;">
      <DisplayCanvas
        :widgets="items"
        :editable="true"
        @layoutChanged="handleLayoutChanged"
        @deleteWidget="handleDeleteWidget"
        @editWidget="handleEditWidget"
        @addFromDrop="handleAddFromDrop"
      />
    </div>
    </div>

    <EditorPanel
      v-model="showEditor"
      :widget="selectedWidget"
      @preview="handlePreview"
      @save="handleSaveEdit"
      @cancel="handleCancelEdit"
    />
  </div>

  <!-- Dashboard Settings Modal -->
  <teleport to="body">
    <div v-if="showSettings">
      <!-- backdrop -->
      <div 
        class="modal-backdrop"
        @click="showSettings=false"
      ></div>
      
      <!-- dialog centered -->
      <div class="modal-container">
        <div
          class="modal-surface modal-lg"
          role="dialog"
          aria-modal="true"
          @click.stop
          :style="{ backgroundColor: styleSettings.cardBg, color: styleSettings.textPrimary, borderColor: styleSettings.cardBorder }"
        >
          <div style="display:flex; align-items:center; justify-content:space-between; padding-bottom:0.5rem; border-bottom:1px solid var(--card-border);">
            <div class="view-subtitle" style="margin:0;">{{ t('dashboard.editor.dashboardSettingsTitle') }}</div>
            <button
              class="button button-outline button-sm"
              type="button"
              @click.stop="showSettings=false"
            >
              ×
            </button>
          </div>

          <div class="modal-content">
            <div class="form-group">
              <label class="form-label">{{ t('dashboard.editor.titleField') }}</label>
              <input
                type="text"
                class="input"
                v-model="settings.title"
                :placeholder="t('dashboard.titlePlaceholder')"
              />
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('dashboard.editor.slugField') }}</label>
              <input
                type="text"
                class="input"
                v-model="settings.slug"
                :placeholder="t('dashboard.slugPlaceholder')"
              />
            </div>
            <div class="form-group">
              <label class="checkbox-label">
                <input
                  type="checkbox"
                  class="input"
                  v-model="settings.is_public"
                />
                <span>{{ t('dashboard.editor.makePublicCheckbox') }}</span>
              </label>
            </div>
          </div>

          <div class="modal-actions">
            <button
              class="button button-secondary"
              type="button"
              @click.stop="showSettings=false"
            >
              {{ t('dashboard.editor.cancelButton') }}
            </button>
            <button
              class="button button-primary"
              type="button"
              @click.stop="saveSettings"
            >
              {{ t('dashboard.editor.saveButton') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
/* Display Editor styles */
.editor-header-card {
  margin-bottom: 1.5rem;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.editor-header-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.header-info {
  flex: 1;
}

.view-title {
  margin: 0 0 0.5rem 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.view-title i {
  color: var(--text-secondary);
}

.header-meta {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 0.9rem;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.meta-item i {
  color: var(--text-secondary);
}

.header-actions {
  display: flex;
  gap: 0.75rem;
}

.palette-card,
.canvas-card {
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s ease;
}

.palette-card:hover,
.canvas-card:hover {
  box-shadow: var(--card-hover-shadow);
}

.card-title {
  margin: 0 0 1rem 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.card-title i {
  color: var(--text-secondary);
}

.modal-content {
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

.checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  color: var(--text-primary);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  border-top: 1px solid var(--card-border);
  padding-top: 0.5rem;
}
</style>