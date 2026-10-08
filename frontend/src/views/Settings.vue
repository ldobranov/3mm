<template>
  <div class="view settings-view ui-v2"
    :data-card="settingsStore.uiDesign.components.card"
    :data-button="settingsStore.uiDesign.components.button">
    <div class="view-header">
      <h1 class="view-title">{{ t('settings.title', 'Settings') }}</h1>
    </div>

    <div v-if="loading" class="settings-loading ui-section" role="status">
      <span class="ui-spinner" aria-hidden="true"></span>
      {{ t('common.loading', 'Loading...') }}
    </div>

    <div v-else class="settings-shell">
      <aside class="settings-nav ui-section" :aria-label="t('settings.title', 'Settings')">
        <label class="settings-mobile-nav ui-field">
          <span>{{ t('settings.title', 'Settings') }}</span>
          <select class="ui-control" v-model="activeSection" aria-controls="settings-content">
            <option v-for="section in settingsSections" :key="section.id" :value="section.id">{{ section.label }}</option>
          </select>
        </label>
        <nav class="settings-desktop-nav" :aria-label="t('settings.title', 'Settings')">
        <button
          v-for="section in settingsSections"
          :key="section.id"
          type="button"
          class="settings-nav-item"
          :class="{ active: activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'true' : undefined"
          aria-controls="settings-content"
          @click="activeSection = section.id"
        >
          <i :class="section.icon" aria-hidden="true"></i>
          <span>{{ section.label }}</span>
        </button>
        </nav>
      </aside>

      <section id="settings-content" class="settings-content" :aria-label="settingsSections.find(section => section.id === activeSection)?.label">
        <div v-show="activeSection === 'application'" id="application-settings" class="settings-anchor">
          <ApplicationSettingsSection
            :available-languages="availableLanguages"
          />
        </div>

        <div v-show="activeSection === 'theme'" id="theme-settings" class="settings-anchor">
          <div class="section-cluster">
            <ThemePackagesSection v-if="isAdmin" :active="activeSection === 'theme'" />
            <ThemeCustomizationSection
              v-for="themeType in ['light', 'dark']"
              v-show="!settingsStore.activeTheme && !settingsStore.isPackagePreview"
              :key="themeType"
              :theme-type="themeType"
              :settings="themeType === 'light' ? lightStyleSettings : darkStyleSettings"
              :saving="themeType === 'light' ? savingLightStyle : savingDarkStyle"
              :t="t"
              :settings-store="settingsStore"
              :section-title="themeType === 'light'
                ? t('settings.lightThemeCustomization', 'Light Theme Customization')
                : t('settings.darkThemeCustomization', 'Dark Theme Customization')"
              @save="themeType === 'light' ? saveLightStyleSettings() : saveDarkStyleSettings()"
            />
          </div>
        </div>

        <div v-show="activeSection === 'header'" id="header-settings" class="settings-anchor">
          <HeaderCustomizationSection
            :header-language="headerLanguage"
            :available-languages="availableLanguages"
            :current-site-name="currentSiteName"
            :current-header-message="currentHeaderMessage"
            :site-name-fallback="headerSiteNameFallback"
            :header-message-fallback="headerMessageFallback"
            :header-settings="headerSettings"
            :saving-header="savingHeader"
            @update:header-language="handleHeaderLanguageChange"
            @update:current-site-name="currentSiteName = $event"
            @update:current-header-message="currentHeaderMessage = $event"
            @save-header-settings="saveHeaderSettings"
            @logo-upload="handleLogoUpload"
            @logo-remove="removeLogo"
          />
        </div>

        <div v-show="activeSection === 'menu'" id="menu-settings" class="settings-anchor">
          <MenuConfigurationSection
            :menu-language="menuLanguage"
            :available-languages="availableLanguages"
            :menus="menus"
            :route-options="availableMenuRoutes"
            :active-menu-id="activeMenuId"
            :current-menu-items="currentMenuItems"
            :saving-menu="savingMenu"
            :creating-menu="creatingMenu"
            :managing-menu="managingMenu"
            :settings-store="settingsStore"
            @update:menu-language="handleMenuLanguageChange"
            @update:active-menu-id="activeMenuId = $event"
            @update:current-menu-items="currentMenuItems = $event"
            @add-menu-item="addMenuItem"
            @edit-menu-item="editMenuItem"
            @remove-menu-item="removeMenuItem"
            @create-menu="createMenu"
            @activate-menu="activateMenu"
            @rename-menu="renameMenu"
            @delete-menu="deleteMenu"
            @save-menu="saveMenu"
            @drag-end="onDragEnd"
          />
        </div>

        <div v-show="activeSection === 'network'" id="network-settings" class="settings-anchor">
          <NetworkConfigurationSection
            @config-updated="onNetworkConfigUpdated"
          />
        </div>

        <div v-if="isAdmin" v-show="activeSection === 'system'" id="system-settings" class="settings-anchor">
          <SystemControlSection />
        </div>

        <div v-if="isAdmin" v-show="activeSection === 'backups'" id="backup-settings" class="settings-anchor">
          <BackupRecoverySection />
        </div>

        <div v-if="isAdmin" v-show="activeSection === 'diagnostics'" id="diagnostic-settings" class="settings-anchor">
          <DiagnosticsSection />
        </div>
      </section>
    </div>

    <div v-if="errorMessage" class="settings-notice settings-notice--error" role="alert">{{ errorMessage }}</div>
    <div v-if="successMessage" class="settings-notice settings-notice--success" role="status">{{ successMessage }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { isMenuRouteEligible } from '@/utils/menu-navigation';
import { upsertSettings } from '@/utils/settings-api';
import { readAvailableLanguages, readLanguageSettings } from '@/utils/language-api';
import {
  DEFAULT_HEADER_SETTINGS,
  editableHeaderTextValue,
  headerTextFallback
} from '@/utils/header-settings';

// Import extracted components
import ApplicationSettingsSection from '@/components/settings/ApplicationSettingsSection.vue';
import HeaderCustomizationSection from '@/components/settings/HeaderCustomizationSection.vue';
import MenuConfigurationSection from '@/components/settings/MenuConfigurationSection.vue';
import ThemeCustomizationSection from '@/components/settings/ThemeCustomizationSection.vue';
import ThemePackagesSection from '@/components/settings/ThemePackagesSection.vue';
import NetworkConfigurationSection from '@/components/settings/NetworkConfigurationSection.vue';
import SystemControlSection from '@/components/settings/SystemControlSection.vue';
import BackupRecoverySection from '@/components/settings/BackupRecoverySection.vue';
import DiagnosticsSection from '@/components/settings/DiagnosticsSection.vue';

interface Setting {
  id?: number;
  key: string;
  value: string;
  description?: string;
  language_code?: string;
}

export default defineComponent({
  name: 'Settings',
  components: {
    ApplicationSettingsSection,
    HeaderCustomizationSection,
    MenuConfigurationSection,
    ThemeCustomizationSection,
    ThemePackagesSection,
    NetworkConfigurationSection,
    SystemControlSection,
    BackupRecoverySection,
    DiagnosticsSection
  },
  setup() {
    const themeStore = useThemeStore();
    const settingsStore = useSettingsStore();
    const router = useRouter();
    const route = useRoute();
    const { t, currentLanguage } = useI18n();
    
    // Reactive state
    const availableLanguages = ref<string[]>(['en']);
    const activeSection = ref('application');
    watch(() => route.query.section, section => {
      if (section === 'theme') activeSection.value = 'theme';
    }, { immediate: true });
    const menus = ref<any[]>([]);
    const loading = ref(false);
    const activeMenuId = ref<number | null>(null);
    const errorMessage = ref('');
    const successMessage = ref('');
    const isAdmin = computed(() => localStorage.getItem('role') === 'admin');
    const savingMenu = ref(false);
    const creatingMenu = ref(false);
    const managingMenu = ref(false);
    const savingHeader = ref(false);
    const savingLightStyle = ref(false);
    const savingDarkStyle = ref(false);
    
    // Language selection refs - default to English
    const headerLanguage = ref<string>(localStorage.getItem('settingsHeaderLanguage') || 'en');
    const menuLanguage = ref<string>(localStorage.getItem('settingsMenuLanguage') || 'en');
    const languageSettingsMap = ref(new Map<string, Setting[]>());
    const headerTextDrafts = reactive<Record<string, { siteName: string; headerMessage: string }>>({});
    const currentMenuItems = ref<any[]>([]);
    
    // Local settings
    const headerSettings = settingsStore.headerSettings;
    const lightStyleSettings = settingsStore.lightStyleSettings;
    const darkStyleSettings = settingsStore.darkStyleSettings;

    const headerSiteNameFallback = computed(() => headerTextFallback(
      languageSettingsMap.value,
      'site_name',
      DEFAULT_HEADER_SETTINGS.siteName
    ));
    const headerMessageFallback = computed(() => headerTextFallback(
      languageSettingsMap.value,
      'header_message',
      DEFAULT_HEADER_SETTINGS.headerMessage
    ));
    
    // Computed
    const activeMenu = computed(() => {
      if (!activeMenuId.value) return null;
      return menus.value.find(m => m.id === activeMenuId.value);
    });

    const availableMenuRoutes = computed(() => {
      const hiddenPaths = new Set(['/user/login', '/user/register', '/user/logout']);
      const currentRole = localStorage.getItem('role') || '';

      return router.getRoutes()
        .filter(route => {
          const requiredRole = route.meta?.requiresRole as string | undefined;
          return !hiddenPaths.has(route.path) && isMenuRouteEligible(route.path, requiredRole, currentRole);
        })
        .map(route => {
          const menuLabel = route.meta?.menuLabel as string | Record<string, string> | undefined;
          const fallbackLabel = String(route.name || route.path).replace(/([a-z])([A-Z])/g, '$1 $2');
          const label = typeof menuLabel === 'string'
            ? menuLabel
            : menuLabel?.[currentLanguage.value] || menuLabel?.en || fallbackLabel;
          return {
            path: route.path,
            label,
            adminOnly: route.meta?.requiresRole === 'admin',
            requiresAuth: route.meta?.requiresAuth === true,
          };
        })
        .filter((route, index, routes) => routes.findIndex(item => item.path === route.path) === index)
        .sort((a, b) => a.label.localeCompare(b.label));
    });

    const settingsSections = computed(() => [
      { id: 'application', icon: 'bi bi-sliders', label: t('applicationSettings', 'Application Settings') },
      { id: 'theme', icon: 'bi bi-palette', label: t('settings.themeCustomization', 'Theme Customization') },
      { id: 'header', icon: 'bi bi-window', label: t('settings.headerCustomization', 'Header Customization') },
      { id: 'menu', icon: 'bi bi-list-nested', label: t('settings.menuConfiguration', 'Menu Configuration') },
      { id: 'network', icon: 'bi bi-router', label: t('settings.networkConfiguration', 'Network Configuration') },
      ...(isAdmin.value
        ? [
            { id: 'backups', icon: 'bi bi-archive', label: t('backups.navigation', 'Backup and recovery') },
            { id: 'diagnostics', icon: 'bi bi-activity', label: t('diagnostics.navigation', 'Diagnostics') },
            { id: 'system', icon: 'bi bi-cpu', label: t('systemControl.navigation', 'Device Control') },
          ]
        : [])
    ]);

    // Theme-specific local state
    const currentSiteName = ref('')
    const currentHeaderMessage = ref('')
    // API Functions
    const fetchMenus = async (preferredMenuId: number | null = activeMenuId.value) => {
      try {
        const response = await http.get('/menu/read');
        const allMenus = response.data.items || [];
        menus.value = allMenus;

        if (allMenus.length > 0) {
          const preferredMenu = allMenus.find((menu: any) => menu.id === preferredMenuId);
          activeMenuId.value = preferredMenu?.id || allMenus[0].id;
        } else {
          activeMenuId.value = null;
          currentMenuItems.value = [];
        }
      } catch (error) {
        console.error('Failed to fetch menus:', error);
        errorMessage.value = 'Failed to fetch menus.';
      }
    };

    const fetchAvailableLanguages = async () => {
      try {
        availableLanguages.value = await readAvailableLanguages();
        if (!availableLanguages.value.includes(menuLanguage.value)) {
          menuLanguage.value = 'en';
          localStorage.setItem('settingsMenuLanguage', 'en');
        }
        if (!availableLanguages.value.includes(headerLanguage.value)) {
          headerLanguage.value = 'en';
          localStorage.setItem('settingsHeaderLanguage', 'en');
        }
      } catch (error) {
        console.error('Failed to fetch available languages:', error);
        availableLanguages.value = ['en'];
      }
    };

    const addMenuItem = (newItem: any) => {
      if (!newItem.label || !newItem.path) return;

      const labelObj: Record<string, string> = {};
      labelObj[menuLanguage.value] = newItem.label;

      currentMenuItems.value.push({
        label: labelObj,
        path: newItem.path,
        audience: newItem.audience || 'authenticated'
      });
    };

    const editMenuItem = (index: number) => {
      const item = currentMenuItems.value[index];
      const newPath = prompt('Enter new path:', item.path);

      if (newPath !== null) {
        item.path = newPath;
      }
    };

    const removeMenuItem = (index: number) => {
      if (confirm('Remove this menu item?')) {
        currentMenuItems.value.splice(index, 1);
      }
    };

    const onDragEnd = () => {
      console.log('Menu items reordered');
    };

    const saveMenu = async () => {
      if (!activeMenu.value) return;

      savingMenu.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        // Send the menu data with the new optimal structure
        const menuData = {
          id: activeMenu.value.id,
          name: activeMenu.value.name,
          items: currentMenuItems.value,
          language: menuLanguage.value
        };

        // Use the proper menu update endpoint
        await http.put(`/menu/update`, menuData);

        successMessage.value = `Menu saved for ${menuLanguage.value.toUpperCase()}!`;
        setTimeout(() => successMessage.value = '', 3000);

        // Refresh local menus data and menu display
        await fetchMenus();
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error) {
        console.error('Failed to save menu:', error);
        errorMessage.value = 'Failed to save menu.';
      } finally {
        savingMenu.value = false;
      }
    };

    const createMenu = async (name: string) => {
      creatingMenu.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        const response = await http.post('/menu/create', {
          name,
          items: [],
          is_active: menus.value.length === 0
        });
        const createdMenuId = response.data.id as number;
        await fetchMenus(createdMenuId);
        currentMenuItems.value = [];
        successMessage.value = `Menu "${name}" created. You can add its items now.`;
        setTimeout(() => successMessage.value = '', 3000);
      } catch (error: any) {
        console.error('Failed to create menu:', error);
        errorMessage.value = error?.response?.data?.detail || 'Failed to create menu.';
      } finally {
        creatingMenu.value = false;
      }
    };

    const activateMenu = async (menuId: number) => {
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.post(`/menu/${menuId}/activate`);
        await fetchMenus(menuId);
        successMessage.value = 'Active menu updated.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to activate menu.';
      } finally {
        managingMenu.value = false;
      }
    };

    const renameMenu = async ({ id, name }: { id: number; name: string }) => {
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.patch(`/menu/${id}`, { name });
        await fetchMenus(id);
        successMessage.value = 'Menu renamed.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to rename menu.';
      } finally {
        managingMenu.value = false;
      }
    };

    const deleteMenu = async (menuId: number) => {
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.delete(`/menu/${menuId}`);
        await fetchMenus(null);
        await safeLoadMenuForLanguage(menuLanguage.value);
        successMessage.value = 'Menu deleted.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to delete menu.';
      } finally {
        managingMenu.value = false;
      }
    };

    const handleLogoUpload = async (eventOrUrl: Event | string) => {
      // Handle both the old file input method and new ImageUpload component method
      if (typeof eventOrUrl === 'string') {
        // New ImageUpload component method - direct URL
        headerSettings.logoUrl = eventOrUrl;
      } else {
        // Old file input method
        const target = eventOrUrl.target as HTMLInputElement;
        const file = target.files?.[0];

        if (!file) return;

        if (file.size > 2 * 1024 * 1024) {
          errorMessage.value = 'Logo file size must be less than 2MB';
          return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
          headerSettings.logoUrl = e.target?.result as string;
        };
        reader.readAsDataURL(file);
      }
    };

    const removeLogo = () => {
      headerSettings.logoUrl = '';
    };

    const saveHeaderSettings = async () => {
      savingHeader.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        const langCode = headerLanguage.value || 'en';

        // Only text varies by language. An empty value intentionally uses the
        // English/default fallback in the rendered header.
        await Promise.all([
          saveSettingForLanguage(
            'site_name',
            currentSiteName.value,
            langCode,
            `Site name in ${langCode.toUpperCase()}`
          ),
          saveSettingForLanguage(
            'header_message',
            currentHeaderMessage.value,
            langCode,
            `Header message in ${langCode.toUpperCase()}`
          )
        ]);

        // Branding saves never rewrite the separately managed theme colors.
        await settingsStore.saveHeaderSettings(false);

        headerTextDrafts[langCode] = {
          siteName: currentSiteName.value,
          headerMessage: currentHeaderMessage.value
        };

        successMessage.value = `Header settings saved for ${langCode.toUpperCase()}!`;
        setTimeout(() => successMessage.value = '', 3000);
        await loadLanguageSettings(langCode);
      } catch (error) {
        console.error('Failed to save header settings:', error);
        errorMessage.value = 'Failed to save header settings.';
      } finally {
        savingHeader.value = false;
      }
    };

    const saveLightStyleSettings = async () => {
      savingLightStyle.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveLightStyleSettings();
        successMessage.value = 'Light style settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        await settingsStore.loadSettings();

        if (themeStore.theme === 'light') {
          settingsStore.updateCSSVariables();
        }
      } catch (error) {
        console.error('Failed to save light style settings:', error);
        errorMessage.value = 'Failed to save light style settings.';
      } finally {
        savingLightStyle.value = false;
      }
    };

    const saveDarkStyleSettings = async () => {
      savingDarkStyle.value = true;
      errorMessage.value = '';
      successMessage.value = '';

      try {
        await settingsStore.saveDarkStyleSettings();
        successMessage.value = 'Dark style settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);

        await settingsStore.loadSettings();

        if (themeStore.theme === 'dark') {
          settingsStore.updateCSSVariables();
        }
      } catch (error) {
        console.error('Failed to save dark style settings:', error);
        errorMessage.value = 'Failed to save dark style settings.';
      } finally {
        savingDarkStyle.value = false;
      }
    };


    const loadLanguageSettings = async (languageCode: string) => {
      try {
        const items = await readLanguageSettings(languageCode);
        languageSettingsMap.value.set(languageCode, items);
        return items;
      } catch (error) {
        console.error(`Failed to load settings for language ${languageCode}:`, error);
        return [];
      }
    };

    const saveSettingForLanguage = async (key: string, value: string, languageCode: string, description?: string) => {
      try {
        const settingData = {
          key,
          value,
          description: description || `${key} setting`,
          language_code: languageCode
        };

        await upsertSettings([settingData]);

        // Update the language settings map for the current language
        const langSettings = languageSettingsMap.value.get(languageCode) || [];
        const updatedSettings = langSettings.filter((item: Setting) => item.key !== key);
        updatedSettings.push(settingData);
        languageSettingsMap.value.set(languageCode, updatedSettings);

      } catch (error) {
        console.error('Failed to save language-specific setting:', error);
        throw error;
      }
    };

    const readHeaderTextDraft = async (languageCode: string) => {
      const langSettings = languageSettingsMap.value.get(languageCode)
        || await loadLanguageSettings(languageCode);

      return {
        siteName: editableHeaderTextValue(langSettings, 'site_name', languageCode),
        headerMessage: editableHeaderTextValue(langSettings, 'header_message', languageCode)
      };
    };

    const handleHeaderLanguageChange = async (newLanguage: string) => {
      const previousLanguage = headerLanguage.value;
      if (newLanguage === previousLanguage) return;

      headerTextDrafts[previousLanguage] = {
        siteName: currentSiteName.value,
        headerMessage: currentHeaderMessage.value
      };

      headerLanguage.value = newLanguage;
      localStorage.setItem('settingsHeaderLanguage', newLanguage);

      const nextDraft = headerTextDrafts[newLanguage]
        || await readHeaderTextDraft(newLanguage);
      headerTextDrafts[newLanguage] = nextDraft;
      currentSiteName.value = nextDraft.siteName;
      currentHeaderMessage.value = nextDraft.headerMessage;
    };

    const loadMenuForLanguage = async (languageCode: string) => {
      if (!activeMenu.value) return;

      try {
        // With the new optimal structure, items already contain multilingual labels
        // Just load them directly from the database
        if (activeMenu.value.items && Array.isArray(activeMenu.value.items)) {
          currentMenuItems.value = [...activeMenu.value.items];
        } else {
          currentMenuItems.value = [];
        }
      } catch (error) {
        console.error('Failed to load menu for language:', error);
        currentMenuItems.value = [];
      }
    };

    // Prevent recursive updates
    let isLoadingMenuLanguage = false;
    const safeLoadMenuForLanguage = async (languageCode: string) => {
      if (isLoadingMenuLanguage) return;
      isLoadingMenuLanguage = true;
      try {
        await loadMenuForLanguage(languageCode);
      } finally {
        isLoadingMenuLanguage = false;
      }
    };

    // Network configuration event handler
    const onNetworkConfigUpdated = async (config: any) => {
      console.log('Network configuration updated:', config);
      // Optionally refresh HTTP configuration or show success message
      successMessage.value = 'Network configuration updated successfully!';
      setTimeout(() => successMessage.value = '', 3000);
    };

    onMounted(async () => {
      loading.value = true;

      await Promise.all([settingsStore.loadSettings(), fetchMenus(), fetchAvailableLanguages()]);

      // Menu items contain every localized label. Load the selected menu once;
      // changing the editing language must not discard unsaved translations.
      await safeLoadMenuForLanguage(menuLanguage.value);

      const headerLanguages = Array.from(new Set(['en', headerLanguage.value]));
      await Promise.all(headerLanguages.map(loadLanguageSettings));

      const initialHeaderDraft = await readHeaderTextDraft(headerLanguage.value);
      headerTextDrafts[headerLanguage.value] = initialHeaderDraft;
      currentSiteName.value = initialHeaderDraft.siteName;
      currentHeaderMessage.value = initialHeaderDraft.headerMessage;

      loading.value = false;
      settingsStore.updateCSSVariables();
    });

    // Watch for theme changes
    watch(() => themeStore.theme, () => {
      settingsStore.updateCSSVariables();
    });


    // Handle menu language changes
    const handleMenuLanguageChange = (newLanguage: string) => {
      menuLanguage.value = newLanguage;
      localStorage.setItem('settingsMenuLanguage', newLanguage);
    };

    // Watch for active menu changes and reload menu items
    watch(activeMenuId, async (newMenuId) => {
      if (newMenuId) {
        // Load menu items for the current language
        await safeLoadMenuForLanguage(menuLanguage.value);
      }
    });

    return {
      // State
      menus,
      loading,
      activeMenuId,
      activeMenu,
      errorMessage,
      successMessage,
      isAdmin,
      savingMenu,
      creatingMenu,
      managingMenu,
      savingHeader,
      savingLightStyle,
      savingDarkStyle,
      headerSettings,
      settingsStore,
      lightStyleSettings,
      darkStyleSettings,
      headerLanguage,
      menuLanguage,
      availableLanguages,
      availableMenuRoutes,
      activeSection,
      settingsSections,
      languageSettingsMap,
      currentSiteName,
      currentHeaderMessage,
      headerSiteNameFallback,
      headerMessageFallback,
      currentMenuItems,

      // Current language for reactivity
      currentLanguage,

      // Functions
      t,
      handleHeaderLanguageChange,
      handleMenuLanguageChange,
      loadMenuForLanguage,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      createMenu,
      activateMenu,
      renameMenu,
      deleteMenu,
      saveMenu,
      onDragEnd,
      handleLogoUpload,
      removeLogo,
      saveHeaderSettings,
      saveLightStyleSettings,
      saveDarkStyleSettings,
      onNetworkConfigUpdated
    };
  },
});
</script>

<style scoped>
.settings-view { background: transparent; }
.view-header { margin-bottom: calc(var(--ui-space) * 6); padding: 0; text-align: left; }
.view-title { margin: 0; overflow-wrap: anywhere; }
.settings-shell { display: grid; grid-template-columns: 204px minmax(0, 1fr); gap: calc(var(--ui-space) * 5); align-items: start; min-width: 0; }
.settings-nav.ui-section { position: sticky; top: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 2); }
.settings-desktop-nav { display: grid; gap: var(--ui-space); }
.settings-mobile-nav.ui-field { display: none; }
.settings-nav-item { display: flex; align-items: center; gap: calc(var(--ui-space) * 3); width: 100%; min-width: 0; min-height: var(--ui-control-height); padding: calc(var(--ui-space) * 3); border: 1px solid transparent; border-radius: var(--ui-radius-sm); color: var(--ui-text-secondary); background: transparent; font-weight: 550; text-align: left; cursor: pointer; }
.settings-nav-item span { min-width: 0; overflow-wrap: anywhere; }
.settings-nav-item:hover { color: var(--ui-text); background: var(--ui-surface-alt); }
.settings-nav-item.active { color: var(--ui-accent); background: color-mix(in srgb, var(--ui-accent) 10%, var(--ui-surface)); border-color: color-mix(in srgb, var(--ui-accent) 35%, var(--ui-border)); }
.settings-nav-item i { flex: 0 0 1.2em; text-align: center; }
.settings-content, .settings-anchor { min-width: 0; max-width: 100%; }
.settings-content, .section-cluster { display: grid; gap: calc(var(--ui-space) * 4); }
.settings-anchor { scroll-margin-top: calc(var(--ui-space) * 4); }
.settings-loading { display: flex; gap: calc(var(--ui-space) * 3); align-items: center; justify-content: center; }
.settings-notice { margin-top: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); border: 1px solid currentColor; border-radius: var(--ui-radius-sm); overflow-wrap: anywhere; }
.settings-notice--error { color: var(--ui-danger); }
.settings-notice--success { color: var(--ui-success); }
@media (max-width: 1100px) {
  .settings-shell { grid-template-columns: minmax(0, 1fr); }
  .settings-nav.ui-section { position: static; padding: calc(var(--ui-space) * 4); }
  .settings-desktop-nav { display: none; }
  .settings-mobile-nav.ui-field { display: grid; }
}
</style>
