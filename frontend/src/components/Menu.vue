<template>
  <nav 
    class="navbar navbar-expand-lg"
    :style="{
      backgroundColor: headerBgColor,
      color: headerTextColor
    }"
  >
    <div class="container-fluid">
      <router-link 
        class="navbar-brand d-flex align-items-center" 
        to="/"
        :style="{ color: headerTextColor }"
      >
        <img 
          v-if="logoUrl" 
          :src="logoUrl" 
          alt="Logo" 
          class="me-2"
          style="max-height: 40px;"
        />
        {{ siteName }}
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
              :style="{ color: headerTextColor }"
            >
              {{ item.label }}
            </router-link>
          </li>
        </ul>
        <ul class="navbar-nav">
          <li class="nav-item">
            <ThemeToggle />
          </li>
          <li class="nav-item">
            <button 
              class="nav-link btn btn-link"
              @click="openCommandPalette"
              :style="{ color: headerTextColor }"
              title="Press Ctrl+K to open"
            >
              <i class="bi bi-command"></i> Ctrl+K
            </button>
          </li>
          <template v-if="isLoggedIn">
            <li class="nav-item">
              <button 
                class="nav-link btn btn-link" 
                @click="handleLogout"
                :style="{ color: headerTextColor }"
              >
                Logout
              </button>
            </li>
          </template>
          <template v-else>
            <li class="nav-item me-2">
              <router-link to="/user/register" class="nav-link btn btn-link" :style="{ color: headerTextColor }">
                Register
              </router-link>
            </li>
            <li class="nav-item">
              <router-link to="/user/login" class="nav-link btn btn-link" :style="{ color: headerTextColor }">
                Login
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
import { defineComponent, ref, onMounted, computed, onUnmounted } from 'vue';
import http from '@/utils/http';
import { useRouter } from 'vue-router';
import ThemeToggle from './ThemeToggle.vue';

export default defineComponent({
  name: 'Menu',
  components: {
    ThemeToggle
  },
  setup() {
    interface MenuItem {
      label: string;
      path: string;
      icon?: string;
    }
    
    const menuItems = ref<MenuItem[]>([]);
    const errorMessage = ref('');
    const authToken = ref(localStorage.getItem('authToken'));
    const siteName = ref('Mega Monitor');
    const logoUrl = ref('');
    const headerBgColor = ref('#f8f9fa');
    const headerTextColor = ref('#212529');
    
    const router = useRouter();

    // Update auth token ref
    const updateAuthToken = () => {
      authToken.value = localStorage.getItem('authToken');
    };

    // Computed property to check login status
    const isLoggedIn = computed(() => {
      return !!authToken.value && authToken.value !== 'null' && authToken.value !== 'undefined';
    });

    const currentRole = computed(() => localStorage.getItem('role') || '');

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

    const fetchHeaderSettings = async () => {
      try {
        const res = await http.get('/settings/read');
        const items = res.data.items || [];
        
        // Fetch all header settings
        const siteNameSetting = items.find((s: any) => s.key === 'site_name');
        const logoSetting = items.find((s: any) => s.key === 'logo_url');
        const bgColorSetting = items.find((s: any) => s.key === 'header_bg_color');
        const textColorSetting = items.find((s: any) => s.key === 'header_text_color');
        
        siteName.value = siteNameSetting?.value || 'Mega Monitor';
        logoUrl.value = logoSetting?.value || '';
        headerBgColor.value = bgColorSetting?.value || '#f8f9fa';
        headerTextColor.value = textColorSetting?.value || '#212529';
      } catch (e) {
        console.error('Failed to fetch header settings:', e);
        siteName.value = 'Mega Monitor';
        headerBgColor.value = '#f8f9fa';
        headerTextColor.value = '#212529';
      }
    };

    const fetchMenuItems = async () => {
      try {
        // Fetch active menu
        const response = await http.get('/menu/read');
        const menus = response.data.items || [];
        
        // Find the active menu
        const activeMenu = menus.find((m: any) => m.is_active) || menus[0];
        
        if (activeMenu && activeMenu.items) {
          menuItems.value = [...activeMenu.items];
        } else {
          // Fallback menu items
          menuItems.value = [
            { label: 'Home', path: '/' },
            { label: 'Dashboard', path: '/dashboard' },
            { label: 'Pages', path: '/pages' },
            { label: 'Settings', path: '/settings' },
            { label: 'Profile', path: '/user/profile' },
          ];
        }
        
        errorMessage.value = '';
      } catch (error) {
        console.error('Failed to fetch menu:', error);
        // Use fallback menu on error
        menuItems.value = [
          { label: 'Home', path: '/' },
          { label: 'Dashboard', path: '/dashboard' },
          { label: 'Pages', path: '/pages' },
        ];
      }
      
      buildMenuItems();
    };

    // Global refresh function
    const refreshMenu = () => {
      updateAuthToken();
      fetchMenuItems();
      fetchHeaderSettings();
    };
    
    const openCommandPalette = () => {
      if ((window as any).openCommandPalette) {
        (window as any).openCommandPalette();
      }
    };

    // Make refreshMenu available globally
    (window as any).refreshMenu = refreshMenu;

    onMounted(() => {
      fetchMenuItems();
      fetchHeaderSettings();
      
      // Listen for custom menu refresh event
      window.addEventListener('menu-refresh', refreshMenu);
      // Listen when settings saved to update header settings instantly
      window.addEventListener('settings-updated', fetchHeaderSettings);
      
      // Listen for storage events (when localStorage changes in another tab)
      window.addEventListener('storage', (e) => {
        if (e.key === 'authToken') {
          refreshMenu();
        }
      });
    });

    onUnmounted(() => {
      window.removeEventListener('menu-refresh', refreshMenu);
      window.removeEventListener('settings-updated', fetchHeaderSettings);
      delete (window as any).refreshMenu;
    });

    return { 
      menuItems, 
      visibleMenuItems, 
      errorMessage, 
      isLoggedIn, 
      handleLogout,
      refreshMenu,
      siteName,
      logoUrl,
      headerBgColor,
      headerTextColor,
      openCommandPalette
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
