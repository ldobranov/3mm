<template>
  <div class="view">
    <div class="view-header">
      <h1 class="view-title">{{ t('settings.title', 'Settings') }}</h1>
    </div>

    <div v-if="loading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else class="settings-shell">
      <aside class="settings-nav" aria-label="Settings sections">
        <button
          v-for="section in settingsSections"
          :key="section.id"
          type="button"
          class="settings-nav-item"
          :class="{ active: activeSection === section.id }"
          @click="activeSection = section.id"
        >
          <i :class="section.icon" aria-hidden="true"></i>
          <span>{{ section.label }}</span>
        </button>
      </aside>

      <section class="settings-content">
        <div v-show="activeSection === 'application'" id="application-settings" class="settings-anchor">
          <ApplicationSettingsSection
            :available-languages="availableLanguages"
          />
        </div>

        <div v-show="activeSection === 'theme'" id="theme-settings" class="settings-anchor">
          <div class="section-cluster">
            <ThemeCustomizationSection
              v-for="themeType in ['light', 'dark']"
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
            :header-settings="headerSettings"
            :saving-header="savingHeader"
            :language-settings-map="languageSettingsMap"
            @update:header-language="headerLanguage = $event"
            @update:current-site-name="currentSiteName = $event"
            @update:current-header-message="currentHeaderMessage = $event"
            @header-language-change="onHeaderLanguageChange"
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
      </section>
    </div>

    <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">{{ errorMessage }}</div>
    <div v-if="successMessage" class="alert alert-success" style="margin-top: 1rem;">{{ successMessage }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';
import { useI18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';
import { isMenuRouteEligible } from '@/utils/menu-navigation';
import { upsertSettings } from '@/utils/settings-api';
import { readAvailableLanguages, readLanguageSettings } from '@/utils/language-api';

// Import extracted components
import ApplicationSettingsSection from '@/components/settings/ApplicationSettingsSection.vue';
import HeaderCustomizationSection from '@/components/settings/HeaderCustomizationSection.vue';
import MenuConfigurationSection from '@/components/settings/MenuConfigurationSection.vue';
import ThemeCustomizationSection from '@/components/settings/ThemeCustomizationSection.vue';
import NetworkConfigurationSection from '@/components/settings/NetworkConfigurationSection.vue';

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
    NetworkConfigurationSection
  },
  setup() {
    const themeStore = useThemeStore();
    const settingsStore = useSettingsStore();
    const router = useRouter();
    const { t, currentLanguage } = useI18n();
    
    // Reactive state
    const availableLanguages = ref<string[]>(['en']);
    const activeSection = ref('application');
    const menus = ref<any[]>([]);
    const loading = ref(false);
    const activeMenuId = ref<number | null>(null);
    const errorMessage = ref('');
    const successMessage = ref('');
    const savingMenu = ref(false);
    const creatingMenu = ref(false);
    const managingMenu = ref(false);
    const savingHeader = ref(false);
    const savingLightStyle = ref(false);
    const savingDarkStyle = ref(false);
    
    // Language selection refs - default to English
    const headerLanguage = ref<string>('en');
    const menuLanguage = ref<string>(localStorage.getItem('settingsMenuLanguage') || 'en');
    const languageSettingsMap = ref(new Map<string, Setting[]>());
    const currentMenuItems = ref<any[]>([]);
    
    // Local settings
    const headerSettings = settingsStore.headerSettings;
    const lightStyleSettings = settingsStore.lightStyleSettings;
    const darkStyleSettings = settingsStore.darkStyleSettings;
    
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
          return { path: route.path, label, adminOnly: route.meta?.requiresRole === 'admin' };
        })
        .filter((route, index, routes) => routes.findIndex(item => item.path === route.path) === index)
        .sort((a, b) => a.label.localeCompare(b.label));
    });

    const settingsSections = computed(() => [
      { id: 'application', icon: 'bi bi-sliders', label: t('applicationSettings', 'Application Settings') },
      { id: 'theme', icon: 'bi bi-palette', label: t('settings.themeCustomization', 'Theme Customization') },
      { id: 'header', icon: 'bi bi-window', label: t('settings.headerCustomization', 'Header Customization') },
      { id: 'menu', icon: 'bi bi-list-nested', label: t('settings.menuConfiguration', 'Menu Configuration') },
      { id: 'network', icon: 'bi bi-router', label: t('settings.networkConfiguration', 'Network Configuration') }
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
        path: newItem.path
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

        // Save current language values
        await saveSettingForLanguage('site_name', currentSiteName.value || 'Mega Monitor', langCode, `Site name in ${langCode.toUpperCase()}`);
        await saveSettingForLanguage('header_message', currentHeaderMessage.value || 'Welcome to Mega Monitor', langCode, `Header message in ${langCode.toUpperCase()}`);
        await saveSettingForLanguage('header_bg_color', headerSettings.backgroundColor, langCode, `Header background color in ${langCode.toUpperCase()}`);
        await saveSettingForLanguage('header_text_color', headerSettings.textColor, langCode, `Header text color in ${langCode.toUpperCase()}`);
        // Save logo URL if it exists
        if (headerSettings.logoUrl) {
          await saveSettingForLanguage('logo_url', headerSettings.logoUrl, langCode, `Logo URL in ${langCode.toUpperCase()}`);
        }

        // Also ensure English defaults exist
        if (langCode !== 'en') {
          await saveSettingForLanguage('site_name', 'Mega Monitor', 'en', 'Site name in EN');
          await saveSettingForLanguage('header_message', 'Welcome to Mega Monitor', 'en', 'Header message in EN');
          await saveSettingForLanguage('header_bg_color', '#4CAF50', 'en', 'Header background color in EN');
          await saveSettingForLanguage('header_text_color', '#ffffff', 'en', 'Header text color in EN');
          // Ensure English logo URL exists if we have a logo
          if (headerSettings.logoUrl) {
            await saveSettingForLanguage('logo_url', headerSettings.logoUrl, 'en', 'Logo URL in EN');
          }
        }

        await settingsStore.saveHeaderSettings();

        // Debug: log the current logo URL
        console.log('Header settings saved. Logo URL:', headerSettings.logoUrl);

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
        errorMessage.value = 'Failed to save setting';
      }
    };

    const onHeaderLanguageChange = async () => {
      try {
        const langSettings = await loadLanguageSettings(headerLanguage.value || 'en');

        const siteName = langSettings.find((s: Setting) => s.key === 'site_name');
        const headerMessage = langSettings.find((s: Setting) => s.key === 'header_message');
        const bgColor = langSettings.find((s: Setting) => s.key === 'header_bg_color');
        const textColor = langSettings.find((s: Setting) => s.key === 'header_text_color');

        currentSiteName.value = siteName?.value || 'Mega Monitor';
        currentHeaderMessage.value = headerMessage?.value || 'Welcome to Mega Monitor';
        headerSettings.backgroundColor = bgColor?.value || '#4CAF50';
        headerSettings.textColor = textColor?.value || '#ffffff';
      } catch (error) {
        console.error('Failed to load header language settings:', error);
      }
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

      // Load the menu items for the current language
      await safeLoadMenuForLanguage(menuLanguage.value);

      await loadLanguageSettings('en');

      headerLanguage.value = 'en';
      menuLanguage.value = 'en';

      await safeLoadMenuForLanguage('en');

      // Initialize local variables
      const langSettings = languageSettingsMap.value.get('en') || [];
      const siteName = langSettings.find((s: Setting) => s.key === 'site_name');
      const headerMessage = langSettings.find((s: Setting) => s.key === 'header_message');
      currentSiteName.value = siteName?.value || 'Mega Monitor';
      currentHeaderMessage.value = headerMessage?.value || 'Welcome to Mega Monitor';

      loading.value = false;
      settingsStore.updateCSSVariables();
    });

    // Watch for theme changes
    watch(() => themeStore.theme, () => {
      settingsStore.updateCSSVariables();
    });


    // Handle menu language changes
    const handleMenuLanguageChange = async (newLanguage: string) => {
      menuLanguage.value = newLanguage;
      localStorage.setItem('settingsMenuLanguage', newLanguage);
      await safeLoadMenuForLanguage(newLanguage);
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
      currentMenuItems,

      // Current language for reactivity
      currentLanguage,

      // Functions
      t,
      onHeaderLanguageChange,
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
.settings-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}

.settings-nav {
  position: sticky;
  top: 1rem;
  display: grid;
  gap: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--card-border, #e3e3e3);
  border-radius: var(--border-radius-md, 8px);
  background: var(--card-bg, #ffffff);
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  width: 100%;
  padding: 0.7rem 0.85rem;
  border-radius: var(--border-radius-sm, 4px);
  text-decoration: none;
  color: var(--text-primary, #222222);
  background: transparent;
  border: 1px solid transparent;
  font-size: 0.95rem;
  text-align: left;
  cursor: pointer;
}

.settings-nav-item:hover,
.settings-nav-item:focus {
  background: var(--panel-bg, #f8f9fa);
  border-color: var(--card-border, #e3e3e3);
}

.settings-nav-item.active {
  color: var(--button-primary-bg, #2563eb);
  background: color-mix(in srgb, var(--button-primary-bg, #2563eb) 10%, transparent);
  border-color: color-mix(in srgb, var(--button-primary-bg, #2563eb) 24%, transparent);
}

.settings-nav-item i {
  width: 1.1rem;
  text-align: center;
}

.settings-content {
  min-width: 0;
  display: grid;
  gap: 1rem;
}

.settings-anchor {
  scroll-margin-top: 1rem;
}

.section-cluster {
  display: grid;
  gap: 1rem;
}

@media (max-width: 1024px) {
  .settings-shell {
    grid-template-columns: 1fr;
  }

  .settings-nav {
    position: static;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }
}

@media (max-width: 768px) {
  .settings-nav {
    padding: 0.75rem;
  }
}
</style>
