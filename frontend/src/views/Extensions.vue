<template>
  <div class="view" :key="currentLanguage">
    <div class="view-header">
      <h1 class="view-title">{{ t('extensions.title', 'Extensions') }}</h1>

      <div v-if="isAdmin" class="header-actions">
        <router-link class="button button-outline ai-builder-link" to="/extensions/ai-builder">
          <i class="bi bi-stars" aria-hidden="true"></i>
          {{ t('extensions.aiBuilder.open', 'Open AI Builder') }}
        </router-link>
      </div>
    </div>

    <!-- Upload Section -->
    <div v-if="isAdmin" class="card upload-section">
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
          <button type="submit" :disabled="!selectedFile || uploading" class="button button-primary upload-btn">
            <i class="bi bi-upload" aria-hidden="true"></i>
            {{ uploading ? t('extensions.uploading', 'Uploading...') : t('extensions.uploadExtensionButton', 'Upload Extension') }}
          </button>
        </form>
        <div v-if="uploadError" class="error-message">{{ uploadError }}</div>
        <div v-if="uploadSuccess" class="success-message">{{ uploadSuccess }}</div>
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
          <span v-if="!loading" class="extension-count">{{ extensions.length }}</span>
        </div>
        <div v-if="operationError" class="error-message">{{ operationError }}</div>
        <div v-if="loading" class="loading">{{ t('extensions.loadingExtensions', 'Loading extensions...') }}</div>
        <div v-else-if="extensions.length === 0" class="no-extensions">
          {{ t('extensions.noExtensionsInstalled', 'No extensions installed yet.') }}
        </div>
        <div v-else class="extensions-grid">
          <div
            v-for="ext in extensions"
            :key="ext.id"
            class="extension-card"
          >
            <div class="extension-header">
              <h3>{{ ext.name }}</h3>
              <span class="extension-version">{{ t('extensions.version', 'v') }} {{ ext.version }}</span>
            </div>
            <div class="extension-meta">
              <span class="extension-type">{{ ext.type }}</span>
              <span v-if="ext.source !== 'legacy'" class="runtime-badge">{{ extensionSourceLabel(ext) }}</span>
              <span v-if="ext.author" class="extension-author">{{ t('extensions.by', 'by') }} {{ ext.author }}</span>
            </div>
            <p v-if="ext.description" class="extension-description">{{ ext.description }}</p>
            <div class="extension-status">
              <span :class="['status-badge', ext.status]">
                {{ t(`extensions.${ext.status}`, ext.status) }}
              </span>
              <label
                class="toggle-switch"
                :aria-label="`${ext.name}: ${t(`extensions.${ext.status}`, ext.status)}`"
              >
                <input
                  type="checkbox"
                  :checked="ext.is_enabled"
                  :disabled="ext.source === 'compiled' || !ext.can_manage || !ext.is_installed || operationBusy === ext.id"
                  @change="toggleExtension(ext, $event)"
                />
                <span class="slider"></span>
              </label>
            </div>
            <div v-if="ext.source !== 'compiled'" class="extension-actions">
               <div v-if="(ext.source === 'runtime' && ext.is_installed) || ext.source === 'application'" class="version-controls">
                 <label :for="`version-${ext.id}`">{{ t('extensions.version', 'Version') }}</label>
                 <select :id="`version-${ext.id}`" v-model="selectedVersions[ext.id]">
                   <option v-for="version in ext.available_versions" :key="version" :value="version">
                     {{ version }}
                   </option>
                 </select>
                 <button
                   type="button"
                   class="button button-outline button-sm version-btn"
                   :disabled="!canActivateVersion(ext)"
                   @click="activateVersion(ext)"
                 >
                   {{ activatingVersion === ext.id
                     ? t('extensions.activatingVersion', 'Activating...')
                     : ext.source === 'application' && !ext.is_enabled
                       ? t('extensions.installApplication', 'Install and activate')
                       : t('extensions.activateVersion', 'Activate version') }}
                 </button>
               </div>
               <div class="extension-action-footer">
                 <span v-if="(ext.source === 'runtime' || ext.source === 'application') && ext.is_installed" class="managed-note">
                   <i class="bi bi-database-check" aria-hidden="true"></i>
                   {{ t('extensions.runtimeDataPreserved', 'Data is preserved when disabled') }}
                 </span>
                 <div class="extension-action-buttons">
                   <button
                     v-if="ext.source === 'runtime' && !ext.is_installed && ext.can_manage"
                     type="button"
                     class="button button-outline button-sm version-btn"
                     :disabled="operationBusy === ext.id"
                     @click="reinstallExtension(ext)"
                   >
                     {{ operationBusy === ext.id
                       ? t('extensions.reinstalling', 'Reinstalling...')
                       : t('extensions.reinstall', 'Reinstall') }}
                   </button>
                   <button
                     v-if="ext.source === 'legacy' || (ext.source === 'runtime' && ext.is_installed && ext.can_manage) || (ext.source === 'application' && ext.can_manage)"
                     type="button"
                     @click="deleteExtension(ext)"
                     class="button button-sm delete-btn"
                     :disabled="operationBusy === ext.id"
                   >
                     {{ isUninstallAction(ext)
                       ? t('extensions.uninstall', 'Uninstall')
                       : ext.source === 'application'
                         ? t('extensions.deletePackage', 'Delete package')
                       : t('extensions.delete', 'Delete') }}
                   </button>
                   <button
                     v-if="ext.source === 'application' && !ext.is_installed && ext.can_manage"
                     type="button"
                     class="button button-sm delete-btn"
                     :disabled="operationBusy === ext.id"
                     @click="eraseApplicationData(ext)"
                   >
                     {{ t('extensions.eraseData', 'Erase data') }}
                   </button>
                 </div>
               </div>
             </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Application installation configuration -->
    <div v-if="showConfigurationModal" class="modal-backdrop" @click="cancelApplicationConfiguration">
      <div class="modal-container">
        <div class="modal-surface" @click.stop>
          <div class="modal-header">
            <h2>{{ t('extensions.configureApplication', 'Configure application') }}</h2>
          </div>
          <div class="modal-body">
            <p>{{ t('extensions.configureApplicationHelp', 'Choose which managed device this application should use. The selection is preserved across updates.') }}</p>
            <div v-for="field in configurationFields" :key="field.key" class="form-field configuration-field">
              <label :for="`application-config-${field.key}`">{{ field.label }}</label>
              <select
                :id="`application-config-${field.key}`"
                v-model="configurationValues[field.key]"
                :required="field.required"
              >
                <option value="" disabled>{{ t('extensions.selectDevice', 'Select a device') }}</option>
                <option v-for="device in configurationDevices" :key="device.device_id" :value="device.device_id">
                  {{ device.display_name || device.device_id }} · {{ device.role }}
                </option>
              </select>
              <small v-if="field.description" class="help-text">{{ field.description }}</small>
            </div>
            <div v-if="configurationDevices.length === 0" class="error-message">
              {{ t('extensions.noDevicesAvailable', 'No active managed devices are available.') }}
            </div>
            <div v-if="configurationError" class="error-message">{{ configurationError }}</div>
          </div>
          <div class="modal-footer">
            <button class="button button-secondary" :disabled="configurationSaving" @click="cancelApplicationConfiguration">
              {{ t('extensions.cancel', 'Cancel') }}
            </button>
            <button class="button version-btn" :disabled="!canSaveApplicationConfiguration || configurationSaving" @click="confirmApplicationConfiguration">
              {{ configurationSaving
                ? t('extensions.activatingVersion', 'Activating...')
                : t('extensions.installApplication', 'Install and activate') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete Extension Modal -->
    <div v-if="showDeleteModal" class="modal-backdrop" @click="cancelDeleteExtension">
      <div class="modal-container">
        <div class="modal-surface" @click.stop>
          <div class="modal-header">
            <h2>{{ deleteAction === 'erase-data'
              ? t('extensions.eraseApplicationData', 'Erase application data')
              : extensionToDelete && isUninstallAction(extensionToDelete)
              ? t('extensions.uninstallExtension', 'Uninstall Extension')
              : extensionToDelete?.source === 'application'
                ? t('extensions.deletePackage', 'Delete package')
              : t('extensions.deleteExtension', 'Delete Extension') }}</h2>
          </div>

          <div class="modal-body">
            <p>{{ deleteAction === 'erase-data'
              ? t('extensions.eraseApplicationDataConfirm', 'Permanently erase all preserved data for this application? This cannot be undone, and reinstalling the package will start with an empty database.')
              : extensionToDelete?.source === 'application' && extensionToDelete.is_installed
              ? t('extensions.uninstallApplicationConfirm', 'Uninstall this application extension? Its service, routes and access configuration will be removed. Its application data and uploaded package will be preserved.')
              : extensionToDelete?.source === 'application'
                ? t('extensions.deleteApplicationPackageConfirm', 'Delete this unused application package version? Preserved application data will not be deleted.')
              : extensionToDelete?.source === 'runtime'
                ? t('extensions.uninstallConfirm', 'Uninstall this runtime extension? Its routes and menu entries will be removed.')
              : t('extensions.deleteConfirm', 'Are you sure you want to delete this extension?') }}</p>
            <p><strong>{{ extensionToDelete?.name }}<template v-if="deleteAction !== 'erase-data'"> v{{ deleteTargetVersion(extensionToDelete) }}</template></strong></p>

            <!-- Database data deletion checkbox - only show if extension has tables -->
            <div v-if="extensionToDelete?.type === 'extension' || extensionToDelete?.source === 'runtime'" class="form-field">
              <label class="checkbox-label">
                <input type="checkbox" v-model="deleteDatabaseData" />
                {{ extensionToDelete?.source === 'runtime'
                  ? t('extensions.deleteRuntimeData', 'Also permanently delete all data created by this extension')
                  : t('extensions.deleteDatabaseData', 'Also delete all database tables and data created by this extension') }}
              </label>
              <small class="help-text">{{ extensionToDelete?.source === 'runtime'
                ? (deleteDatabaseData
                  ? t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All data will be permanently lost.')
                  : t('extensions.preserveRuntimeData', 'Data will be preserved and becomes available after reinstalling the extension.'))
                : t('extensions.deleteDatabaseDataWarning', 'This action cannot be undone. All selected data will be permanently lost.') }}</small>
            </div>

            <!-- Uploaded files deletion checkbox - only show if extension uploads files -->
            <div v-if="extensionToDelete?.type === 'extension'" class="form-field">
              <label class="checkbox-label">
                <input type="checkbox" v-model="deleteUploadedFiles" />
                {{ t('extensions.deleteUploadedFiles', 'Also delete all uploaded files (images, documents, etc.) for this extension') }}
              </label>
              <small class="help-text">{{ t('extensions.deleteUploadedFilesWarning', 'This will remove all files uploaded by this extension from the server.') }}</small>
            </div>
          </div>

          <div class="modal-footer">
            <button @click="cancelDeleteExtension" class="button button-secondary" :disabled="operationBusy !== null">
              {{ t('extensions.cancel', 'Cancel') }}
            </button>
            <button @click="confirmDeleteExtension" class="button button-danger" :disabled="operationBusy !== null">
              {{ deleteAction === 'erase-data'
                ? t('extensions.eraseData', 'Erase data')
                : extensionToDelete && isUninstallAction(extensionToDelete)
                ? t('extensions.uninstall', 'Uninstall')
                : extensionToDelete?.source === 'application'
                  ? t('extensions.deletePackage', 'Delete package')
                : t('extensions.delete', 'Delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>
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

const { t, currentLanguage } = useI18n();
const settingsStore = useSettingsStore();
const themeStore = useThemeStore();
const router = useRouter();


interface Extension {
  id: string;
  source: 'legacy' | 'runtime' | 'compiled' | 'application';
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
  return 'Runtime';
};

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
    const [catalogResponse, compiledPackages, modulePackagesResponse, applicationInstallationsResponse] = await Promise.all([
      http.get('/api/v1/runtime-extensions/catalog', { params: { language: currentLanguage.value } }),
      getCompiledUiCatalog(true),
      isAdmin.value ? http.get('/api/v1/modules/packages') : Promise.resolve({ data: [] }),
      isAdmin.value ? http.get('/api/v1/application-extensions') : Promise.resolve({ data: [] })
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
    extensions.value = [...(catalogResponse.data || []), ...applications, ...compiled];
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
.upload-section {
  margin-bottom: 1.5rem;
  overflow: hidden;
}

.header-actions {
  display: flex;
  align-items: center;
}

.ai-builder-link {
  gap: 0.45rem;
  min-height: 2.5rem;
  border-color: var(--card-border);
  color: var(--text-primary);
}

.ai-builder-link:hover {
  border-color: var(--button-primary-bg);
  background: color-mix(in srgb, var(--button-primary-bg) 8%, transparent);
  color: var(--button-primary-bg);
}

.card-content {
  padding: 1.25rem;
}

.section-heading,
.extensions-list-heading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.section-heading h2,
.extensions-list-heading h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 680;
  letter-spacing: -0.015em;
}

.section-heading-icon {
  display: inline-grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  flex: 0 0 2.25rem;
  border-radius: var(--border-radius-md);
  color: var(--button-primary-bg);
  background: color-mix(in srgb, var(--button-primary-bg) 10%, transparent);
}

.upload-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  gap: 0.75rem;
  margin-top: 1rem;
}

.upload-picker {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
  min-height: 3.25rem;
  padding: 0.6rem 0.75rem;
  border: 1px dashed var(--input-border);
  border-radius: var(--border-radius-md);
  background: var(--panel-bg);
  cursor: pointer;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.upload-picker:hover,
.upload-picker:focus-within {
  border-color: var(--button-primary-bg);
  background: color-mix(in srgb, var(--button-primary-bg) 5%, var(--panel-bg));
}

.upload-picker-icon {
  display: inline-grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  flex: 0 0 2rem;
  border-radius: var(--border-radius-sm);
  background: var(--card-bg);
  color: var(--text-secondary);
}

.upload-picker-copy {
  display: grid;
  min-width: 0;
  line-height: 1.25;
}

.upload-picker-copy strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-picker-copy small {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.upload-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.upload-btn {
  gap: 0.45rem;
  min-width: 10rem;
  min-height: 3.25rem;
}

.upload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-message {
  color: var(--error-color);
  margin-top: 1rem;
  padding: 0.75rem;
  background-color: var(--error-bg);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--error-border);
}

.success-message {
  color: var(--success-color);
  margin-top: 1rem;
  padding: 0.75rem;
  background-color: var(--success-bg);
  border-radius: var(--border-radius-md);
  border: 1px solid var(--success-border);
}

.extensions-list {
  margin-top: 1.5rem;
}

.extensions-list-content {
  min-width: 0;
}

.extensions-list-heading {
  justify-content: space-between;
  padding-bottom: 0.9rem;
  border-bottom: 1px solid var(--card-border);
}

.extension-count {
  display: inline-grid;
  place-items: center;
  min-width: 2rem;
  height: 2rem;
  padding: 0 0.55rem;
  border: 1px solid var(--card-border);
  border-radius: 999px;
  background: var(--panel-bg);
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 650;
}

.extensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.extension-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 18rem;
  padding: 1rem;
  border-radius: var(--border-radius-md);
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  box-shadow: 0 1px 2px var(--card-shadow);
  word-wrap: break-word;
  overflow-wrap: break-word;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.extension-card:hover {
  border-color: var(--color-border-hover);
  box-shadow: 0 6px 18px color-mix(in srgb, var(--card-shadow) 65%, transparent);
}

.extension-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
  gap: 1rem;
}

.extension-header h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.05rem;
  font-weight: 680;
  letter-spacing: -0.015em;
  word-break: break-word;
  flex: 1;
  min-width: 0;
}

.extension-version {
  font-size: 0.75rem;
  color: var(--text-secondary);
  background-color: var(--panel-bg);
  border: 1px solid var(--card-border);
  padding: 0.22rem 0.45rem;
  border-radius: 999px;
  flex-shrink: 0;
  white-space: nowrap;
}

.extension-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.65rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.extension-type,
.runtime-badge {
  padding: 0.15rem 0.45rem;
  border: 1px solid var(--card-border);
  border-radius: 999px;
  color: var(--text-secondary);
  background: var(--panel-bg);
  font-size: 0.72rem;
}

.managed-note {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--text-secondary);
  font-size: 0.76rem;
}

.toggle-switch input:disabled + .slider {
  cursor: not-allowed;
  opacity: 0.7;
}

.extension-description {
  flex: 1;
  color: var(--text-secondary);
  margin: 0 0 0.85rem;
  font-size: 0.84rem;
  line-height: 1.5;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.extension-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  min-height: 2.5rem;
  margin-bottom: 0.85rem;
  padding: 0.45rem 0.6rem;
  gap: 1rem;
  border-radius: var(--border-radius-md);
  background: var(--panel-bg);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0;
  font-size: 0.7rem;
  font-weight: 680;
  text-transform: uppercase;
}

.status-badge::before {
  content: '';
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: currentColor;
}

.status-badge.active {
  color: var(--success-color);
}

.status-badge.inactive,
.status-badge.disabled,
.status-badge.staged {
  color: var(--text-muted);
}

.status-badge.error {
  color: var(--error-color);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 42px;
  height: 22px;
  flex: 0 0 42px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--card-border);
  transition: 0.2s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: #ffffff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.22);
  transition: 0.2s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--success-color);
}

input:checked + .slider:before {
  transform: translateX(20px);
}

.extension-actions {
  display: grid;
  gap: 0.7rem;
  margin-top: auto;
  padding-top: 0.85rem;
  border-top: 1px solid var(--card-border);
}

.version-controls {
  display: grid;
  grid-template-columns: auto minmax(4.5rem, 0.45fr) minmax(0, 1fr);
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.version-controls label {
  color: var(--text-secondary);
  font-size: 0.76rem;
}

.version-controls select,
.version-btn {
  min-width: 0;
  min-height: 2.25rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-sm);
  background: var(--input-bg);
  color: var(--text-primary);
  padding: 0.375rem 0.625rem;
}

.version-btn {
  width: 100%;
}

.version-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.extension-action-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  min-height: 1.9rem;
}

.extension-action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
  margin-left: auto;
}

.delete-btn {
  min-height: 2rem;
  background-color: color-mix(in srgb, var(--error-color) 9%, transparent);
  color: var(--error-color);
  border: 1px solid color-mix(in srgb, var(--error-color) 36%, transparent);
  border-radius: var(--border-radius-sm);
  transition: background-color 0.2s;
}

.delete-btn:hover:not(:disabled) {
  background-color: var(--error-color);
  color: white;
}

.loading, .no-extensions {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary);
}

.configuration-field {
  display: grid;
  gap: 0.5rem;
  margin-top: 1rem;
}

.configuration-field label {
  font-weight: 600;
}

.configuration-field select {
  width: 100%;
  min-height: 2.75rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--card-border);
  border-radius: var(--border-radius-md);
  background: var(--input-bg);
  color: var(--text-primary);
}

@media (max-width: 720px) {
  .view-header {
    align-items: stretch;
  }

  .header-actions,
  .ai-builder-link {
    width: 100%;
  }

  .upload-form {
    grid-template-columns: minmax(0, 1fr);
  }

  .upload-btn {
    width: 100%;
  }

  .extensions-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .extension-card {
    min-height: 0;
  }
}

@media (max-width: 480px) {
  .card-content {
    padding: 1rem;
  }

  .extension-card {
    padding: 0.85rem;
  }

  .extension-header {
    gap: 0.5rem;
  }

  .extension-version {
    max-width: 45%;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .version-controls {
    grid-template-columns: minmax(0, 0.75fr) minmax(0, 1.25fr);
  }

  .version-controls label {
    grid-column: 1 / -1;
  }

  .extension-action-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .extension-action-buttons {
    width: 100%;
  }

  .extension-action-buttons .button {
    flex: 1;
  }
}
</style>
