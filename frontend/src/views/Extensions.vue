<template>
  <div class="view extensions-view ui-v2" :key="currentLanguage"
    :data-card="settingsStore.uiDesign.components.card"
    :data-button="settingsStore.uiDesign.components.button">
    <div class="view-header">
      <h1 class="view-title">{{ t('extensions.title', 'Extensions') }}</h1>

      <div v-if="isAdmin" class="header-actions">
        <router-link class="ui-button ui-button--secondary ai-builder-link" to="/extensions/ai-builder">
          <i class="bi bi-stars" aria-hidden="true"></i>
          {{ t('extensions.aiBuilder.open', 'Open AI Builder') }}
        </router-link>
      </div>
    </div>

    <!-- Upload Section -->
    <div v-if="isAdmin" class="ui-section upload-section">
      <div class="card-content">
        <div class="section-heading">
          <span class="section-heading-icon" aria-hidden="true">
            <i class="bi bi-file-earmark-arrow-up"></i>
          </span>
          <h2>{{ t('extensions.uploadExtension', 'Upload Extension') }}</h2>
        </div>
        <form @submit.prevent="uploadExtension" class="upload-form">
          <label for="extension-file" class="upload-picker">
            <span class="upload-picker-icon" aria-hidden="true"><i class="bi bi-file-earmark-zip"></i></span>
            <span class="upload-picker-copy">
              <strong>{{ selectedFile?.name || t('extensions.extensionFile', 'Extension File (.zip)') }}</strong>
              <small>.zip</small>
            </span>
            <input
              id="extension-file"
              class="upload-file-input"
              type="file"
              accept=".zip"
              @change="handleFileSelect"
              required
            />
          </label>
          <UiButton type="submit" :disabled="!selectedFile || uploading" variant="primary" class="upload-btn" :loading="uploading">
            <i class="bi bi-upload" aria-hidden="true"></i>
            {{ uploading ? t('extensions.uploading', 'Uploading...') : t('extensions.uploadExtensionButton', 'Upload Extension') }}
          </UiButton>
        </form>
        <PackageInspection :file="selectedFile" :disabled="uploading" />
        <div v-if="uploadError" class="error-message" role="alert">{{ uploadError }}</div>
        <div v-if="uploadSuccess" class="success-message" role="status">{{ uploadSuccess }}</div>
      </div>
    </div>

    <!-- Extensions List -->
    <section class="extensions-list">
      <div class="extensions-list-content">
        <div class="extensions-list-heading">
          <div class="section-heading">
            <span class="section-heading-icon" aria-hidden="true">
              <i class="bi bi-boxes"></i>
            </span>
            <h2>{{ t('extensions.installedExtensions', 'Extensions') }}</h2>
          </div>
          <span v-if="!loading" class="ui-badge extension-count">{{ extensions.length }}</span>
        </div>
        <div v-if="operationError" class="error-message" role="alert">{{ operationError }}</div>
        <div v-if="loading" class="ui-section loading" role="status">{{ t('extensions.loadingExtensions', 'Loading extensions...') }}</div>
        <div v-else-if="extensions.length === 0" class="ui-section no-extensions" role="status">
          {{ t('extensions.noExtensionsInstalled', 'No extensions installed yet.') }}
        </div>
        <div v-else class="extensions-grid">
          <div
            v-for="ext in extensions"
            :key="ext.id"
            class="ui-section extension-card"
          >
            <div class="extension-header">
              <h3>{{ ext.name }}</h3>
              <span class="ui-badge extension-version">{{ t('extensions.version', 'v') }} {{ ext.version }}</span>
            </div>
            <div class="extension-meta">
              <span v-if="ext.source !== 'theme'" class="ui-badge extension-type">{{ ext.type }}</span>
              <span v-if="ext.source !== 'legacy'" class="ui-badge runtime-badge">{{ extensionSourceLabel(ext) }}</span>
              <span v-if="ext.author" class="extension-author">{{ t('extensions.by', 'by') }} {{ ext.author }}</span>
            </div>
            <p v-if="ext.description" class="extension-description">{{ ext.description }}</p>
            <div class="extension-status">
              <span :class="['ui-badge status-badge', ext.status]">
                {{ extensionStatusLabel(ext) }}
              </span>
              <span v-if="ext.is_selected" class="selected-theme">{{ t('themePackages.selected', 'Selected') }}</span>
              <label
                class="toggle-switch"
                :aria-label="`${ext.name}: ${extensionStatusLabel(ext)}`"
              >
                <input
                  type="checkbox"
                  :checked="ext.is_enabled"
                  :aria-label="`${ext.name}: ${extensionStatusLabel(ext)}`"
                  :disabled="ext.source === 'compiled' || !ext.can_manage || (ext.source !== 'theme' && !ext.is_installed) || (ext.source === 'theme' && ext.status === 'unavailable' && !ext.is_enabled) || operationBusy === ext.id"
                  @change="toggleExtension(ext, $event)"
                />
                <span class="slider"></span>
              </label>
            </div>
            <p v-if="ext.source === 'theme'" class="theme-note">
              {{ ext.status === 'unavailable'
                ? t('themePackages.unavailableHelp', 'Package missing or invalid. Built-in settings are used if it was selected.')
                : t('themePackages.manageHelp', 'Enable this version, then choose it in Settings → Theme Customization. Enabling does not change the selected theme.') }}
            </p>
            <div v-if="ext.source !== 'compiled'" class="extension-actions">
               <div v-if="(ext.source === 'runtime' && ext.is_installed) || ext.source === 'application'" class="version-controls">
                 <label :for="`version-${ext.id}`">{{ t('extensions.version', 'Version') }}</label>
                 <select class="ui-control" :id="`version-${ext.id}`" v-model="selectedVersions[ext.id]">
                   <option v-for="version in ext.available_versions" :key="version" :value="version">
                     {{ version }}
                   </option>
                 </select>
                 <UiButton
                   type="button"
                   class="version-btn"
                   :disabled="!canActivateVersion(ext)"
                   @click="activateVersion(ext)"
                 >
                   {{ activatingVersion === ext.id
                     ? t('extensions.activatingVersion', 'Activating...')
                     : ext.source === 'application' && !ext.is_enabled
                       ? t('extensions.installApplication', 'Install and activate')
                       : t('extensions.activateVersion', 'Activate version') }}
                 </UiButton>
               </div>
               <div class="extension-action-footer">
                 <span v-if="(ext.source === 'runtime' || ext.source === 'application') && ext.is_installed" class="managed-note">
                   <i class="bi bi-database-check" aria-hidden="true"></i>
                   {{ t('extensions.runtimeDataPreserved', 'Data is preserved when disabled') }}
                 </span>
                 <div class="extension-action-buttons">
                   <UiButton v-if="isAdmin && ext.source === 'application' && ext.is_installed && ext.can_manage"
                     class="authority-manage-btn" :disabled="operationBusy !== null"
                     @click="authorityTarget = { moduleId: ext.id.replace('application:', ''), name: ext.name }">
                     <i class="bi bi-shield-check" aria-hidden="true"></i>{{ authorityLabel('manage') }}
                   </UiButton>
                   <UiButton
                     v-if="ext.source === 'runtime' && !ext.is_installed && ext.can_manage"
                     type="button"
                     class="version-btn"
                     :disabled="operationBusy === ext.id"
                     @click="reinstallExtension(ext)"
                   >
                     {{ operationBusy === ext.id
                       ? t('extensions.reinstalling', 'Reinstalling...')
                       : t('extensions.reinstall', 'Reinstall') }}
                   </UiButton>
                   <UiButton
                     v-if="ext.source === 'legacy' || (ext.source === 'runtime' && ext.is_installed && ext.can_manage) || ((ext.source === 'application' || ext.source === 'theme') && ext.can_manage)"
                     type="button"
                     @click="deleteExtension(ext)"
                     variant="danger" class="delete-btn"
                     :disabled="operationBusy === ext.id"
                   >
                     {{ ext.source === 'theme'
                       ? t('themePackages.delete', 'Delete')
                       : isUninstallAction(ext)
                       ? t('extensions.uninstall', 'Uninstall')
                       : ext.source === 'application'
                         ? t('extensions.deletePackage', 'Delete package')
                       : t('extensions.delete', 'Delete') }}
                   </UiButton>
                   <UiButton
                     v-if="ext.source === 'application' && !ext.is_installed && ext.can_manage"
                     type="button"
                     variant="danger" class="delete-btn"
                     :disabled="operationBusy === ext.id"
                     @click="eraseApplicationData(ext)"
                   >
                     {{ t('extensions.eraseData', 'Erase data') }}
                   </UiButton>
                 </div>
               </div>
             </div>
          </div>
        </div>
      </div>
    </section>

    <ApplicationAuthorityDialog v-if="isAdmin && authorityTarget" :key="authorityTarget.moduleId"
      :module-id="authorityTarget.moduleId" :name="authorityTarget.name"
      @close="authorityTarget = null" @changed="loadExtensions" />

    <!-- Application installation configuration -->
    <UiDialog v-if="showConfigurationModal" :open="showConfigurationModal"
      :title="t('extensions.configureApplication', 'Configure application')" :close-label="label('close')"
      @update:open="!$event && cancelApplicationConfiguration()"
      @click="closeOnBackdrop($event, cancelApplicationConfiguration)">
      <div class="modal-body ui-stack">
        <p>{{ t('extensions.configureApplicationHelp', 'Choose which managed device this application should use. The selection is preserved across updates.') }}</p>
        <div v-for="(field, index) in configurationFields" :key="field.key" class="ui-field configuration-field">
          <label :for="`application-config-${field.key}`">{{ field.label }}</label>
          <select
            class="ui-control" :autofocus="index === 0"
            :id="`application-config-${field.key}`"
            v-model="configurationValues[field.key]"
            :required="field.required"
          >
            <option value="" disabled>{{ t('extensions.selectDevice', 'Select a device') }}</option>
            <option v-for="device in configurationDevices" :key="device.device_id" :value="device.device_id">
              {{ device.display_name || device.device_id }} · {{ device.role }}
            </option>
          </select>
          <small v-if="field.description" class="ui-help">{{ field.description }}</small>
        </div>
        <div v-if="configurationDevices.length === 0" class="error-message" role="alert">
          {{ t('extensions.noDevicesAvailable', 'No active managed devices are available.') }}
        </div>
        <div v-if="configurationError" class="error-message" role="alert">{{ configurationError }}</div>
      </div>
      <template #actions>
        <UiButton :disabled="configurationSaving" @click="cancelApplicationConfiguration">
          {{ t('extensions.cancel', 'Cancel') }}
        </UiButton>
        <UiButton variant="primary" class="version-btn" :loading="configurationSaving" :disabled="!canSaveApplicationConfiguration" @click="confirmApplicationConfiguration">
          {{ configurationSaving
            ? t('extensions.activatingVersion', 'Activating...')
            : t('extensions.installApplication', 'Install and activate') }}
        </UiButton>
      </template>
    </UiDialog>

    <!-- Delete Extension Modal -->
    <UiDialog v-if="showDeleteModal" :open="showDeleteModal"
      :title="deleteAction === 'erase-data'
          ? t('extensions.eraseApplicationData', 'Erase application data')
          : extensionToDelete?.source === 'theme'
          ? t('themePackages.delete', 'Delete')
          : extensionToDelete && isUninstallAction(extensionToDelete)
          ? t('extensions.uninstallExtension', 'Uninstall Extension')
          : extensionToDelete?.source === 'application'
            ? t('extensions.deletePackage', 'Delete package')
          : t('extensions.deleteExtension', 'Delete Extension')" :close-label="label('close')"
      @update:open="!$event && closeDeleteDialog()"
      @click="closeOnBackdrop($event, closeDeleteDialog)">
      <div class="modal-body ui-stack">
        <p>{{ deleteAction === 'erase-data'
          ? t('extensions.eraseApplicationDataConfirm', 'Permanently erase all preserved data for this application? This cannot be undone, and reinstalling the package will start with an empty database.')
          : extensionToDelete?.source === 'theme'
          ? t('themePackages.confirmDelete', 'Delete this theme version? An active theme will return to built-in settings.')
          : extensionToDelete?.source === 'application' && extensionToDelete.is_installed
          ? t('extensions.uninstallApplicationConfirm', 'Uninstall this application extension? Its service, routes and access configuration will be removed. Its application data and uploaded package will be preserved.')
          : extensionToDelete?.source === 'application'
            ? t('extensions.deleteApplicationPackageConfirm', 'Delete this unused application package version? Preserved application data will not be deleted.')
          : extensionToDelete?.source === 'runtime'
            ? t('extensions.uninstallConfirm', 'Uninstall this runtime extension? Its routes and menu entries will be removed.')
          : t('extensions.deleteConfirm', 'Are you sure you want to delete this extension?') }}</p>
        <p><strong>{{ extensionToDelete?.name }}<template v-if="deleteAction !== 'erase-data'"> v{{ deleteTargetVersion(extensionToDelete) }}</template></strong></p>
        <div v-if="operationError" class="error-message" role="alert">{{ operationError }}</div>

        <!-- Database data deletion checkbox - only show if extension has tables -->
        <div v-if="extensionToDelete?.type === 'extension' || extensionToDelete?.source === 'runtime'" class="ui-stack">
          <label class="ui-check">
            <input type="checkbox" v-model="deleteDatabaseData" />
            {{ extensionToDelete?.source === 'runtime'
              ? t('extensions.deleteRuntimeData', 'Also permanently delete all data created by this extension')
              : t('extensions.deleteDatabaseData', 'Also delete all database tables and data created by this extension') }}
          </label>
          <small class="ui-help">{{ extensionToDelete?.source === 'runtime'
            ? (deleteDatabaseData
              ? t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All data will be permanently lost.')
              : t('extensions.preserveRuntimeData', 'Data will be preserved and becomes available after reinstalling the extension.'))
            : t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All selected data will be permanently lost.') }}</small>
        </div>

        <!-- Uploaded files deletion checkbox - only show if extension uploads files -->
        <div v-if="extensionToDelete?.type === 'extension'" class="ui-stack">
          <label class="ui-check">
            <input type="checkbox" v-model="deleteUploadedFiles" />
            {{ t('extensions.deleteUploadedFiles', 'Also delete all uploaded files (images, documents, etc.) for this extension') }}
          </label>
          <small class="ui-help">{{ t('extensions.deleteUploadedFilesWarning', 'This will remove all files uploaded by this extension from the server.') }}</small>
        </div>
      </div>
      <template #actions>
        <UiButton @click="closeDeleteDialog" autofocus :disabled="operationBusy !== null">
          {{ t('extensions.cancel', 'Cancel') }}
        </UiButton>
        <UiButton @click="confirmDeleteExtension" variant="danger" :loading="operationBusy !== null">
          {{ deleteAction === 'erase-data'
            ? t('extensions.eraseData', 'Erase data')
            : extensionToDelete?.source === 'theme'
            ? t('themePackages.delete', 'Delete')
            : extensionToDelete && isUninstallAction(extensionToDelete)
            ? t('extensions.uninstall', 'Uninstall')
            : extensionToDelete?.source === 'application'
              ? t('extensions.deletePackage', 'Delete package')
            : t('extensions.delete', 'Delete') }}
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import http from '@/utils/dynamic-http';
import { useI18n, i18n } from '@/utils/i18n';
import { useSettingsStore } from '@/stores/settings';
import { useThemeStore } from '@/stores/theme';
import { useRouter } from 'vue-router';
import { reloadRuntimeExtensionRoutes } from '@/utils/runtime-extensions';
import { getCompiledUiCatalog } from '@/utils/compiled-ui';
import { useUiLabels } from '@/utils/ui-labels';
import UiButton from '@/components/ui/UiButton.vue';
import UiDialog from '@/components/ui/UiDialog.vue';
import PackageInspection from '@/components/extensions/PackageInspection.vue';
import ApplicationAuthorityDialog from '@/components/extensions/ApplicationAuthorityDialog.vue';
import { useAuthorityLabels } from '@/components/extensions/authority-labels';

const { t, currentLanguage } = useI18n();
const settingsStore = useSettingsStore();
const themeStore = useThemeStore();
const router = useRouter();
const label = useUiLabels();
const authorityLabel = useAuthorityLabels();
const authorityTarget = ref<{ moduleId: string; name: string } | null>(null);


interface Extension {
  id: string;
  source: 'legacy' | 'runtime' | 'compiled' | 'application' | 'theme';
  name: string;
  type: string;
  version: string;
  description?: string;
  author?: string;
  status: string;
  is_enabled: boolean;
  created_at: string;
  can_manage: boolean;
  available_versions: string[];
  package_sha256?: string | null;
  package_sha256_by_version?: Record<string, string>;
  is_installed: boolean;
  is_selected?: boolean;
}

interface ThemeCatalogItem {
  module_id: string;
  version: string;
  sha256: string;
  name: { en: string; translations?: Record<string, string> };
  enabled: boolean;
  is_installed: boolean;
  is_selected: boolean;
  status: string;
}

interface ModulePackageCatalogItem {
  module_id: string;
  version: string;
  sha256: string;
  manifest: {
    name?: string;
    description?: string;
    entrypoints?: Record<string, string>;
  };
}

interface ApplicationInstallation {
  module_id: string;
  active_version: string | null;
  status: string;
  enabled: boolean;
}

interface ApplicationConfigurationField {
  key: string;
  kind: 'device';
  label: string;
  description?: string | null;
  required: boolean;
  value?: string | null;
}

interface ApplicationConfigurationDevice {
  device_id: string;
  display_name?: string | null;
  role: string;
}

const extensions = ref<Extension[]>([]);
const loading = ref(false);
const uploading = ref(false);
const selectedFile = ref<File | null>(null);
const uploadError = ref('');
const uploadSuccess = ref('');
const showDeleteModal = ref(false);
const extensionToDelete = ref<Extension | null>(null);
const deleteDatabaseData = ref(false);
const deleteUploadedFiles = ref(false);
const selectedVersions = ref<Record<string, string>>({});
const activatingVersion = ref<string | null>(null);
const operationBusy = ref<string | null>(null);
const operationError = ref('');
const deleteAction = ref<'remove' | 'erase-data'>('remove');
const showConfigurationModal = ref(false);
const configurationFields = ref<ApplicationConfigurationField[]>([]);
const configurationDevices = ref<ApplicationConfigurationDevice[]>([]);
const configurationValues = ref<Record<string, string>>({});
const configurationTarget = ref<{ extension: Extension; sha256: string } | null>(null);
const configurationSaving = ref(false);
const configurationError = ref('');

const isAdmin = computed(() => (localStorage.getItem('role') || '') === 'admin');

const canSaveApplicationConfiguration = computed(() =>
  configurationDevices.value.length > 0
  && configurationFields.value.every(field =>
    !field.required || Boolean(configurationValues.value[field.key]),
  ),
);

const authHeaders = () => {
  const token = localStorage.getItem('authToken') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const extensionSourceLabel = (extension: Extension): string => {
  if (extension.source === 'compiled') return 'Compiled UI';
  if (extension.source === 'application') return 'Application';
  if (extension.source === 'theme') return t('themePackages.kind', 'Theme');
  return 'Runtime';
};

const extensionStatusLabel = (extension: Extension): string =>
  t(`${extension.source === 'theme' ? 'themePackages' : 'extensions'}.${extension.status}`, extension.status);

const applicationPackageSha = (extension: Extension, version: string): string | null =>
  extension.package_sha256_by_version?.[version] || null;

const activateApplicationPackage = async (
  extension: Extension,
  sha256: string,
): Promise<boolean> => {
  const response = await http.get(
    `/api/v1/application-extensions/packages/${sha256}/configuration`,
  );
  const fields = Array.isArray(response.data?.fields)
    ? response.data.fields as ApplicationConfigurationField[]
    : [];
  if (fields.length === 0) {
    await http.post(`/api/v1/application-extensions/packages/${sha256}/activate`);
    return true;
  }
  configurationFields.value = fields;
  configurationDevices.value = Array.isArray(response.data?.devices)
    ? response.data.devices as ApplicationConfigurationDevice[]
    : [];
  configurationValues.value = Object.fromEntries(
    fields.map(field => [field.key, field.value || '']),
  );
  configurationTarget.value = { extension, sha256 };
  configurationError.value = '';
  showConfigurationModal.value = true;
  return false;
};

const cancelApplicationConfiguration = () => {
  if (configurationSaving.value) return;
  showConfigurationModal.value = false;
  configurationTarget.value = null;
  configurationFields.value = [];
  configurationDevices.value = [];
  configurationValues.value = {};
  configurationError.value = '';
};

const confirmApplicationConfiguration = async () => {
  if (!configurationTarget.value || !canSaveApplicationConfiguration.value) return;
  configurationSaving.value = true;
  configurationError.value = '';
  const target = configurationTarget.value;
  operationBusy.value = target.extension.id;
  try {
    await http.post(
      `/api/v1/application-extensions/packages/${target.sha256}/activate`,
      { configuration: { ...configurationValues.value } },
    );
    configurationSaving.value = false;
    cancelApplicationConfiguration();
    await getCompiledUiCatalog(true);
    window.dispatchEvent(new Event('menu-refresh'));
    await loadExtensions();
  } catch (error) {
    configurationError.value = errorMessage(
      error,
      t('extensions.versionError', 'Could not activate the selected version.'),
    );
  } finally {
    configurationSaving.value = false;
    operationBusy.value = null;
  }
};

const isUninstallAction = (extension: Extension): boolean =>
  extension.source === 'runtime' || (
    extension.source === 'application' && extension.is_installed
  );

const deleteTargetVersion = (extension: Extension | null): string => {
  if (!extension) return '';
  if (extension.source === 'application' && !extension.is_installed) {
    return selectedVersions.value[extension.id] || extension.version;
  }
  return extension.version;
};

const canActivateVersion = (extension: Extension): boolean => {
  const version = selectedVersions.value[extension.id];
  if (!extension.can_manage || !version || operationBusy.value === extension.id) return false;
  if (extension.source === 'application') {
    return Boolean(applicationPackageSha(extension, version)) && (
      !extension.is_enabled || version !== extension.version
    );
  }
  return extension.source === 'runtime' && version !== extension.version;
};

const buildApplicationExtensions = (
  packages: ModulePackageCatalogItem[],
  installations: ApplicationInstallation[],
): Extension[] => {
  const installationByModule = new Map(
    installations.map(installation => [installation.module_id, installation]),
  );
  const packagesByModule = new Map<string, ModulePackageCatalogItem[]>();
  for (const pkg of packages) {
    if (pkg.manifest?.entrypoints?.core !== 'application-extension.json') continue;
    const versions = packagesByModule.get(pkg.module_id) || [];
    versions.push(pkg);
    packagesByModule.set(pkg.module_id, versions);
  }

  return Array.from(packagesByModule.entries()).map(([moduleId, modulePackages]) => {
    const ordered = [...modulePackages].sort((left, right) =>
      left.version.localeCompare(right.version, undefined, { numeric: true }),
    );
    const installation = installationByModule.get(moduleId);
    const selectedPackage = ordered.find(pkg => pkg.version === installation?.active_version)
      || ordered[ordered.length - 1];
    const active = installation?.status === 'active' && installation.enabled;
    return {
      id: `application:${moduleId}`,
      source: 'application',
      name: selectedPackage.manifest.name || moduleId,
      type: 'application',
      version: installation?.active_version || selectedPackage.version,
      description: selectedPackage.manifest.description
        || t('extensions.applicationDescription', 'Core-hosted application extension'),
      status: installation?.status || 'staged',
      is_enabled: Boolean(active),
      created_at: '',
      can_manage: isAdmin.value,
      available_versions: ordered.map(pkg => pkg.version),
      package_sha256: selectedPackage.sha256,
      package_sha256_by_version: Object.fromEntries(
        ordered.map(pkg => [pkg.version, pkg.sha256]),
      ),
      is_installed: Boolean(installation?.active_version),
    };
  });
};

const loadExtensions = async () => {
  loading.value = true;
  try {
    const [catalogResponse, compiledPackages, modulePackagesResponse, applicationInstallationsResponse, themesResponse] = await Promise.all([
      http.get('/api/v1/runtime-extensions/catalog', { params: { language: currentLanguage.value } }),
      getCompiledUiCatalog(true),
      isAdmin.value ? http.get('/api/v1/modules/packages') : Promise.resolve({ data: [] }),
      isAdmin.value ? http.get('/api/v1/application-extensions') : Promise.resolve({ data: [] }),
      isAdmin.value ? http.get('/api/v1/modules/themes/catalog') : Promise.resolve({ data: { items: [] } }),
    ]);
    const modulePackages = Array.isArray(modulePackagesResponse.data)
      ? modulePackagesResponse.data as ModulePackageCatalogItem[]
      : [];
    const applicationInstallations = Array.isArray(applicationInstallationsResponse.data)
      ? applicationInstallationsResponse.data as ApplicationInstallation[]
      : [];
    const applications = buildApplicationExtensions(modulePackages, applicationInstallations);
    const applicationModuleIds = new Set(applications.map(extension =>
      extension.id.replace('application:', ''),
    ));
    const compiled: Extension[] = compiledPackages
      .filter(pkg => !applicationModuleIds.has(pkg.module_id))
      .map(pkg => ({
      id: `compiled:${pkg.module_id}:${pkg.version}`,
      source: 'compiled',
      name: pkg.name,
      type: 'widget',
      version: pkg.version,
      description: t('extensions.compiledDescription', 'Install-time compiled UI extension'),
      status: 'active',
      is_enabled: true,
      created_at: '',
      can_manage: isAdmin.value,
      available_versions: [pkg.version],
      package_sha256: pkg.source_sha256,
      is_installed: true
    }));
    const themes: Extension[] = (themesResponse.data?.items || []).map((item: ThemeCatalogItem) => ({
      id: `theme:${item.sha256}`,
      source: 'theme',
      name: item.name.translations?.[currentLanguage.value] || item.name.en,
      type: 'theme',
      version: item.version,
      description: item.module_id,
      status: item.status,
      is_enabled: item.enabled,
      is_selected: item.is_selected,
      is_installed: item.is_installed,
      created_at: '',
      can_manage: isAdmin.value,
      available_versions: [item.version],
      package_sha256: item.sha256,
    }));
    extensions.value = [...(catalogResponse.data || []), ...applications, ...compiled, ...themes];
    selectedVersions.value = Object.fromEntries(
      extensions.value.map(extension => [extension.id, extension.version])
    );

    // Load translations for enabled extensions
    for (const ext of extensions.value) {
      if (ext.source === 'legacy' && ext.is_enabled) {
        await i18n.loadExtensionTranslationsForExtension(ext.name, currentLanguage.value);
      }
    }
  } catch (error) {
    console.error('Failed to load extensions:', error);
  } finally {
    loading.value = false;
  }
};

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  selectedFile.value = target.files?.[0] || null;
  uploadError.value = '';
  uploadSuccess.value = '';
};

const uploadExtension = async () => {
  if (!selectedFile.value) return;

  uploading.value = true;
  uploadError.value = '';
  uploadSuccess.value = '';

  try {
    const moduleForm = new FormData();
    moduleForm.append('package', selectedFile.value);
    let uploadedName = '';
    try {
      const moduleResponse = await http.post('/api/v1/modules/packages', moduleForm);
      uploadedName = moduleResponse.data.module_id;
      await getCompiledUiCatalog(true);
    } catch (moduleError: any) {
      const moduleStatus = moduleError.response?.status;
      const moduleDetail = String(moduleError.response?.data?.detail || '').toLowerCase();
      if (
        moduleStatus !== 422 ||
        moduleDetail.includes('compiled ui') ||
        moduleDetail.includes('compiler')
      ) {
        throw moduleError;
      }
      const legacyForm = new FormData();
      legacyForm.append('file', selectedFile.value);
      const legacyResponse = await http.post('/api/extensions/upload', legacyForm);
      uploadedName = legacyResponse.data.name;
    }

    uploadSuccess.value = t(
      'extensions.uploadSuccess',
      'Extension "{name}" uploaded successfully!',
      { name: uploadedName },
    ).replace('{name}', uploadedName);
    selectedFile.value = null;
    // Reset file input
    const fileInput = document.getElementById('extension-file') as HTMLInputElement;
    if (fileInput) fileInput.value = '';

    // Reload extensions list
    await loadExtensions();
  } catch (error: any) {
    uploadError.value = error.response?.data?.detail || t('extensions.uploadError', 'Failed to upload extension');
  } finally {
    uploading.value = false;
  }
};

const toggleExtension = async (extension: Extension, event: Event) => {
  const target = event.target as HTMLInputElement;
  const isEnabled = target.checked;
  operationBusy.value = extension.id;
  operationError.value = '';

  try {
    if (extension.source === 'compiled') {
      target.checked = true;
      return;
    } else if (extension.source === 'theme') {
      await http.post(`/api/v1/modules/themes/packages/${extension.package_sha256}/${isEnabled ? 'enable' : 'disable'}`);
      await Promise.all([settingsStore.loadThemeAppearance(), loadExtensions()]);
      return;
    } else if (extension.source === 'application') {
      const moduleId = extension.id.replace('application:', '');
      if (isEnabled) {
        const version = selectedVersions.value[extension.id];
        const sha256 = applicationPackageSha(extension, version);
        if (!sha256) throw new Error('Application package version is unavailable');
        const activated = await activateApplicationPackage(extension, sha256);
        if (!activated) {
          target.checked = false;
          return;
        }
      } else {
        await http.post(
          `/api/v1/application-extensions/${encodeURIComponent(moduleId)}/disable`,
        );
      }
      await getCompiledUiCatalog(true);
      window.dispatchEvent(new Event('menu-refresh'));
      await loadExtensions();
      return;
    } else if (extension.source === 'runtime') {
      const moduleId = extension.id.replace('runtime:', '');
      await http.patch(
        `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}`,
        { enabled: isEnabled }
      );
      await reloadRuntimeExtensionRoutes(router);
      window.dispatchEvent(new Event('menu-refresh'));
    } else {
      await http.patch(
        `/api/extensions/${extension.id.replace('legacy:', '')}`,
        { is_enabled: isEnabled }
      );
    }

    // Update local state
    const ext = extensions.value.find(e => e.id === extension.id);
    if (ext) {
      ext.is_enabled = isEnabled;
      ext.status = isEnabled ? 'active' : 'inactive';

      // Reload translations if extension was enabled
      if (extension.source === 'legacy' && isEnabled) {
        await i18n.loadExtensionTranslationsForExtension(ext.name, currentLanguage.value);
      }
    }
  } catch (error) {
    console.error('Failed to toggle extension:', error);
    operationError.value = errorMessage(error, t('extensions.toggleError', 'Could not change the extension status.'));
    // Revert checkbox
    target.checked = !isEnabled;
  } finally {
    operationBusy.value = null;
  }
};

const deleteExtension = (extension: Extension) => {
  extensionToDelete.value = extension;
  deleteAction.value = 'remove';
  deleteDatabaseData.value = false;
  deleteUploadedFiles.value = false;
  showDeleteModal.value = true;
};

const eraseApplicationData = (extension: Extension) => {
  extensionToDelete.value = extension;
  deleteAction.value = 'erase-data';
  deleteDatabaseData.value = false;
  deleteUploadedFiles.value = false;
  showDeleteModal.value = true;
};

const activateVersion = async (extension: Extension) => {
  const version = selectedVersions.value[extension.id];
  if (!canActivateVersion(extension) || !version) return;

  activatingVersion.value = extension.id;
  operationBusy.value = extension.id;
  operationError.value = '';
  try {
    if (extension.source === 'application') {
      const sha256 = applicationPackageSha(extension, version);
      if (!sha256) throw new Error('Application package version is unavailable');
      const activated = await activateApplicationPackage(extension, sha256);
      if (!activated) return;
      await getCompiledUiCatalog(true);
    } else {
      const moduleId = extension.id.replace('runtime:', '');
      await http.post(
        `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}/versions/${encodeURIComponent(version)}/activate`
      );
      await reloadRuntimeExtensionRoutes(router);
    }
    window.dispatchEvent(new Event('menu-refresh'));
    await loadExtensions();
  } catch (error) {
    console.error('Failed to activate extension version:', error);
    operationError.value = errorMessage(error, t('extensions.versionError', 'Could not activate the selected version.'));
  } finally {
    activatingVersion.value = null;
    operationBusy.value = null;
  }
};

const errorMessage = (error: any, fallback: string): string =>
  error?.response?.data?.detail || error?.response?.data?.error || fallback;

const reinstallExtension = async (extension: Extension) => {
  if (!extension.package_sha256 || !extension.can_manage) return;
  operationBusy.value = extension.id;
  operationError.value = '';
  try {
    await http.post(`/api/v1/runtime-extensions/packages/${extension.package_sha256}/activate`);
    await reloadRuntimeExtensionRoutes(router);
    window.dispatchEvent(new Event('menu-refresh'));
    await loadExtensions();
  } catch (error) {
    console.error('Failed to reinstall runtime extension:', error);
    operationError.value = errorMessage(error, t('extensions.reinstallError', 'Could not reinstall the extension.'));
  } finally {
    operationBusy.value = null;
  }
};

const confirmDeleteExtension = async () => {
  if (!extensionToDelete.value) return;
  operationBusy.value = extensionToDelete.value.id;
  operationError.value = '';

  try {
    if (deleteAction.value === 'erase-data') {
      const moduleId = extensionToDelete.value.id.replace('application:', '');
      await http.delete(
        `/api/v1/application-extensions/${encodeURIComponent(moduleId)}/data`,
      );
    } else if (extensionToDelete.value.source === 'theme') {
      await http.delete(`/api/v1/modules/themes/packages/${extensionToDelete.value.package_sha256}`);
      await settingsStore.loadThemeAppearance();
    } else if (extensionToDelete.value.source === 'compiled') {
      const [, moduleId, version] = extensionToDelete.value.id.split(':');
      await http.delete(`/api/v1/modules/compiled-ui/packages/${encodeURIComponent(moduleId)}/${encodeURIComponent(version)}`);
      await getCompiledUiCatalog(true);
    } else if (extensionToDelete.value.source === 'runtime') {
      const moduleId = extensionToDelete.value.id.replace('runtime:', '');
      await http.delete(
        `/api/v1/runtime-extensions/definitions/${encodeURIComponent(moduleId)}`,
        { params: { delete_data: deleteDatabaseData.value } }
      );
      await reloadRuntimeExtensionRoutes(router);
      window.dispatchEvent(new Event('menu-refresh'));
    } else if (extensionToDelete.value.source === 'application') {
      const moduleId = extensionToDelete.value.id.replace('application:', '');
      if (extensionToDelete.value.is_installed) {
        await http.delete(
          `/api/v1/application-extensions/${encodeURIComponent(moduleId)}`,
        );
      } else {
        const version = deleteTargetVersion(extensionToDelete.value);
        await http.delete(
          `/api/v1/modules/compiled-ui/packages/${encodeURIComponent(moduleId)}/${encodeURIComponent(version)}`,
        );
      }
      await getCompiledUiCatalog(true);
      window.dispatchEvent(new Event('menu-refresh'));
    } else {
      await http.delete(`/api/extensions/${extensionToDelete.value.id.replace('legacy:', '')}`, {
        params: {
          deleteData: deleteDatabaseData.value,
          deleteFiles: deleteUploadedFiles.value
        }
      });
    }

    await loadExtensions();
    showDeleteModal.value = false;
    extensionToDelete.value = null;
    deleteAction.value = 'remove';
  } catch (error) {
    console.error('Failed to delete extension:', error);
    operationError.value = errorMessage(error, t('extensions.uninstallError', 'Could not remove the extension.'));
  } finally {
    operationBusy.value = null;
  }
};

const cancelDeleteExtension = () => {
  showDeleteModal.value = false;
  extensionToDelete.value = null;
  deleteAction.value = 'remove';
  deleteDatabaseData.value = false;
  deleteUploadedFiles.value = false;
};

// Keep the in-flight target stable while an install/remove request is pending.
const closeDeleteDialog = () => {
  if (operationBusy.value === null) cancelDeleteExtension();
};
const closeOnBackdrop = (event: MouseEvent, close: () => void) => {
  const dialog = event.currentTarget as HTMLDialogElement;
  if (event.target !== dialog) return;
  const bounds = dialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom) close();
};

onMounted(async () => {
  await loadExtensions();

  // Load settings and apply CSS variables
  await settingsStore.loadSettings();
  settingsStore.updateCSSVariables();
});

// Watch for theme changes and update CSS variables
watch(() => themeStore.theme, async () => {
  await settingsStore.loadSettings();
  settingsStore.updateCSSVariables();
});

// Watch for language changes and reload extension translations
watch(currentLanguage, async () => {
  await loadExtensions();
});
</script>

<style scoped>
.extensions-view { background: transparent; }
.view-header { gap: calc(var(--ui-space) * 4); margin-bottom: calc(var(--ui-space) * 6); padding: 0; text-align: left; }
.view-title { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.header-actions { display: flex; align-items: center; }
.upload-section { margin-bottom: calc(var(--ui-space) * 6); }
.section-heading, .extensions-list-heading { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); min-width: 0; }
.section-heading-icon { color: var(--ui-accent); font-size: 1.25em; }
.upload-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: calc(var(--ui-space) * 3); margin-top: calc(var(--ui-space) * 4); }
.upload-picker {
  position: relative; display: flex; align-items: center; gap: calc(var(--ui-space) * 3);
  min-width: 0; padding: calc(var(--ui-space) * 3); cursor: pointer;
  border: 1px dashed var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-alt);
}
.upload-picker:hover { border-color: var(--ui-accent); }
.upload-picker:focus-within { outline: 2px solid var(--ui-focus); outline-offset: 3px; }
.upload-picker-icon { flex-shrink: 0; color: var(--ui-text-secondary); font-size: 1.2em; }
.upload-picker-copy { display: grid; min-width: 0; }
.upload-picker-copy strong { font-weight: 550; overflow-wrap: anywhere; }
.upload-picker-copy small { font-size: .85em; color: var(--ui-text-muted); }
.upload-file-input { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
.upload-btn { min-width: 0; }
.error-message, .success-message {
  margin-top: calc(var(--ui-space) * 3); padding: calc(var(--ui-space) * 3);
  border: 1px solid currentColor; border-radius: var(--ui-radius-sm); overflow-wrap: anywhere;
}
.error-message { color: var(--ui-danger); }
.success-message { color: var(--ui-success); }
.extensions-list-content { min-width: 0; }
.extensions-list-heading { justify-content: space-between; padding-bottom: calc(var(--ui-space) * 4); border-bottom: 1px solid var(--ui-border); }
.extensions-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap: calc(var(--ui-space) * 5); margin-top: calc(var(--ui-space) * 4); }
.extension-card { display: flex; flex-direction: column; gap: calc(var(--ui-space) * 3); overflow-wrap: anywhere; }
.extension-header { display: flex; align-items: flex-start; justify-content: space-between; gap: calc(var(--ui-space) * 3); }
.extension-header h3 { font-size: 1.1em; line-height: 1.4; font-weight: 650; color: var(--ui-text); margin: 0; min-width: 0; }
.extension-version { flex-shrink: 0; max-width: 45%; overflow-wrap: anywhere; }
.extension-meta { display: flex; align-items: center; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
.extension-author { font-size: .85em; color: var(--ui-text-muted); }
.extension-description { flex: 1; color: var(--ui-text-secondary); font-size: .95em; }
.extension-status { display: flex; align-items: center; flex-wrap: wrap; gap: calc(var(--ui-space) * 2); }
.status-badge { text-transform: capitalize; }
.status-badge::before { content: ''; width: .45em; height: .45em; flex-shrink: 0; border-radius: 50%; background: currentColor; }
.status-badge.active, .status-badge.enabled { color: var(--ui-success); }
.status-badge.error, .status-badge.unavailable { color: var(--ui-danger); }
.selected-theme, .theme-note, .managed-note { font-size: .85em; color: var(--ui-text-secondary); }
.theme-note { padding-top: calc(var(--ui-space) * 2); }
.toggle-switch { position: relative; display: inline-flex; flex: 0 0 44px; width: 44px; height: 44px; margin-left: auto; }
.toggle-switch input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; opacity: 0; cursor: pointer; z-index: 1; }
.slider { position: absolute; inset: 10px 1px; border: 1px solid var(--ui-border); border-radius: 24px; background: var(--ui-surface-alt); pointer-events: none; }
.slider::before { position: absolute; content: ''; width: 16px; height: 16px; left: 3px; top: 3px; border-radius: 50%; background: var(--ui-text-secondary); }
.toggle-switch input:checked + .slider { background: var(--ui-accent); border-color: var(--ui-accent); }
.toggle-switch input:checked + .slider::before { transform: translateX(18px); background: var(--ui-accent-text); }
.toggle-switch input:focus-visible + .slider { outline: 2px solid var(--ui-focus); outline-offset: 3px; }
.toggle-switch input:disabled { cursor: not-allowed; }
.toggle-switch input:disabled + .slider { opacity: .5; }
.extension-actions { display: grid; gap: calc(var(--ui-space) * 3); margin-top: auto; padding-top: calc(var(--ui-space) * 4); border-top: 1px solid var(--ui-border); }
.version-controls { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); align-items: stretch; gap: calc(var(--ui-space) * 2); }
.version-controls label { grid-column: 1 / -1; color: var(--ui-text-muted); font-size: .85em; }
.version-controls > .ui-button { min-width: 0; overflow-wrap: anywhere; }
.extension-action-footer { display: grid; gap: calc(var(--ui-space) * 3); }
.managed-note { display: flex; align-items: flex-start; gap: calc(var(--ui-space) * 2); }
.extension-action-buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: calc(var(--ui-space) * 2); }
.extension-action-buttons > .ui-button { min-width: 0; overflow-wrap: anywhere; }
.loading, .no-extensions { margin-top: calc(var(--ui-space) * 4); text-align: center; color: var(--ui-text-secondary); }
.configuration-field { min-width: 0; }
.configuration-field label { font-weight: 550; }
@media (max-width: 720px) {
  .view-header { align-items: stretch; flex-direction: column; }
  .header-actions, .ai-builder-link { width: 100%; }
  .upload-form { grid-template-columns: minmax(0, 1fr); }
  .extensions-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 480px) {
  .extension-action-buttons > .ui-button { flex: 1; }
}
</style>
