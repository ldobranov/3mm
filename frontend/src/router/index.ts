import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import Login from '../views/Login.vue';
import Register from '../views/Register.vue';
import Settings from '../views/Settings.vue';
import SettingsEditor from '../views/SettingsEditor.vue';
import Users from '../views/Users.vue';
import Profile from '../views/Profile.vue';
import Extensions from '@/views/Extensions.vue';
import { getAvailableExtensions } from '@/utils/extension-relationships';

// Component resolver for dynamic imports
function createComponentResolver(extensionName: string, extensionVersion: string) {
  return {
    resolveComponent: (componentName: string) => {
      // Add .vue extension if not present
      const fullComponentName = componentName.endsWith('.vue') ? componentName : `${componentName}.vue`;
      const componentPath = `../extensions/${extensionName}_${extensionVersion}/${fullComponentName}`;
      return () => import(/* @vite-ignore */ componentPath);
    }
  };
}

// Dynamic extension route loader - will be called after extension system initializes
let extensionRoutesLoaded = false;
let pendingExtensionRoutes: RouteRecordRaw[] = [];

async function loadExtensionRoutes(): Promise<RouteRecordRaw[]> {
  // If already loaded, return cached routes
  if (extensionRoutesLoaded) {
    return pendingExtensionRoutes;
  }

  // Check if extension system is ready - try to get extensions, fallback to known ones if not ready
  let extensionNames = getAvailableExtensions();
  if (extensionNames.length === 0) {
    // Fallback: dynamically discover extensions that have frontend routes
    try {
      // Use Vite's import.meta.glob to find extensions with frontend routes
      const manifestModules = import.meta.glob('../extensions/*/manifest.json', { eager: true });
      extensionNames = [];

      for (const path in manifestModules) {
        const match = path.match(/\/extensions\/([^\/]+)_[^\/]+\/manifest\.json$/);
        if (match) {
          const extensionName = match[1];
          const manifest = (manifestModules[path] as any).default;

          // Only include extensions that have frontend routes
          if (manifest && manifest.frontend_routes && Array.isArray(manifest.frontend_routes)) {
            extensionNames.push(extensionName);
          }
        }
      }
    } catch (error) {
      console.warn('Router: Fallback discovery failed:', error);
      extensionNames = [];
    }
  }

  const extensionRoutes: RouteRecordRaw[] = [];

  for (const extensionName of extensionNames) {
    try {
      // Load manifest directly from file
      const manifestModule = await import(`../extensions/${extensionName}_1.0.0/manifest.json`);
      const manifest = manifestModule.default;

      if (!manifest) {
        console.warn(`No manifest found for ${extensionName}`);
        continue;
      }

      const resolver = createComponentResolver(extensionName, '1.0.0'); // Assuming version 1.0.0

      if (manifest.frontend_routes && Array.isArray(manifest.frontend_routes)) {
        for (const routeConfig of manifest.frontend_routes) {
          try {
            const route: RouteRecordRaw = {
              path: routeConfig.path,
              name: routeConfig.name || `${extensionName}-${routeConfig.path.replace(/[^a-zA-Z0-9]/g, '-')}`,
              component: resolver.resolveComponent(routeConfig.component),
              meta: {
                ...routeConfig.meta || {},
                isExtensionRoute: true,
                extensionName: extensionName
              },
              props: routeConfig.props || false
            };
            extensionRoutes.push(route);
          } catch (routeError) {
            console.warn(`Failed to create route for ${routeConfig.path}:`, routeError);
          }
        }
      }
    } catch (error) {
      console.warn(`Failed to load manifest for ${extensionName}:`, error);
    }
  }

  extensionRoutesLoaded = true;
  pendingExtensionRoutes = extensionRoutes;
  return extensionRoutes;
}

// Function to add extension routes after extension system initializes
export async function addExtensionRoutes(router: any) {
  if (extensionRoutesLoaded) {
    return;
  }

  const extensionRoutes = await loadExtensionRoutes();
  if (extensionRoutes.length > 0) {
    for (const route of extensionRoutes) {
      router.addRoute(route);
    }
  }
}

// Function to reload extension routes with full discovery (after extension system initializes)
export async function reloadExtensionRoutes(router: any) {
  // Force reload by resetting the loaded flag
  extensionRoutesLoaded = false;
  pendingExtensionRoutes = [];

  // Remove existing extension routes by checking route metadata
  const allRoutes = router.getRoutes();
  const extensionRouteNames: string[] = [];

  for (const route of allRoutes) {
    // Check if this route has the extension metadata we added during creation
    if (route.meta && (route.meta as any).isExtensionRoute) {
      extensionRouteNames.push(route.name as string);
    }
  }

  extensionRouteNames.forEach((routeName: string) => {
    try {
      router.removeRoute(routeName);
    } catch (error) {
      console.warn(`Could not remove route ${routeName}:`, error);
    }
  });

  // Load routes again with full discovery
  const extensionRoutes = await loadExtensionRoutes();
  if (extensionRoutes.length > 0) {
    for (const route of extensionRoutes) {
      router.addRoute(route);
    }
  }
}

async function createRouterWithDynamicRoutes() {

  // Load base application routes
  const routes: RouteRecordRaw[] = [
    { path: '/user/login', name: 'Login', component: Login },
    { path: '/user/register', name: 'Register', component: Register },
    { path: '/user/profile', name: 'Profile', component: Profile, meta: { requiresAuth: true } },
    { path: '/user/logout', name: 'Logout', component: () => import('../views/Logout.vue') },
    { path: '/settings', name: 'Settings', component: Settings, meta: { requiresAuth: true } },
    { path: '/security', name: 'Security', component: () => import('../views/Security.vue'), meta: { requiresAuth: true } },
    { path: '/settings-editor', name: 'SettingsEditor', component: SettingsEditor, meta: { requiresAuth: true } },
    { path: '/users', name: 'Users', component: Users, meta: { requiresAuth: true } },
    { path: '/dashboard', name: 'DashboardList', component: () => import('@/views/DashboardList.vue'), meta: { requiresAuth: true } },
    { path: '/dashboard/:id/edit', name: 'DisplayEditor', component: () => import('@/views/DisplayEditor.vue'), meta: { requiresAuth: true } },
    { path: '/extensions', name: 'Extensions', component: Extensions, meta: { requiresAuth: true } },
    { path: '/@:username/:slug', name: 'PublicDisplay', component: () => import('@/views/PublicDisplay.vue') },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue') },
  ];

  // Load extension routes synchronously during router creation
  try {
    const extensionRoutes = await loadExtensionRoutes();
    routes.push(...extensionRoutes);
  } catch (error) {
    console.error('Failed to load extension routes during router creation:', error);
  }

  const router = createRouter({
    history: createWebHistory(),
    routes,
  });

  router.beforeEach((to, from, next) => {
    const requiresAuth = to.matched.some((record) => record.meta && record.meta.requiresAuth === true);
     
    if (!requiresAuth) {
      return next();
    }

    const token = localStorage.getItem('authToken');
    if (!token || token === 'null' || token === 'undefined') {
      return next('/user/login');
    }

    const requiredRole = to.matched.find((r) => r.meta && (r.meta as any).requiresRole)?.meta?.requiresRole as string | undefined;
    if (requiredRole) {
      const currentRole = localStorage.getItem('role');
      if (!currentRole || currentRole !== requiredRole) {
        return next('/user/profile');
      }
    }

    next();
  });

  return router;
}

const router = await createRouterWithDynamicRoutes();
export default router;