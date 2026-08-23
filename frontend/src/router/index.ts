import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import Login from '../views/Login.vue';
import { getAvailableExtensions } from '@/utils/extension-relationships';
import http from '@/utils/dynamic-http';
import { getCompiledUiCatalog, loadCompiledComponent } from '@/utils/compiled-ui';

const extensionManifests = import.meta.glob('../extensions/*/manifest.json', { eager: true });
const extensionComponents = import.meta.glob('../extensions/*/*.vue');

const HomeRedirect = {
  name: 'HomeRedirect',
  render: () => null,
};

// Component resolver for dynamic imports
function createComponentResolver(extensionName: string, extensionVersion: string) {
  return {
    resolveComponent: (componentName: string) => {
      // Add .vue extension if not present
      const fullComponentName = componentName.endsWith('.vue') ? componentName : `${componentName}.vue`;
      const componentPath = `../extensions/${extensionName}_${extensionVersion}/${fullComponentName}`;
      const componentLoader = extensionComponents[componentPath];
      if (!componentLoader) {
        throw new Error(`Component not bundled: ${componentPath}`);
      }
      return componentLoader;
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

  // Preferred: query enabled extensions with real versions from backend (public endpoint).
  // Fallback: filesystem discovery.
  const enabledExtensions: Array<{ name: string; version: string }> = [];
  let extensionApiAvailable = false;

  try {
    const response = await http.get('/api/extensions/public');
    extensionApiAvailable = true;
    const items = response.data?.items || [];
    for (const item of items) {
      if (item?.name && item?.version) {
        enabledExtensions.push({ name: item.name, version: item.version });
      }
    }
  } catch (error) {
    console.warn('Router: failed to fetch /api/extensions/public, falling back to filesystem discovery:', error);
  }

  if (!extensionApiAvailable) {
    // Fallback: dynamically discover extensions that have frontend routes
    try {
      const candidates: Array<{ name: string; version: string; hasRoutes: boolean }> = [];

      for (const path in extensionManifests) {
        const match = path.match(/\/extensions\/([^\/]+)_([^\/]+)\/manifest\.json$/);
        if (match) {
          const extensionName = match[1];
          const extensionVersion = match[2];
          const manifest = (extensionManifests[path] as any).default;
          const hasRoutes = Boolean(manifest && Array.isArray(manifest.frontend_routes));
          candidates.push({ name: extensionName, version: extensionVersion, hasRoutes });
        }
      }

      // Pick one version per name (highest semver-ish) that has routes
      const byName: Record<string, { name: string; version: string }> = {};
      const compareVersions = (a: string, b: string) => {
        const pa = a.split('.').map(n => Number(n));
        const pb = b.split('.').map(n => Number(n));
        if (pa.some(Number.isNaN) || pb.some(Number.isNaN) || pa.length < 3 || pb.length < 3) {
          return a.localeCompare(b);
        }
        for (let i = 0; i < 3; i++) {
          if (pa[i] !== pb[i]) return pa[i] < pb[i] ? -1 : 1;
        }
        return 0;
      };

      for (const c of candidates) {
        if (!c.hasRoutes) continue;
        const existing = byName[c.name];
        if (!existing || compareVersions(existing.version, c.version) < 0) {
          byName[c.name] = { name: c.name, version: c.version };
        }
      }

      enabledExtensions.push(...Object.values(byName));
    } catch (error) {
      console.warn('Router: filesystem discovery failed:', error);
    }
  }

  const extensionRoutes: RouteRecordRaw[] = [];

  // If extension system is ready, prefer its discovery list as a filter, but keep versions from enabledExtensions.
  const discoveredNames = getAvailableExtensions();
  const filteredEnabled = discoveredNames.length > 0
    ? enabledExtensions.filter(e => discoveredNames.includes(e.name))
    : enabledExtensions;

  for (const { name: extensionName, version: extensionVersion } of filteredEnabled) {
    try {
      const manifestPath = `../extensions/${extensionName}_${extensionVersion}/manifest.json`;
      const manifestModule = extensionManifests[manifestPath] as any;
      const manifest = manifestModule?.default;

      if (!manifest) {
        console.warn(`No manifest found for ${extensionName}`);
        continue;
      }

      const resolver = createComponentResolver(extensionName, extensionVersion);

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

export async function createRouterWithDynamicRoutes() {

  // Load base application routes
  const routes: RouteRecordRaw[] = [
    { path: '/', name: 'Home', component: HomeRedirect },
    { path: '/user/login', name: 'Login', component: Login },
    { path: '/user/register', name: 'Register', component: () => import('../views/Register.vue') },
    { path: '/user/profile', name: 'Profile', component: () => import('../views/Profile.vue'), meta: { requiresAuth: true } },
    { path: '/user/logout', name: 'Logout', component: () => import('../views/Logout.vue') },
    { path: '/settings', name: 'Settings', component: () => import('../views/Settings.vue'), meta: { requiresAuth: true } },
    { path: '/security', name: 'Security', component: () => import('../views/Security.vue'), meta: { requiresAuth: true } },
    { path: '/users', name: 'Users', component: () => import('../views/Users.vue'), meta: { requiresAuth: true } },
    { path: '/dashboard', name: 'DashboardList', component: () => import('@/views/DashboardList.vue'), meta: { requiresAuth: true } },
    { path: '/dashboard/:id/edit', name: 'DisplayEditor', component: () => import('@/views/DisplayEditor.vue'), meta: { requiresAuth: true } },
    { path: '/extensions', name: 'Extensions', component: () => import('../views/Extensions.vue'), meta: { requiresAuth: true } },
    { path: '/extensions/ai-builder', name: 'AiExtensionBuilder', component: () => import('../views/AiExtensionBuilder.vue'), meta: { requiresAuth: true, requiresRole: 'admin' } },
    {
      path: '/automations/proposals',
      name: 'AutomationProposals',
      component: () => import('@/views/AutomationProposals.vue'),
      meta: {
        requiresAuth: true,
        requiresRole: 'admin',
        menuLabel: { en: 'Automations', bg: 'Автоматизации' },
      },
    },
    { path: '/@:username/:slug', name: 'PublicDisplay', component: () => import('@/views/PublicDisplay.vue') },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue') },
  ];

  // Load extension routes synchronously during router creation
  try {
    const extensionRoutes = await loadExtensionRoutes();
    routes.splice(routes.length - 1, 0, ...extensionRoutes);
  } catch (error) {
    console.error('Failed to load extension routes during router creation:', error);
  }

  try {
    const compiledRoutes: RouteRecordRaw[] = [];
    for (const pkg of await getCompiledUiCatalog()) {
      for (const entrypoint of pkg.entrypoints.filter(item => item.kind === 'route' && item.route)) {
        compiledRoutes.push({
          path: entrypoint.route!,
          name: `compiled-${pkg.module_id}-${pkg.version}-${entrypoint.entrypoint_id}`,
          component: () => loadCompiledComponent(pkg, entrypoint),
          meta: {
            requiresAuth: true,
            requiresRole: entrypoint.requires_role || undefined,
            isCompiledExtensionRoute: true,
            compiledModuleId: pkg.module_id,
            compiledSourceHash: pkg.source_sha256,
          },
        });
      }
    }
    routes.splice(routes.length - 1, 0, ...compiledRoutes);
  } catch (error) {
    console.error('Failed to load compiled extension routes:', error);
  }

  const router = createRouter({
    history: createWebHistory(),
    routes,
  });

  router.beforeEach((to, from, next) => {
    const token = localStorage.getItem('authToken');
    const isAuthenticated = Boolean(token && token !== 'null' && token !== 'undefined');

    if (to.path === '/') {
      if (!isAuthenticated) {
        return next('/user/login');
      }

      const currentRole = localStorage.getItem('role') || '';
      const defaultLanding = router.getRoutes().find((route) => {
        if (route.path === '/' || route.meta?.defaultLanding !== true) return false;
        const requiredRole = route.meta?.requiresRole as string | undefined;
        return !requiredRole || requiredRole === currentRole;
      });

      return next(defaultLanding?.path || '/user/profile');
    }

    const requiresAuth = to.matched.some((record) => record.meta && record.meta.requiresAuth === true);
     
    if (!requiresAuth) {
      return next();
    }

    if (!isAuthenticated) {
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
