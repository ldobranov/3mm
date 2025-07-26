import { createRouter, createWebHistory } from 'vue-router';
import type { RouteRecordRaw } from 'vue-router';
import Login from '../views/Login.vue';
import Register from '../views/Register.vue';
import Settings from '../views/Settings.vue';
import SettingsEditor from '../views/SettingsEditor.vue';
import MenuEditor from '../views/MenuEditor.vue';
import Users from '../views/Users.vue';
import Profile from '../views/Profile.vue';
import Pages from '@/views/Pages.vue';
import PageView from '@/views/PageView.vue';
import axios from 'axios';
import RaspberryController from '@/views/RaspberryController.vue';
import hiveosRoutes from '@/extensions/hiveos';
import ManagerRouter from '../extensions/manager';

async function fetchDynamicRoutesForPages() {
  try {
    console.log('Fetching dynamic routes for pages...');
    const response = await axios.get(`${import.meta.env.VITE_API_BASE_URL}/pages/read`);
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

async function createRouterWithDynamicRoutes() {
  const routes: RouteRecordRaw[] = [
    { path: '/login', component: Login },
    { path: '/register', component: Register },
    { path: '/settings', name: 'Settings', component: Settings },
    { path: '/settings-editor', name: 'SettingsEditor', component: SettingsEditor },
    { path: '/menu-editor', name: 'MenuEditor', component: MenuEditor },
    { path: '/users', name: 'Users', component: Users },
    { path: '/profile', name: 'Profile', component: Profile },
    { path: '/raspberry-controller', name: 'RaspberryController', component: RaspberryController },
    { path: '/pages', name: 'Pages', component: Pages },
    {
      path: '/pages/:slug',
      name: 'PageView',
      component: PageView,
      props: (route) => ({ slug: route.params.slug }),
      beforeEnter: async (to, from, next) => {
        if (!to.params.slug) {
          console.warn('No slug provided, skipping dynamic route matching.');
          next();
          return;
        }

        const dynamicRoutes = await fetchDynamicRoutesForPages();
        console.log('Dynamic routes:', dynamicRoutes);
        console.log('Requested slug:', to.params.slug);

        const matchingRoute = dynamicRoutes.find((route: { slug: string }) => route.slug === to.params.slug);
        if (matchingRoute) {
          console.log('Matching route found:', matchingRoute);
          next();
        } else {
          console.warn('No matching route found for slug:', to.params.slug);
          next('/404');
        }
      },
    },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue') },
    ...hiveosRoutes,
    ...ManagerRouter.getRoutes(),
  ];

  return createRouter({
    history: createWebHistory(),
    routes,
  });
}

const routerPromise = createRouterWithDynamicRoutes();

export default routerPromise;