<template>
  <div class="view" :key="currentLanguage">
    <div class="view-header">
      <h1 class="view-title">{{ t('settings.title') }}</h1>
    </div>

    <div v-if="loading" class="text-center" style="padding: 2rem 0;">
      <div class="spinner" role="status" aria-label="Loading"></div>
    </div>

    <div v-else class="settings-grid">
      <!-- Application Settings Section -->
      <ApplicationSettingsSection
        :available-languages="availableLanguages"
      />

      <!-- Theme Customization Sections -->
      <ThemeCustomizationSection
        v-for="themeType in ['light', 'dark']"
        :key="themeType"
        :theme-type="themeType"
        :settings="themeType === 'light' ? lightStyleSettings : darkStyleSettings"
        :saving="themeType === 'light' ? savingLightStyle : savingDarkStyle"
        :t="t"
        :settings-store="settingsStore"
        :section-title="themeType === 'light' ? t('settings.lightThemeCustomization') : t('settings.darkThemeCustomization')"
        @save="themeType === 'light' ? saveLightStyleSettings() : saveDarkStyleSettings()"
      />

      <!-- Header Customization Section -->
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

      <!-- Menu Configuration Section -->
      <MenuConfigurationSection
        :menu-language="menuLanguage"
        :available-languages="availableLanguages"
        :menus="menus"
        :active-menu-id="activeMenuId"
        :current-menu-items="currentMenuItems"
        :saving-menu="savingMenu"
        :settings-store="settingsStore"
        @update:menu-language="handleMenuLanguageChange"
        @update:active-menu-id="activeMenuId = $event"
        @update:current-menu-items="currentMenuItems = $event"
        @set-active-menu="setActiveMenu"
        @add-menu-item="addMenuItem"
        @edit-menu-item="editMenuItem"
        @remove-menu-item="removeMenuItem"
        @save-menu="saveMenu"
        @drag-end="onDragEnd"
      />

      <!-- Network Configuration Section -->
      <NetworkConfigurationSection
        @config-updated="onNetworkConfigUpdated"
      />
    </div>

    <div v-if="errorMessage" class="alert alert-danger" style="margin-top: 1rem;">{{ errorMessage }}</div>
    <div v-if="successMessage" class="alert alert-success" style="margin-top: 1rem;">{{ successMessage }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed, watch } from 'vue';
import { useThemeStore } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settings';
import { useI18n, i18n } from '@/utils/i18n';
import http from '@/utils/dynamic-http';

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
    const { t, currentLanguage } = useI18n();
    
    // Reactive state
    const availableLanguages = ref<string[]>(['en', 'bg']);
    const languageKey = ref(0);
    const settings = ref<Setting[]>([]);
    const menus = ref<any[]>([]);
    const loading = ref(false);
    const activeMenuId = ref<number | null>(null);
    const errorMessage = ref('');
    const successMessage = ref('');
    const saving = ref(false);
    const savingMenu = ref(false);
    const savingHeader = ref(false);
    const savingLightStyle = ref(false);
    const savingDarkStyle = ref(false);
    const logoInput = ref<HTMLInputElement | null>(null);
    const currentTheme = ref<'light' | 'dark'>(themeStore.theme);
    
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

    const menuProp = computed(() => {
      if (!activeMenu.value) return null;
      return { ...activeMenu.value, items: currentMenuItems.value };
    });

    const filteredSettings = computed(() => {
      const excludedKeys = [
        'site_name', 'header_message', 'logo_url', 'header_bg_color', 'header_text_color',
        // Light theme settings
        'light_body_bg', 'light_content_bg', 'light_button_primary_bg', 'light_button_secondary_bg', 'light_button_danger_bg',
        'light_card_bg', 'light_card_border', 'light_panel_bg', 'light_text_primary', 'light_text_secondary', 'light_text_muted',
        'light_border_radius_sm', 'light_border_radius_md', 'light_border_radius_lg',
        // Dark theme settings
        'dark_body_bg', 'dark_content_bg', 'dark_button_primary_bg', 'dark_button_secondary_bg', 'dark_button_danger_bg',
        'dark_card_bg', 'dark_card_border', 'dark_panel_bg', 'dark_text_primary', 'dark_text_secondary', 'dark_text_muted',
        'dark_border_radius_sm', 'dark_border_radius_md', 'dark_border_radius_lg',
        // Old theme settings (deprecated)
        'theme', 'button_primary_bg', 'button_secondary_bg', 'card_bg', 'card_border', 'body_bg', 'content_bg',
        'button_danger_bg', 'panel_bg', 'text_primary', 'text_secondary', 'text_muted',
        'border_radius_sm', 'border_radius_md', 'border_radius_lg',
        // Network configuration
        'frontend_backend_url'
      ];
      return settings.value.filter((s: Setting) => !excludedKeys.includes(s.key));
    });

    // Theme-specific local state
    const currentSiteName = ref('')
    const currentHeaderMessage = ref('')
    const originalMenuItems = ref<any[]>([])

    // API Functions
    const fetchSettings = async () => {
      try {
        const response = await http.get('/settings/read');
        settings.value = response.data.items || [];
        await settingsStore.loadSettings();
      } catch (error) {
        console.error('Failed to fetch settings:', error);
        errorMessage.value = 'Failed to fetch settings.';
      }
    };

    const fetchMenus = async () => {
      try {
        const response = await http.get('/menu/read');
        const allMenus = response.data.items || [];
        menus.value = allMenus;

        // Always set the first menu as active for editing, regardless of is_active flag
        if (allMenus.length > 0) {
          activeMenuId.value = allMenus[0].id;
        }
      } catch (error) {
        console.error('Failed to fetch menus:', error);
        errorMessage.value = 'Failed to fetch menus.';
      }
    };

    const fetchAvailableLanguages = async () => {
      try {
        const response = await http.get('/language/available');
        const languages = response.data.languages || ['en', 'bg'];
        // Ensure 'en' is first
        availableLanguages.value = ['en', ...languages.filter((lang: string) => lang !== 'en')];
      } catch (error) {
        console.error('Failed to fetch available languages:', error);
        availableLanguages.value = ['en', 'bg'];
      }
    };

    // Unified save function
    const saveAllSettings = async () => {
      saving.value = true;
      errorMessage.value = '';
      successMessage.value = '';
      
      try {
        for (const setting of filteredSettings.value) {
          await http.put('/settings/update', {
            id: setting.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          });
        }
        successMessage.value = 'Settings saved successfully!';
        setTimeout(() => successMessage.value = '', 3000);
        window.dispatchEvent(new Event('settings-updated'));
      } catch (error) {
        console.error('Failed to save settings:', error);
        errorMessage.value = 'Failed to save settings.';
      } finally {
        saving.value = false;
      }
    };

    const setActiveMenu = async () => {
      for (const menu of menus.value) {
        menu.is_active = menu.id === activeMenuId.value;
      }
    };

    // Helper function to normalize menu item labels to objects
    const normalizeMenuItemLabel = (item: any) => {
      if (typeof item.label === 'string') {
        item.label = { en: item.label };
      } else if (!item.label || typeof item.label !== 'object') {
        item.label = { en: 'Menu Item' };
      }
      return item;
    };

    const getMenuItemLabel = (item: any, languageCode: string): string => {
      // Ensure label is normalized
      normalizeMenuItemLabel(item);

      if (typeof item.label === 'object' && item.label) {
        // Return the label for the current language, or fallback to English, or generic fallback
        return item.label[languageCode] || item.label['en'] || 'Menu Item';
      }
      return 'Menu Item';
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

        await fetchSettings();
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

        await fetchSettings();
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
        const response = await http.get(`/settings/language/${languageCode}`);
        const items = response.data.items || [];
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

        const response = await http.get('/settings/read');
        const existingSettings = response.data.items || [];
        const existing = existingSettings.find((s: Setting) =>
          s.key === key && s.language_code === languageCode
        );

        if (existing) {
          await http.put('/settings/update', {
            id: existing.id,
            ...settingData
          });
        } else {
          await http.post('/settings/create', settingData);
        }

        // Update the language settings map for the current language
        const langSettings = languageSettingsMap.value.get(languageCode) || [];
        const updatedSettings = langSettings.filter((item: Setting) => item.key !== key);
        updatedSettings.push({ id: existing?.id, ...settingData });
        languageSettingsMap.value.set(languageCode, updatedSettings);

      } catch (error) {
        console.error('Failed to save language-specific setting:', error);
        errorMessage.value = 'Failed to save setting';
      }
    };

    const getSettingValueForLanguage = (key: string, languageCode: string): string => {
      const langSettings = languageSettingsMap.value.get(languageCode) || [];
      const setting = langSettings.find((s: Setting) => s.key === key);
      return setting?.value || '';
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

    const onMenuLanguageChange = async () => {
      localStorage.setItem('settingsMenuLanguage', menuLanguage.value);
      await safeLoadMenuForLanguage(menuLanguage.value);
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

      await Promise.all([fetchSettings(), fetchMenus(), fetchAvailableLanguages()]);

      // Set original menu items from the menus table items field
      if (activeMenu.value && activeMenu.value.items) {
        originalMenuItems.value = JSON.parse(JSON.stringify(activeMenu.value.items));
      } else {
        originalMenuItems.value = [];
      }

      // Load the menu items for the current language
      await safeLoadMenuForLanguage(menuLanguage.value);

      const currentLang = currentLanguage.value || 'en';
      await loadLanguageSettings('en');

      headerLanguage.value = 'en';
      menuLanguage.value = 'en';

      await safeLoadMenuForLanguage('en');

      // Load default theme from settings
      const defaultThemeSetting = settings.value.find((s: Setting) => s.key === 'default_theme');
      if (defaultThemeSetting) {
        currentTheme.value = defaultThemeSetting.value as 'light' | 'dark';
      }

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
      languageKey.value++;
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
        // Set original menu items from the new active menu
        const newActiveMenu = menus.value.find(m => m.id === newMenuId);
        if (newActiveMenu && newActiveMenu.items) {
          originalMenuItems.value = JSON.parse(JSON.stringify(newActiveMenu.items));
        } else {
          originalMenuItems.value = [];
        }

        // Load menu items for the current language
        await safeLoadMenuForLanguage(menuLanguage.value);
      }
    });

    return {
      // State
      settings,
      filteredSettings,
      menus,
      loading,
      activeMenuId,
      activeMenu,
      errorMessage,
      successMessage,
      saving,
      savingMenu,
      savingHeader,
      savingLightStyle,
      savingDarkStyle,
      headerSettings,
      settingsStore,
      lightStyleSettings,
      darkStyleSettings,
      logoInput,
      currentTheme,
      headerLanguage,
      menuLanguage,
      availableLanguages,
      languageKey,
      languageSettingsMap,
      currentSiteName,
      currentHeaderMessage,
      currentMenuItems,
      menuProp,

      // Current language for reactivity
      currentLanguage,

      // Functions
      t,
      onHeaderLanguageChange,
      handleMenuLanguageChange,
      onMenuLanguageChange,
      loadMenuForLanguage,
      saveAllSettings,
      setActiveMenu,
      addMenuItem,
      editMenuItem,
      removeMenuItem,
      saveMenu,
      onDragEnd,
      handleLogoUpload,
      removeLogo,
      saveHeaderSettings,
      saveLightStyleSettings,
      saveDarkStyleSettings,
      getSettingValueForLanguage,
      getMenuItemLabel,
      normalizeMenuItemLabel,
      onNetworkConfigUpdated
    };
  },
});
</script>

<style scoped>
/* Uses existing CSS classes from styles.css */
</style>
