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
            :saving-header="savingHeader || headerReading"
            :dirty="headerDirty"
            :disabled="!isAdmin || !headerReady"
            :state="headerState"
            :error="headerError"
            @update:header-language="handleHeaderLanguageChange"
            @update:current-site-name="currentSiteName = $event"
            @update:current-header-message="currentHeaderMessage = $event"
            @save-header-settings="saveHeaderSettings"
            @logo-upload="handleLogoUpload"
            @logo-remove="removeLogo"
            @discard="discardHeader"
            @reload="reloadHeader"
            @open-theme="activeSection = 'theme'"
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
            :disabled="!isAdmin"
            :unavailable="menuUnavailable"
            :state="menuState"
            :error="menuError"
            @update:menu-language="handleMenuLanguageChange"
            @update:active-menu-id="selectMenu"
            @update:current-menu-items="currentMenuItems = $event"
            @create-menu="createMenu"
            @activate-menu="activateMenu"
            @rename-menu="renameMenu"
            @delete-menu="deleteMenu"
            @save-menu="saveMenu"
            @discard="discardMenu"
            @reload="reloadMenus"
            @open-theme="activeSection = 'theme'"
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
import { readSettings, upsertSettings } from '@/utils/settings-api';
import { readAvailableLanguages, readLanguageSettings } from '@/utils/language-api';
import {
  DEFAULT_HEADER_SETTINGS,
  editableHeaderTextValue,
  headerTextFallback,
  resolveHeaderSettings
} from '@/utils/header-settings';

// Import extracted components
import ApplicationSettingsSection from '@/components/settings/ApplicationSettingsSection.vue';
import HeaderCustomizationSection from '@/components/settings/HeaderCustomizationSection.vue';
import MenuConfigurationSection from '@/components/settings/MenuConfigurationSection.vue';
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
    const headerReading = ref(false);
    const headerReady = ref(false);
    const headerState = ref<'idle' | 'unconfirmed'>('idle');
    const headerError = ref('');
    const menuState = ref<'idle' | 'unconfirmed'>('idle');
    const menuError = ref('');
    const menuUnavailable = ref(false);
    const menuDrafts = new Map<number, any[]>();
    const copyItems = (items: any[]) => JSON.parse(JSON.stringify(items));
    
    // Language selection refs - default to English
    const headerLanguage = ref<string>(localStorage.getItem('settingsHeaderLanguage') || 'en');
    const menuLanguage = ref<string>(localStorage.getItem('settingsMenuLanguage') || 'en');
    const languageSettingsMap = ref(new Map<string, Setting[]>());
    const headerTextDrafts = reactive<Record<string, { siteName: string; headerMessage: string }>>({});
    const currentMenuItems = ref<any[]>([]);
    
    // Local settings
    const headerSettings = reactive({ ...settingsStore.headerSettings });
    const savedLogo = ref('');

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
    const headerDirty = computed(() => {
      const saved = languageSettingsMap.value.get(headerLanguage.value) || [];
      return currentSiteName.value !== editableHeaderTextValue(saved, 'site_name', headerLanguage.value)
        || currentHeaderMessage.value !== editableHeaderTextValue(saved, 'header_message', headerLanguage.value)
        || headerSettings.logoUrl !== savedLogo.value;
    });
    const selectMenu = (id: number | null) => {
      if (id === activeMenuId.value) return;
      if (activeMenuId.value !== null) menuDrafts.set(activeMenuId.value, copyItems(currentMenuItems.value));
      activeMenuId.value = id;
      currentMenuItems.value = id === null ? [] : copyItems(menuDrafts.get(id) || menus.value.find(menu => menu.id === id)?.items || []);
    };
    // API Functions
    const fetchMenus = async (preferredMenuId: number | null = activeMenuId.value) => {
      try {
        const response = await http.get('/menu/read');
        if (!Array.isArray(response.data.items)) throw new Error('Invalid menu response');
        const allMenus = response.data.items;
        menus.value = allMenus;
        menuUnavailable.value = false;

        if (allMenus.length > 0) {
          const preferredMenu = allMenus.find((menu: any) => menu.id === preferredMenuId);
          selectMenu(preferredMenu?.id || allMenus[0].id);
        } else {
          selectMenu(null);
          currentMenuItems.value = [];
        }
        return true;
      } catch (error) {
        console.error('Failed to fetch menus:', error);
        errorMessage.value = 'Failed to fetch menus.';
        menuError.value = errorMessage.value;
        menuUnavailable.value = true;
        return false;
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

    const menuLocked = computed(() => !isAdmin.value || menuUnavailable.value || menuState.value !== 'idle'
      || savingMenu.value || creatingMenu.value || managingMenu.value);
    const discardMenu = () => {
      if (menuLocked.value) return;
      currentMenuItems.value = copyItems(activeMenu.value?.items || []);
      if (activeMenuId.value !== null) menuDrafts.delete(activeMenuId.value);
    };
    const reloadMenus = async () => {
      if (savingMenu.value || creatingMenu.value || managingMenu.value) return;
      managingMenu.value = true;
      try {
        if (!await fetchMenus()) return;
        currentMenuItems.value = copyItems(activeMenu.value?.items || []);
        for (const id of menuDrafts.keys()) if (!menus.value.some(menu => menu.id === id) || id === activeMenuId.value) menuDrafts.delete(id);
        menuState.value = 'idle'; menuError.value = '';
        window.dispatchEvent(new Event('menu-refresh'));
      } finally { managingMenu.value = false; }
    };

    const saveMenu = async () => {
      if (!activeMenu.value || menuLocked.value) return;

      savingMenu.value = true;
      errorMessage.value = '';
      successMessage.value = '';
      menuError.value = '';

      try {
        // Send the menu data with the new optimal structure
        const menuData = {
          id: activeMenu.value.id,
          name: activeMenu.value.name,
          items: copyItems(currentMenuItems.value),
          language: menuLanguage.value
        };

        // Use the proper menu update endpoint
        await http.put(`/menu/update`, menuData);

        // Refresh local menus data and menu display
        if (!await fetchMenus()) throw new Error('Saved menu could not be read');
        const confirmed = menus.value.find(menu => menu.id === menuData.id);
        if (!confirmed || JSON.stringify(confirmed.items || []) !== JSON.stringify(menuData.items)) throw new Error('Menu read does not confirm this draft');
        currentMenuItems.value = copyItems(activeMenu.value?.items || []);
        menuDrafts.delete(menuData.id);
        successMessage.value = `Menu saved for ${menuLanguage.value.toUpperCase()}!`;
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error) {
        console.error('Failed to save menu:', error);
        errorMessage.value = 'Failed to save menu.';
        menuState.value = 'unconfirmed'; menuError.value = errorMessage.value;
      } finally {
        savingMenu.value = false;
      }
    };

    const createMenu = async (name: string) => {
      if (menuLocked.value || !name.trim()) return;
      creatingMenu.value = true;
      errorMessage.value = '';
      successMessage.value = '';
      menuError.value = '';

      try {
        const response = await http.post('/menu/create', {
          name,
          items: [],
          is_active: menus.value.length === 0
        });
        const createdMenuId = response.data.id as number;
        if (!await fetchMenus(createdMenuId)) throw new Error('Created menu could not be read');
        currentMenuItems.value = [];
        successMessage.value = `Menu "${name}" created. You can add its items now.`;
        setTimeout(() => successMessage.value = '', 3000);
      } catch (error: any) {
        console.error('Failed to create menu:', error);
        errorMessage.value = error?.response?.data?.detail || 'Failed to create menu.';
        menuState.value = 'unconfirmed'; menuError.value = errorMessage.value;
      } finally {
        creatingMenu.value = false;
      }
    };

    const activateMenu = async (menuId: number) => {
      if (menuLocked.value) return;
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.post(`/menu/${menuId}/activate`);
        if (!await fetchMenus(menuId)) throw new Error('Active menu could not be read');
        successMessage.value = 'Active menu updated.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to activate menu.';
        menuState.value = 'unconfirmed'; menuError.value = errorMessage.value;
      } finally {
        managingMenu.value = false;
      }
    };

    const renameMenu = async ({ id, name }: { id: number; name: string }) => {
      if (menuLocked.value || !name.trim()) return;
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.patch(`/menu/${id}`, { name });
        if (!await fetchMenus(id)) throw new Error('Renamed menu could not be read');
        successMessage.value = 'Menu renamed.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to rename menu.';
        menuState.value = 'unconfirmed'; menuError.value = errorMessage.value;
      } finally {
        managingMenu.value = false;
      }
    };

    const deleteMenu = async (menuId: number) => {
      if (menuLocked.value) return;
      managingMenu.value = true;
      errorMessage.value = '';
      try {
        await http.delete(`/menu/${menuId}`);
        if (!await fetchMenus(null)) throw new Error('Remaining menus could not be read');
        menuDrafts.delete(menuId);
        successMessage.value = 'Menu deleted.';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('menu-refresh'));
      } catch (error: any) {
        errorMessage.value = error?.response?.data?.detail || 'Failed to delete menu.';
        menuState.value = 'unconfirmed'; menuError.value = errorMessage.value;
      } finally {
        managingMenu.value = false;
      }
    };

    const headerLocked = computed(() => !isAdmin.value || !headerReady.value || savingHeader.value
      || headerReading.value || headerState.value !== 'idle');
    const handleLogoUpload = (url: string) => { if (!headerLocked.value) headerSettings.logoUrl = url; };
    const removeLogo = () => { if (!headerLocked.value) headerSettings.logoUrl = ''; };
    const discardHeader = () => {
      if (headerLocked.value) return;
      const saved = languageSettingsMap.value.get(headerLanguage.value) || [];
      currentSiteName.value = editableHeaderTextValue(saved, 'site_name', headerLanguage.value);
      currentHeaderMessage.value = editableHeaderTextValue(saved, 'header_message', headerLanguage.value);
      headerSettings.logoUrl = savedLogo.value;
      headerTextDrafts[headerLanguage.value] = { siteName: currentSiteName.value, headerMessage: currentHeaderMessage.value };
    };
    const readHeaderSnapshot = async (language: string, expected?: { siteName: string; headerMessage: string; logoUrl: string }) => {
      const languages = Array.from(new Set(['en', language]));
      const [all, localized] = await Promise.all([
        readSettings(),
        Promise.all(languages.map(async code => ({ code, items: await readLanguageSettings(code) }))),
      ]);
      const items = localized.find(value => value.code === language)!.items;
      const actual = { siteName: editableHeaderTextValue(items, 'site_name', language),
        headerMessage: editableHeaderTextValue(items, 'header_message', language), logoUrl: resolveHeaderSettings(items, all, language).logoUrl };
      if (expected && JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Saved header does not confirm this draft');
      // Apply only after every read succeeded. A failed or mismatching read is
      // not confirmation and must not erase the unsaved draft.
      for (const { code, items } of localized) languageSettingsMap.value.set(code, items);
      savedLogo.value = actual.logoUrl;
      headerSettings.logoUrl = savedLogo.value;
      currentSiteName.value = actual.siteName;
      currentHeaderMessage.value = actual.headerMessage;
      headerTextDrafts[language] = { siteName: currentSiteName.value, headerMessage: currentHeaderMessage.value };
      headerReady.value = true; headerState.value = 'idle'; headerError.value = '';
    };
    const reloadHeader = async (notify = true) => {
      if (savingHeader.value || headerReading.value) return;
      headerReading.value = true;
      try {
        await readHeaderSnapshot(headerLanguage.value);
        if (notify) {
          await settingsStore.loadSettings();
          window.dispatchEvent(new Event('settings-updated'));
        }
      } catch { headerError.value = t('uiPlatform.savedReadFailed', 'Could not read saved settings. The draft is kept.'); }
      finally { headerReading.value = false; }
    };
    const saveHeaderSettings = async () => {
      if (headerLocked.value || !headerDirty.value) return;
      savingHeader.value = true; headerError.value = ''; successMessage.value = '';
      const language = headerLanguage.value;
      const expected = { siteName: currentSiteName.value, headerMessage: currentHeaderMessage.value, logoUrl: headerSettings.logoUrl };
      try {
        // Existing settings API performs individual writes, not a transaction.
        // On any failure, read all saved values before permitting another save.
        await upsertSettings([
          { key: 'site_name', value: expected.siteName, language_code: language, description: `Site name in ${language.toUpperCase()}` },
          { key: 'header_message', value: expected.headerMessage, language_code: language, description: `Header message in ${language.toUpperCase()}` },
          { key: 'logo_url', value: expected.logoUrl, language_code: null, description: 'Shared site logo' },
        ]);
        await readHeaderSnapshot(language, expected);
        await settingsStore.loadSettings();
        window.dispatchEvent(new Event('settings-updated'));
        successMessage.value = t('uiPlatform.brandingSaved', 'Header settings saved.');
      } catch {
        headerState.value = 'unconfirmed';
        headerError.value = t('uiPlatform.brandingSaveFailed', 'Could not confirm every header setting. Read saved values before saving again.');
      } finally { savingHeader.value = false; }
    };

    const loadLanguageSettings = async (languageCode: string) => {
      try {
        const items = await readLanguageSettings(languageCode);
        languageSettingsMap.value.set(languageCode, items);
        return items;
      } catch (error) {
        console.error(`Failed to load settings for language ${languageCode}:`, error);
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
      if (newLanguage === previousLanguage || headerLocked.value || !availableLanguages.value.includes(newLanguage)) return;

      headerTextDrafts[previousLanguage] = {
        siteName: currentSiteName.value,
        headerMessage: currentHeaderMessage.value
      };

      headerReading.value = true;
      try {
        const nextDraft = headerTextDrafts[newLanguage] || await readHeaderTextDraft(newLanguage);
        headerLanguage.value = newLanguage;
        localStorage.setItem('settingsHeaderLanguage', newLanguage);
        headerTextDrafts[newLanguage] = nextDraft;
        currentSiteName.value = nextDraft.siteName; currentHeaderMessage.value = nextDraft.headerMessage;
      } catch { headerError.value = t('uiPlatform.savedReadFailed', 'Could not read saved settings. The draft is kept.'); }
      finally { headerReading.value = false; }
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

      await reloadHeader(false);

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
      headerReading, headerReady, headerDirty, headerState, headerError,
      menuState, menuError, menuUnavailable,
      headerSettings,
      settingsStore,
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
      createMenu,
      activateMenu,
      renameMenu,
      deleteMenu,
      saveMenu,
      selectMenu, discardMenu, reloadMenus, discardHeader, reloadHeader,
      handleLogoUpload,
      removeLogo,
      saveHeaderSettings,
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
