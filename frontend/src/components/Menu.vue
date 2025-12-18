<template>
  <nav
    class="navbar navbar-expand-lg"
    :style="{
      backgroundColor: settingsStore.headerSettings.backgroundColor,
      color: settingsStore.headerSettings.textColor
    }"
  >
    <div class="container-fluid">
      <router-link
        class="navbar-brand d-flex align-items-center"
        to="/"
        :style="{ color: settingsStore.headerSettings.textColor }"
      >
        <img
          v-if="settingsStore.headerSettings.logoUrl"
          :src="settingsStore.headerSettings.logoUrl"
          alt="Logo"
          class="me-2"
          style="max-height: 40px;"
        />
        {{ settingsStore.headerSettings.siteName }}
      </router-link>
      <button
        class="navbar-toggler"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#navbarNav"
        aria-controls="navbarNav"
        aria-expanded="false"
        aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav me-auto">
          <li v-for="item in visibleMenuItems" :key="item.path" class="nav-item">
            <router-link
              :to="item.path"
              class="nav-link"
              :style="{ color: settingsStore.headerSettings.textColor }"
            >
              {{ getMenuItemLabel(item) }}
            </router-link>
          </li>
        </ul>
        <ul class="navbar-nav">
          <li v-if="showLanguageSwitcher" class="nav-item me-2">
            <select
              v-model="selectedLanguage"
              @change="changeLanguage"
              :style="{ color: settingsStore.headerSettings.textColor, backgroundColor: 'transparent', border: '1px solid ' + settingsStore.headerSettings.textColor, borderRadius: '8px', padding: '10px 12px', height: 'auto', cursor: 'pointer' }"
            >
              <option
                v-for="lang in availableLanguages"
                :key="lang"
                :value="lang"
                :style="{ backgroundColor: settingsStore.headerSettings.backgroundColor, color: settingsStore.headerSettings.textColor }"
              >
                {{ lang.toUpperCase() }}
              </option>
            </select>
          </li>
          <li class="nav-item me-2">
            <ThemeToggle />
          </li>
          <li class="nav-item">
            <button
              class="nav-link btn btn-link"
              @click="openCommandPalette"
              :style="{ color: settingsStore.headerSettings.textColor }"
              title="Press Ctrl+K to open"
            >
              <i class="bi bi-command"></i><span class="d-lg-inline"> Ctrl+K</span>
            </button>
          </li>
          <template v-if="isLoggedIn">
            <li class="nav-item">
              <button
                class="nav-link btn btn-link"
                @click="handleLogout"
                :style="{ color: settingsStore.headerSettings.textColor }"
              >
                {{ t('menu.logout', 'Logout') }}
              </button>
            </li>
          </template>
          <template v-else>
            <li class="nav-item me-2">
              <router-link to="/user/register" class="nav-link btn btn-link" :style="{ color: settingsStore.headerSettings.textColor }">
                {{ t('menu.register', 'Register') }}
              </router-link>
            </li>
            <li class="nav-item">
              <router-link to="/user/login" class="nav-link btn btn-link" :style="{ color: settingsStore.headerSettings.textColor }">
                {{ t('menu.login', 'Login') }}
              </router-link>
            </li>
          </template>
        </ul>
      </div>
      <div v-if="errorMessage" class="alert alert-danger mt-3">{{ errorMessage }}</div>
    </div>
  </nav>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed, onUnmounted, watch } from 'vue';
import http from '@/utils/dynamic-http';
import { useRouter } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import { useSettingsStore } from '@/stores/settings';
import ThemeToggle from './ThemeToggle.vue';

export default defineComponent({
  name: 'Menu',
  components: {
    ThemeToggle
  },
  setup() {
    interface MenuItem {
      label: string | { [key: string]: string };
      path: string;
      icon?: string;
    }

    const menuItems = ref<MenuItem[]>([]);
    const errorMessage = ref('');
    const authToken = ref(localStorage.getItem('authToken'));
    const settingsStore = useSettingsStore();

    const router = useRouter();
    const { t, currentLanguage, setLanguage } = useI18n();
    const availableLanguages = ref<string[]>(['en', 'bg']);
    const selectedLanguage = ref<string>('en');

    // Update auth token ref
    const updateAuthToken = () => {
      authToken.value = localStorage.getItem('authToken');
    };

    // Computed property to check login status
    const isLoggedIn = computed(() => {
      return !!authToken.value && authToken.value !== 'null' && authToken.value !== 'undefined';
    });

    const currentRole = computed(() => localStorage.getItem('role') || '');


    const getMenuItemLabel = (item: MenuItem): string => {
      if (typeof item.label === 'string') {
        // Direct string label - assume it's English
        return item.label;
      }

      if (typeof item.label === 'object' && item.label) {
        // Object with language keys
        const langLabel = item.label[currentLanguage.value];
        if (langLabel) {
          return langLabel;
        }

        // Fallback to English
        const enLabel = item.label['en'];
        if (enLabel) {
          return enLabel;
        }

        // Use any available label
        const anyLabel = Object.values(item.label)[0] as string;
        if (anyLabel) {
          return anyLabel;
        }
      }

      // Final fallback
      return 'Menu Item';
    };

    const visibleMenuItems = computed(() => {
      // Filter menu items based on authentication and role
      return menuItems.value.filter((item) => {
        // Don't show login/logout in the regular menu items
        if (item.path === '/user/login' || item.path === '/user/logout') {
          return false;
        }

        // Check route requirements
        const route = router.getRoutes().find((r) => r.path === item.path);
        if (!route) return true; // Show if route not found (external link)

        const requiresAuth = route.meta?.requiresAuth === true;
        if (requiresAuth && !isLoggedIn.value) return false;

        const requiredRole = route.meta?.requiresRole as string | undefined;
        if (requiredRole && currentRole.value !== requiredRole) return false;

        return true;
      });
    });

    const showLanguageSwitcher = computed(() => {
      return availableLanguages.value.length > 1;
    });

    // Function to handle logout
    const handleLogout = () => {
      localStorage.removeItem('authToken');
      localStorage.removeItem('role');
      localStorage.removeItem('username');
      updateAuthToken(); // Update the ref
      buildMenuItems(); // Rebuild menu
      router.push('/user/login');
    };

    const buildMenuItems = () => {
      // Start with base menu items
      const baseItems = [...menuItems.value.filter(item => 
        item.path !== '/user/login' && item.path !== '/user/logout'
      )];
      
      // Clear and rebuild
      menuItems.value = baseItems;
    };


    const fetchMenuItems = async () => {
      try {
        // Load language-specific settings for header
        const langSettingsResponse = await http.get(`/settings/language/${currentLanguage.value}`);
        const langSettings = langSettingsResponse.data.items || [];

        // Update header settings for current language
        const siteName = langSettings.find((s: any) => s.key === 'site_name');
        const headerMessage = langSettings.find((s: any) => s.key === 'header_message');
        const logoUrl = langSettings.find((s: any) => s.key === 'logo_url');
        const bgColor = langSettings.find((s: any) => s.key === 'header_bg_color');
        const textColor = langSettings.find((s: any) => s.key === 'header_text_color');

        settingsStore.headerSettings.siteName = siteName?.value || 'Mega Monitor';
        settingsStore.headerSettings.headerMessage = headerMessage?.value || 'Welcome to Mega Monitor';
        settingsStore.headerSettings.logoUrl = logoUrl?.value || '';
        settingsStore.headerSettings.backgroundColor = bgColor?.value || '#4CAF50';
        settingsStore.headerSettings.textColor = textColor?.value || '#ffffff';

        // Load menu for current language - uses items field with translation support
        const response = await http.get(`/menu/read/${currentLanguage.value}`);
        const menus = response.data.items || [];

        // Prioritize main menu (ID 1) for header display, fallback to first active menu
        const activeMenu = menus.find((m: any) => m.id === 1) || menus.find((m: any) => m.is_active) || menus[0];

        if (activeMenu && activeMenu.items) {
          // Use translated items for current language
          menuItems.value = [...activeMenu.items];
        } else {
          // No menu available - use empty menu
          menuItems.value = [];
        }

        errorMessage.value = '';
      } catch (error) {
        console.error('Failed to fetch menu:', error);
        // Use empty menu on error
        menuItems.value = [];
      }

      buildMenuItems();
    };

    const fetchAvailableLanguages = async () => {
      try {
        const response = await http.get('/language/available');
        availableLanguages.value = response.data.languages || ['en'];
      } catch (error) {
        console.error('Failed to fetch available languages:', error);
        availableLanguages.value = ['en']; // Fallback to English only
      }
    };

    // Global refresh function
    const refreshMenu = () => {
      updateAuthToken();
      fetchMenuItems();
      settingsStore.loadSettings();
    };
    
    const openCommandPalette = () => {
      if ((window as any).openCommandPalette) {
        (window as any).openCommandPalette();
      }
    };

    const changeLanguage = async (event: Event) => {
      const target = event.target as HTMLSelectElement;
      const newLang = target.value;
      selectedLanguage.value = newLang;
      await setLanguage(newLang);

      // Save user preference if logged in
      const isAuthenticated = !!localStorage.getItem('authToken')
      if (isAuthenticated) {
        try {
          await http.post('/settings/create', {
            key: 'user_language',
            value: newLang,
            description: 'User language preference'
          })
          console.log('User language preference saved:', newLang)
        } catch (e) {
          console.error('Failed to save user language preference:', e)
        }
      }

      // Don't fetch menu items here - let the watch handle it
      // This prevents overwriting Bulgarian translations with English data
    };

    // Make refreshMenu available globally
    (window as any).refreshMenu = refreshMenu;

    onMounted(() => {
      fetchMenuItems();
      settingsStore.loadSettings();
      fetchAvailableLanguages();
      // Initialize selected language
      selectedLanguage.value = currentLanguage.value;

      // Listen for custom menu refresh event
      window.addEventListener('menu-refresh', refreshMenu);
      // Listen when settings saved to update header settings instantly
      window.addEventListener('settings-updated', () => settingsStore.loadSettings());
      // Listen for language changes
      window.addEventListener('language-changed', refreshMenu);

      // Listen for storage events (when localStorage changes in another tab)
      window.addEventListener('storage', (e) => {
        if (e.key === 'authToken') {
          refreshMenu();
        }
      });
    });

    // Watch for language changes from other components
    watch(currentLanguage, async (newLang) => {
      selectedLanguage.value = newLang;
      // Refresh menu items and header settings when language changes externally
      await fetchMenuItems();
      await settingsStore.loadSettings();
    });

    onUnmounted(() => {
      window.removeEventListener('menu-refresh', refreshMenu);
      window.removeEventListener('settings-updated', () => settingsStore.loadSettings());
      window.removeEventListener('language-changed', refreshMenu);
      delete (window as any).refreshMenu;
    });

    return {
      menuItems,
      visibleMenuItems,
      errorMessage,
      isLoggedIn,
      handleLogout,
      refreshMenu,
      settingsStore,
      openCommandPalette,
      getMenuItemLabel,
      selectedLanguage,
      availableLanguages,
      changeLanguage,
      showLanguageSwitcher,
      currentLanguage,
      t
    };
  },
});
</script>

<style scoped>
.btn-sm {
  padding: 0.375rem 0.75rem;
  margin-top: 0.25rem;
}
</style>