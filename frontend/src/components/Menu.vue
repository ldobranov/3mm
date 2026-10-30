<template>
  <slot v-if="$slots.default && custom" :navigation="navigation" />
  <nav
    v-else
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
  <slot name="content" :navigation="navigation" />
  <slot name="footer" :navigation="navigation" />
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, computed, onUnmounted, watch } from 'vue';
import type { PropType } from 'vue';
import http from '@/utils/dynamic-http';
import { useRouter } from 'vue-router';
import { useI18n } from '@/utils/i18n';
import { useSettingsStore } from '@/stores/settings';
import ThemeToggle from './ThemeToggle.vue';
import { isNavigationItemVisible, localizedNavigationLabel } from '@/utils/menu-navigation';
import type { MenuAudience } from '@/utils/menu-navigation';
import { readAvailableLanguages } from '@/utils/language-api';
import { reloadCompiledUiRoutes } from '@/router';
import { kioskRouteAvailable } from '@/utils/kiosk-session';
import { resolveMenuRegions } from '@/utils/menu-layout';

export default defineComponent({
  name: 'Menu',
  props: {
    custom: { type: Boolean, default: true },
    primaryLocation: { type: String as PropType<'header' | 'sidebar'>, default: 'sidebar' },
  },
  components: {
    ThemeToggle
  },
  setup(props) {
    interface MenuItem {
      label: string | { [key: string]: string };
      path: string;
      icon?: string;
      audience?: MenuAudience;
    }

    const menus = ref<{ id: number; name: string; is_active: boolean; items: MenuItem[] }[]>([]);
    const menuItems = computed(() => menus.value.find(menu => menu.is_active)?.items ?? []);
    const errorMessage = ref('');
    const authToken = ref(localStorage.getItem('authToken'));
    const role = ref(localStorage.getItem('role') || '');
    const settingsStore = useSettingsStore();

    const router = useRouter();
    const { t, currentLanguage, setLanguage, setPreviewLanguage } = useI18n();
    const availableLanguages = ref<string[]>(['en']);
    const selectedLanguage = ref<string>('en');

    // Update auth token ref
    const updateAuthToken = () => {
      authToken.value = localStorage.getItem('authToken');
      role.value = localStorage.getItem('role') || '';
    };

    // Computed property to check login status
    const isLoggedIn = computed(() => {
      return !!authToken.value && authToken.value !== 'null' && authToken.value !== 'undefined';
    });

    const currentRole = computed(() => role.value);


    const getMenuItemLabel = (item: MenuItem): string => {
      return localizedNavigationLabel(item.label, currentLanguage.value) || 'Menu Item';
    };

    const filterItems = (items: MenuItem[]) => {
      // Filter menu items based on authentication and role
      return items.filter((item) => {
        // Don't show login/logout in the regular menu items
        if (item.path === '/user/login' || item.path === '/user/logout') {
          return false;
        }

        // Check route requirements
        const matched = router.resolve(item.path).matched;
        const route = matched[matched.length - 1];
        // Stored custom menus must follow the live route registry too.
        if (!route || route.name === 'NotFound') return false;
        const kiosk = kioskRouteAvailable(route.meta.compiledModuleId);
        if ((route.meta.requiresKiosk || route.meta.applicationAudience === 'kiosk') && !kiosk) return false;
        return isNavigationItemVisible(item, {
          isLoggedIn: isLoggedIn.value,
          isKiosk: kiosk,
          currentRole: currentRole.value,
          routeRequiresAuth: route?.meta?.requiresAuth === true,
          routeRequiredRole: route?.meta?.requiresRole as string | undefined,
        });
      });
    };
    const visibleMenuItems = computed(() => filterItems(menuItems.value));
    const regions = computed(() => {
      const placed = resolveMenuRegions(menus.value, settingsStore.menuLayout, props.primaryLocation);
      return Object.fromEntries(Object.entries(placed).map(([region, groups]) => [region,
        groups.map(menu => ({ ...menu, items: filterItems(menu.items) })).filter(menu => menu.items.length),
      ])) as Record<'header' | 'sidebar' | 'footer', typeof menus.value>;
    });

    const showLanguageSwitcher = computed(() => {
      return availableLanguages.value.length > 1;
    });

    // Both shells render the SAME registry, filtering and action handlers.
    const navigation = computed(() => ({
      items: visibleMenuItems.value,
      regions: regions.value,
      label: getMenuItemLabel,
      loggedIn: isLoggedIn.value,
      selectedLanguage: selectedLanguage.value,
      languages: availableLanguages.value,
      showLanguageSwitcher: showLanguageSwitcher.value,
      changeLanguage,
      logout: handleLogout,
      openCommandPalette,
      t,
    }));

    // Function to handle logout
    const handleLogout = () => {
      localStorage.removeItem('authToken');
      localStorage.removeItem('role');
      localStorage.removeItem('username');
      updateAuthToken(); // Update the ref
      window.dispatchEvent(new Event('menu-refresh'));
      router.push('/user/login');
    };

    let menuRequest = 0;
    const fetchMenuItems = async () => {
      const request = ++menuRequest;
      try {
        // Load menu for current language - uses items field with translation support
        const response = await http.get(`/menu/read/${currentLanguage.value}`);
        if (request !== menuRequest) return;
        const values = response.data.items;
        menus.value = Array.isArray(values) ? values.filter((menu: any) => Number.isInteger(menu?.id) &&
          Array.isArray(menu.items)) : [];

        errorMessage.value = '';
      } catch (error) {
        if (request !== menuRequest) return;
        console.error('Failed to fetch menu:', error);
        menus.value = [];
      }
    };

    const fetchAvailableLanguages = async () => {
      try {
        availableLanguages.value = await readAvailableLanguages();
      } catch (error) {
        console.error('Failed to fetch available languages:', error);
        availableLanguages.value = ['en']; // Fallback to English only
      }
    };

    const refreshMenu = async () => {
      updateAuthToken();
      try {
        await reloadCompiledUiRoutes(router);
      } catch (error) {
        console.warn('Extension routes could not be refreshed:', error);
      }
      await fetchAvailableLanguages();
      await fetchMenuItems();
      await settingsStore.loadSettings();
    };

    const handleSettingsUpdated = () => {
      settingsStore.loadSettings();
    };

    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === 'authToken') {
        refreshMenu();
      }
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
      if (settingsStore.previewDesign) await setPreviewLanguage(newLang);
      else await setLanguage(newLang);

      // Save user preference if logged in
      const isAuthenticated = !!localStorage.getItem('authToken')
      if (isAuthenticated && !settingsStore.previewDesign) {
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

    onMounted(() => {
      fetchMenuItems();
      settingsStore.loadSettings();
      fetchAvailableLanguages();
      // Initialize selected language
      selectedLanguage.value = currentLanguage.value;

      // Listen for custom menu refresh event
      window.addEventListener('menu-refresh', refreshMenu);
      // Listen when settings saved to update header settings instantly
      window.addEventListener('settings-updated', handleSettingsUpdated);
      // Listen for storage events (when localStorage changes in another tab)
      window.addEventListener('storage', handleStorageChange);
    });

    // Watch for language changes from other components
    watch(currentLanguage, async (newLang) => {
      selectedLanguage.value = newLang;
      // Refresh menu items and header settings when language changes externally
      await fetchAvailableLanguages();
      await fetchMenuItems();
      await settingsStore.loadSettings();
    });

    onUnmounted(() => {
      ++menuRequest;
      window.removeEventListener('menu-refresh', refreshMenu);
      window.removeEventListener('settings-updated', handleSettingsUpdated);
      window.removeEventListener('storage', handleStorageChange);
    });

    return {
      navigation,
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
