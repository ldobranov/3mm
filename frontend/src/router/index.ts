import { createRouter, createWebHistory } from 'vue-router';
import Login from '../views/Login.vue';
import Register from '../views/Register.vue';
import Settings from '../views/Settings.vue';
import SettingsEditor from '../views/SettingsEditor.vue';
import MenuEditor from '../views/MenuEditor.vue';
import Users from '../views/Users.vue';
import Profile from '../views/Profile.vue';
import Pages from '@/views/Pages.vue';
import axios from 'axios';

async function fetchDynamicRoutes() {
  try {
    const response = await axios.get('/pages'); // Assuming the backend provides a list of pages
    const pages = Array.isArray(response.data) ? response.data : [];
    return pages.map((page: { slug: string }) => ({
      path: `/${page.slug}`,
      component: Pages, // Use the existing Pages component
      props: { slug: page.slug },
    }));
  } catch (error) {
    console.error('Failed to fetch dynamic routes:', error);
    return [];
  }
}

const dynamicRoutes = await fetchDynamicRoutes();

const routes = [
  { path: '/login', component: Login },
  { path: '/register', component: Register },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings,
  },
  {
    path: '/settings-editor',
    name: 'SettingsEditor',
    component: SettingsEditor,
  },
  {
    path: '/menu-editor',
    name: 'MenuEditor',
    component: MenuEditor,
  },
  { path: '/users', name: 'Users', component: Users },
  {
    path: '/profile',
    name: 'Profile',
    component: Profile,
  },
  ...dynamicRoutes,
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('../views/NotFound.vue'), // Lazy load a 404 component
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;