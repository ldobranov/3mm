import { createRouter, createWebHistory } from 'vue-router';
import ManagerView from './views/ManagerView.vue';

const routes = [
  {
    path: '/extensions/manager',
    name: 'Manager',
    component: ManagerView,
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
