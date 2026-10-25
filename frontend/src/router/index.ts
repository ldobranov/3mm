import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import Login from '../views/Login.vue';
import { getCompiledUiCatalog, loadCompiledComponent } from '@/utils/compiled-ui';
import type { CompiledUiPackage } from '@/utils/compiled-ui';
import { withApplicationHost } from '@/utils/application-host';

const HomeRedirect = {
  name: 'HomeRedirect',
  render: () => null,
};

export function compiledRouteRecords(packages: CompiledUiPackage[]): RouteRecordRaw[] {
  const routes: RouteRecordRaw[] = [];
  for (const pkg of packages) {
    for (const entrypoint of pkg.entrypoints.filter(item => item.kind === 'route' && item.route)) {
      const audience = entrypoint.application_audience;
      const isApplicationRoute = Boolean(audience);
      routes.push({
        path: entrypoint.route!,
        name: `compiled-${pkg.module_id}-${pkg.version}-${entrypoint.entrypoint_id}`,
        component: async () => {
          const component = await loadCompiledComponent(pkg, entrypoint);
          return isApplicationRoute ? withApplicationHost(pkg, entrypoint, component) : component;
        },
        meta: {
          requiresAuth: isApplicationRoute
            ? audience === 'operator' || audience === 'administrator'
            : true,
          requiresKiosk: audience === 'kiosk',
          requiresRole: audience === 'administrator'
            ? 'admin'
            : entrypoint.requires_role || undefined,
          applicationAudience: audience,
          applicationPermissions: entrypoint.required_permissions || [],
          menuLabel: entrypoint.navigation === false ? undefined : entrypoint.label,
          menuOrder: entrypoint.menu_order,
          isCompiledExtensionRoute: true,
          compiledModuleId: pkg.module_id,
          compiledSourceHash: pkg.source_sha256,
        },
      });
    }
  }
  return routes;
}

export async function reloadCompiledUiRoutes(router: any): Promise<void> {
  for (const route of router.getRoutes()) {
    if (route.meta?.isCompiledExtensionRoute && route.name) {
      router.removeRoute(route.name);
    }
  }
  for (const route of compiledRouteRecords(await getCompiledUiCatalog(true))) {
    router.addRoute(route);
  }
}

export async function createRouterWithDynamicRoutes() {

  // Load base application routes
  const routes: RouteRecordRaw[] = [
    { path: '/', name: 'Home', component: HomeRedirect },
    { path: '/user/login', name: 'Login', component: Login, meta: { uiShell: 'auth' } },
    { path: '/user/register', name: 'Register', component: () => import('../views/Register.vue'), meta: { uiShell: 'auth' } },
    { path: '/user/profile', name: 'Profile', component: () => import('../views/Profile.vue'), meta: { requiresAuth: true } },
    { path: '/user/logout', name: 'Logout', component: () => import('../views/Logout.vue') },
    { path: '/devices', name: 'Devices', component: () => import('../views/Devices.vue'), meta: { requiresAuth: true, requiresRole: 'admin', defaultLanding: true, menuLabel: { en: 'Devices' }, menuLabelKey: 'mainServer.title' } },
    { path: '/settings', name: 'Settings', component: () => import('../views/Settings.vue'), meta: { requiresAuth: true, requiresRole: 'admin' } },
    { path: '/settings/ui-preview', name: 'UiPreview', component: () => import('../views/UiPreview.vue'), meta: { requiresAuth: true, requiresRole: 'admin', uiShell: 'application' } },
    { path: '/security', name: 'Security', component: () => import('../views/Security.vue'), meta: { requiresAuth: true } },
    { path: '/users', name: 'Users', component: () => import('../views/Users.vue'), meta: { requiresAuth: true, requiresRole: 'admin' } },
    { path: '/dashboard', name: 'DashboardList', component: () => import('@/views/DashboardList.vue'), meta: { requiresAuth: true } },
    { path: '/dashboard/:id/edit', name: 'DisplayEditor', component: () => import('@/views/DisplayEditor.vue'), meta: { requiresAuth: true } },
    { path: '/extensions', name: 'Extensions', component: () => import('../views/Extensions.vue'), meta: { requiresAuth: true, requiresRole: 'admin' } },
    { path: '/extensions/ai-builder', name: 'AiExtensionBuilder', component: () => import('../views/AiExtensionBuilder.vue'), meta: { requiresAuth: true, requiresRole: 'admin' } },
    {
      path: '/automations/proposals',
      name: 'AutomationProposals',
      component: () => import('@/views/AutomationProposals.vue'),
      meta: {
        requiresAuth: true,
        requiresRole: 'admin',
      },
    },
    {
      path: '/system/updates',
      name: 'SystemUpdates',
      component: () => import('@/views/SystemUpdates.vue'),
      meta: {
        requiresAuth: true,
        requiresRole: 'admin',
      },
    },
    { path: '/@:username/:slug', name: 'PublicDisplay', component: () => import('@/views/PublicDisplay.vue'), meta: { uiShell: 'display' } },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue') },
  ];

  try {
    const compiledRoutes = compiledRouteRecords(await getCompiledUiCatalog());
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
    const kioskToken = localStorage.getItem('applicationKioskToken');
    const isKiosk = Boolean(kioskToken && kioskToken !== 'null' && kioskToken !== 'undefined');

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
    const requiresKiosk = to.matched.some((record) => record.meta && record.meta.requiresKiosk === true);

    if (requiresKiosk && !isKiosk) {
      return next('/user/login');
    }
     
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
