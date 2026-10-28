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
import UiButton from '@/components/ui/UiButton.vue';
import UiDialog from '@/components/ui/UiDialog.vue';

const route = useRoute();
const displayId = Number(route.params.id);
const displays = useDisplaysStore();
const widgets = useWidgetsStore();
const settingsStore = useSettingsStore();
const { t } = useI18n();
const design = computed(() => settingsStore.uiDesign);

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
const editSaving = ref(false);
const editError = ref('');
const operationError = ref('');
const widgetSelector = ref<HTMLSelectElement>();

// Dashboard settings modal state
const showSettings = ref(false);
const settingsSaving = ref(false);
const settingsError = ref('');
const settings = ref<{ title: string; slug: string; is_public: boolean }>({ title: '', slug: '', is_public: false });

function openSettings() {
  const a = displays.active;
  if (!a) return;
  settings.value = { title: a.title || '', slug: a.slug || '', is_public: !!a.is_public };
  settingsError.value = '';
  showSettings.value = true;
}

async function saveSettings() {
  const a = displays.active;
  if (!a || settingsSaving.value) return;
  settingsSaving.value = true;
  settingsError.value = '';
  try {
    await displays.update(a.id, { title: settings.value.title, slug: settings.value.slug, is_public: settings.value.is_public });
    await displays.getById(displayId);
    showSettings.value = false;
  } catch (err) {
    settingsError.value = err instanceof Error ? err.message : String(err);
  } finally { settingsSaving.value = false; }
}

function handleSettingsBackdrop(event: MouseEvent) {
  if (settingsSaving.value || event.target !== event.currentTarget) return;
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) showSettings.value = false;
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

});

function openEditor(id: number) {
  if (editSaving.value || (showEditor.value && selectedWidget.value?.id === id)) return;
  if (showEditor.value && selectedWidget.value) handleCancelEdit(selectedWidget.value.id);
  const w = items.value.find(x => x.id === id) || null;
  selectedWidget.value = w;
  editError.value = '';
  if (w) {
    // Store the current config from the store, not the potentially modified local config
    const currentWidget = widgets.byDisplayId[displayId]?.find(wgt => wgt.id === id);
    originalConfigs.set(w.id, JSON.parse(JSON.stringify(currentWidget?.config || {})));
  }
  showEditor.value = !!w;
}

function selectWidget(event: Event) {
  openEditor(Number((event.target as HTMLSelectElement).value));
}

function setEditorOpen(open: boolean) {
  showEditor.value = open;
  if (!open) widgetSelector.value?.focus();
}

function widgetLabel(widget: Widget) {
  return String(widget.config?.title || widget.config?.name || `${widget.type} · #${widget.id}`);
}

async function runMutation(action: () => Promise<unknown>) {
  operationError.value = '';
  try { await action(); }
  catch (err) { operationError.value = err instanceof Error ? err.message : String(err); }
}

async function handleLayoutChanged(changes: Array<{ id: number; x: number; y: number; width: number; height: number; z_index: number }>) {
  await runMutation(() => widgets.bulkLayout(changes));
}

async function addWidget(type: Widget['type']) {
  // For extension widgets, use default config from extension or empty object
  let config = {};
  if (type.startsWith('extension:')) {
    config = {}; // Extensions can define their own defaults in manifest
  }

  await runMutation(() => widgets.create(displayId, { type, config, x: 0, y: 0, width: 3, height: 2, z_index: 1 }));
}

async function handleDeleteWidget(id: number) {
  if (editSaving.value) return;
  await runMutation(async () => {
    await widgets.remove(id);
    originalConfigs.delete(id);
    if (selectedWidget.value?.id === id) { showEditor.value = false; selectedWidget.value = null; }
  });
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
  if (editSaving.value) return;
  editSaving.value = true;
  editError.value = '';
  try {
    await widgets.update(payload.id, { config: payload.config });
    originalConfigs.delete(payload.id);
    showEditor.value = false;
    widgetSelector.value?.focus();
  } catch (err) {
    editError.value = err instanceof Error ? err.message : String(err);
  } finally { editSaving.value = false; }
}

// CANCEL: restore original config snapshot
function handleCancelEdit(id: number) {
  const orig = originalConfigs.get(id);
  if (orig) {
    handlePreview({ id, config: orig });
  }
  originalConfigs.delete(id);
  editError.value = '';
}

function handleAddFromDrop(payload: { type: Widget['type']; x: number; y: number; width: number; height: number }) {
  // For extension widgets, use default config from extension or empty object
  let config = {};
  if (payload.type.startsWith('extension:')) {
    config = {}; // Extensions can define their own defaults in manifest
  }

  return runMutation(() => widgets.create(displayId, {
    type: payload.type,
    x: payload.x,
    y: payload.y,
    width: payload.width,
    height: payload.height,
    z_index: 1,
    config,
  }));
}
</script>

<template>
  <div class="display-editor-view ui-v2" :data-card="design.components.card" :data-button="design.components.button">
    <div v-if="loading" class="workspace-status" role="status">
      <span class="ui-spinner" aria-hidden="true"></span>{{ t('dashboard.editor.loading', 'Loading dashboard…') }}
    </div>
    <div v-else-if="error" class="ui-error workspace-status" role="alert">
      {{ t('dashboard.editor.errorLoading', 'Could not load dashboard') }}: {{ error }}
    </div>
    <template v-else>
      <header class="workspace-header">
        <div class="workspace-heading">
          <p class="workspace-eyebrow">{{ t('dashboard.editor.editTitle', 'Edit dashboard') }}</p>
          <h1>{{ displays.active?.title }}</h1>
          <div class="workspace-meta">
            <span>/{{ displays.active?.slug }}</span>
            <span><i :class="displays.active?.is_public ? 'bi bi-globe' : 'bi bi-lock'" aria-hidden="true"></i>
              {{ displays.active?.is_public ? t('dashboard.editor.publicLabel', 'Public') : t('dashboard.editor.privateLabel', 'Private') }}
            </span>
          </div>
        </div>
        <div class="workspace-actions">
          <RouterLink v-if="previewUsername && previewSlug" class="ui-button ui-button--secondary"
            :to="{ name: 'PublicDisplay', params: { username: previewUsername, slug: previewSlug } }"
            target="_blank" rel="noopener">
            <i class="bi bi-eye" aria-hidden="true"></i>{{ t('dashboard.editor.previewButton', 'Preview') }}
          </RouterLink>
          <UiButton @click="openSettings"><i class="bi bi-gear" aria-hidden="true"></i>{{ t('dashboard.editor.settingsButton', 'Settings') }}</UiButton>
        </div>
      </header>
      <p v-if="operationError" class="ui-error" role="alert">{{ operationError }}</p>
      <div class="editor-workspace">
        <section class="ui-section workspace-palette" aria-labelledby="workspace-palette-title">
          <h2 id="workspace-palette-title">{{ t('dashboard.editor.addWidgetsTitle', 'Add widgets') }}</h2>
          <p class="ui-help">{{ t('dashboard.editor.paletteHint', 'Select a widget to add it, or drag it onto the canvas.') }}</p>
          <WidgetPalette @add="addWidget" />
        </section>
        <section class="ui-section workspace-canvas" aria-labelledby="workspace-canvas-title">
          <div class="canvas-heading">
            <h2 id="workspace-canvas-title">{{ t('dashboard.editor.canvasTitle', 'Canvas') }}</h2>
            <span class="widget-count">{{ items.length }} {{ t('dashboard.editor.widgetCount', 'widgets') }}</span>
          </div>
          <p class="ui-help">{{ t('dashboard.editor.canvasHint', 'Move or resize widgets here. Select one to edit its properties.') }}</p>
          <p class="canvas-mobile-hint ui-help">{{ t('dashboard.editor.canvasScrollHint', 'Scroll the canvas sideways to see all widgets.') }}</p>
          <p v-if="!items.length" class="canvas-empty" role="status">{{ t('dashboard.editor.emptyCanvas', 'Add your first widget from the palette.') }}</p>
          <div class="canvas-scroll">
            <DisplayCanvas :widgets="items" :editable="true" @layoutChanged="handleLayoutChanged"
              @deleteWidget="handleDeleteWidget" @editWidget="handleEditWidget" @addFromDrop="handleAddFromDrop" />
          </div>
        </section>
        <section class="ui-section workspace-inspector" aria-labelledby="workspace-inspector-title">
          <h2 id="workspace-inspector-title">{{ t('dashboard.editor.propertiesTitle', 'Properties') }}</h2>
          <label class="ui-field widget-selection">
            <span>{{ t('dashboard.editor.selectWidget', 'Select widget') }}</span>
            <select ref="widgetSelector" class="ui-control" :value="showEditor ? selectedWidget?.id : ''"
              :disabled="!items.length || editSaving" @change="selectWidget">
              <option value="">{{ t('dashboard.editor.chooseWidget', 'Choose a widget…') }}</option>
              <option v-for="widget in items" :key="widget.id" :value="widget.id">{{ widgetLabel(widget) }}</option>
            </select>
          </label>
          <EditorPanel :model-value="showEditor" @update:modelValue="setEditorOpen" :widget="selectedWidget" :saving="editSaving" :error="editError"
            @preview="handlePreview" @save="handleSaveEdit" @cancel="handleCancelEdit" />
        </section>
      </div>
    </template>
    <UiDialog v-if="showSettings" :open="showSettings" :title="t('dashboard.editor.dashboardSettingsTitle', 'Dashboard settings')"
      :close-label="t('common.close', 'Close')" @click="handleSettingsBackdrop" @update:open="value => { if (!settingsSaving) showSettings = value }">
      <form id="display-settings-form" class="dashboard-settings-form" @submit.prevent="saveSettings">
        <label class="ui-field">
          <span>{{ t('dashboard.editor.titleField', 'Title') }}</span>
          <input v-model="settings.title" class="ui-control" type="text" required autofocus :disabled="settingsSaving"
            :placeholder="t('dashboard.titlePlaceholder', 'Dashboard title')" />
        </label>
        <label class="ui-field">
          <span>{{ t('dashboard.editor.slugField', 'Slug') }}</span>
          <input v-model="settings.slug" class="ui-control" type="text" required :disabled="settingsSaving"
            :placeholder="t('dashboard.slugPlaceholder', 'dashboard-slug')" />
        </label>
        <label class="ui-check"><input v-model="settings.is_public" type="checkbox" :disabled="settingsSaving" />
          <span>{{ t('dashboard.editor.makePublicCheckbox', 'Make public') }}</span>
        </label>
        <p v-if="settingsError" class="ui-error" role="alert">{{ settingsError }}</p>
      </form>
      <template #actions>
        <UiButton :disabled="settingsSaving" @click="showSettings = false">{{ t('dashboard.editor.cancelButton', 'Cancel') }}</UiButton>
        <UiButton variant="primary" type="submit" form="display-settings-form" :loading="settingsSaving">{{ t('dashboard.editor.saveButton', 'Save') }}</UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<style scoped>
.display-editor-view { min-width: 0; padding: calc(var(--ui-space) * 5); }
.workspace-header, .workspace-actions, .workspace-meta, .canvas-heading { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); }
.workspace-header { justify-content: space-between; flex-wrap: wrap; margin-bottom: calc(var(--ui-space) * 5); padding: 0; text-align: left; }
.workspace-heading { flex: 1; min-width: 0; }
.workspace-eyebrow { margin: 0 0 calc(var(--ui-space) * 1); color: var(--ui-text-muted); font-size: .875em; }
.workspace-heading h1 { margin: 0; font-size: clamp(1.5rem, 3vw, 2rem); font-weight: 650; overflow-wrap: anywhere; text-align: left; }
.workspace-meta { flex-wrap: wrap; margin-top: calc(var(--ui-space) * 2); color: var(--ui-text-muted); font-size: .875em; overflow-wrap: anywhere; }
.workspace-actions { flex-wrap: wrap; }
.editor-workspace { display: grid; grid-template-columns: 11rem minmax(0, 1fr) 19rem; gap: calc(var(--ui-space) * 4); align-items: start; }
.editor-workspace > section { min-width: 0; padding: calc(var(--ui-space) * 4); }
.editor-workspace h2 { margin: 0 0 calc(var(--ui-space) * 3); font-size: 1.08rem; font-weight: 650; }
.workspace-status { padding: calc(var(--ui-space) * 6); display: flex; gap: calc(var(--ui-space) * 3); align-items: center; justify-content: center; }
.canvas-heading { justify-content: space-between; flex-wrap: wrap; }
.canvas-heading h2 { margin: 0; }
.widget-count { color: var(--ui-text-muted); font-size: .875em; }
.workspace-canvas > .ui-help { margin-top: calc(var(--ui-space) * 3); }
.workspace-palette > .ui-help, .workspace-canvas > .ui-help { margin-bottom: calc(var(--ui-space) * 3); }
.canvas-scroll { min-height: 28rem; overflow-x: auto; border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-lg); background: var(--ui-surface-alt); }
.canvas-empty { color: var(--ui-text-muted); font-size: .875em; }
.canvas-mobile-hint { display: none; }
.widget-selection { margin-bottom: calc(var(--ui-space) * 4); }
.dashboard-settings-form { display: grid; gap: calc(var(--ui-space) * 4); margin-top: calc(var(--ui-space) * 4); }
:deep(.grid-stack-item-content) { border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); }
:deep(.widget-toolbar) { opacity: 1; background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
:deep(.widget-toolbar button) { color: var(--ui-text); min-height: 2rem; min-width: 2rem; }
:deep(.widget-toolbar button:hover), :deep(.widget-toolbar button:focus-visible) { background: var(--ui-surface-alt); color: var(--ui-text); }
@media (max-width: 1200px) and (min-width: 901px) {
  .editor-workspace { grid-template-columns: minmax(0, 1fr) 18rem; }
  .workspace-palette { grid-column: 1 / -1; }
  :deep(.widget-palette) { grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); }
}
@media (max-width: 900px) {
  .editor-workspace { grid-template-columns: minmax(0, 1fr); }
  .display-editor-view { padding: calc(var(--ui-space) * 3); }
  .workspace-header { flex-direction: column; align-items: stretch; }
  .canvas-scroll { min-height: 18rem; }
  .canvas-mobile-hint { display: block; }
  .canvas-scroll :deep(.grid-stack) { min-width: 600px; }
  :deep(.widget-toolbar button) { min-height: 2.75rem; min-width: 2.75rem; }
}
</style>
