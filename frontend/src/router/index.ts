import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import Login from '../views/Login.vue';
import Register from '../views/Register.vue';
import Settings from '../views/Settings.vue';
import SettingsEditor from '../views/SettingsEditor.vue';
import MenuEditor from '../views/MenuEditor.vue';
import Users from '../views/Users.vue';
import Profile from '../views/Profile.vue';
import Extensions from '@/views/Extensions.vue';
import http from '@/utils/http';

async function fetchDynamicRoutesForPages() {
  try {
    console.log('Fetching dynamic routes for pages...');
    const response = await http.get(`/api/pages/read`);
    console.log('Dynamic routes response:', response.data);

    const pages = Array.isArray(response.data.items) ? response.data.items : [];
    return pages.map((page: { id: number; slug?: string; title: string }) => {
      const slug = page.slug || page.title.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
      return {
        path: `/pages/${slug}`,
        slug: slug,
      };
    });
  } catch (error) {
    console.error('Failed to fetch dynamic routes for pages:', error);
    return []; // Return an empty array if fetching fails
  }
}

async function checkPagesExtensionAvailable(): Promise<boolean> {
  try {
    // Only check for extensions if user has a valid token
    const token = localStorage.getItem('authToken');
    if (!token || token === 'null' || token === 'undefined') {
      // User not authenticated, assume no extensions available for now
      return false;
    }
    
    // Check if the extension is available by trying to load it
    const response = await http.get('/api/extensions');
    const extensions = response.data.items || [];
    const pagesExtension = extensions.find((ext: any) =>
      ext.name === 'PagesExtension' && ext.is_enabled
    );
    return !!pagesExtension;
  } catch (error: any) {
    // If we get a 401/403, user is not authenticated - this is expected
    const status = error?.response?.status;
    if (status === 401 || status === 403) {
      return false;
    }
    
    // Other errors - log but don't break the app
    console.warn('Could not check extension status:', error);
    return false;
  }
}

async function createRouterWithDynamicRoutes() {
  // Check if PagesExtension is available
  const pagesExtensionAvailable = await checkPagesExtensionAvailable();
  
  const routes: RouteRecordRaw[] = [
    { path: '/user/login', name: 'Login', component: Login },
    { path: '/user/register', name: 'Register', component: Register },
    
    { path: '/user/profile', name: 'Profile', component: Profile, meta: { requiresAuth: true } },
    { path: '/user/logout', name: 'Logout', component: () => import('../views/Logout.vue') },
    { path: '/settings', name: 'Settings', component: Settings, meta: { requiresAuth: true } },
    { path: '/security', name: 'Security', component: () => import('../views/Security.vue'), meta: { requiresAuth: true } },
    { path: '/settings-editor', name: 'SettingsEditor', component: SettingsEditor, meta: { requiresAuth: true } },
    { path: '/menu-editor', name: 'MenuEditor', component: MenuEditor, meta: { requiresAuth: true } },
    { path: '/users', name: 'Users', component: Users, meta: { requiresAuth: true } },
  ];

  // Add pages routes only if extension is available
  if (pagesExtensionAvailable) {
    console.log('✅ PagesExtension detected - adding pages routes');
    
    // Individual page viewing using extension component
    routes.push({
      path: '/pages/:slug',
      name: 'PageView',
      component: () => import('@/extensions/PagesExtension_1.0.0/PageView.vue'),
      props: (route) => ({ slug: route.params.slug }),
      beforeEnter: async (to, from, next) => {
        if (!to.params.slug) {
          console.warn('No slug provided, skipping dynamic route matching.');
          next();
          return;
        }
        const incoming = String(to.params.slug).toLowerCase();
        try {
          await http.get(`/api/pages/${incoming}`);
          next();
        } catch (e: any) {
          const status = e?.response?.status;
          if (status === 404) { next('/404');

          } else if (status === 401 || status === 403) {
            next('/user/login'); }
            else { next('/404');

            }
          }
      },
    });
    
    // Pages management route using extension component
    routes.push({
      path: '/pages',
      name: 'PagesExtension',
      component: () => import('@/extensions/PagesExtension_1.0.0/PagesExtension.vue'),
      meta: { requiresAuth: true }
    });
  } else {
    console.log('❌ PagesExtension not detected - pages routes not added');
  }

  routes.push(
    { path: '/dashboard', name: 'DashboardList', component: () => import('@/views/DashboardList.vue'), meta: { requiresAuth: true } },
    { path: '/dashboard/:id/edit', name: 'DisplayEditor', component: () => import('@/views/DisplayEditor.vue'), meta: { requiresAuth: true } },
    { path: '/extensions', name: 'Extensions', component: Extensions, meta: { requiresAuth: true } },
    { path: '/@:username/:slug', name: 'PublicDisplay', component: () => import('@/views/PublicDisplay.vue') },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue') },
  );

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

export default await createRouterWithDynamicRoutes();