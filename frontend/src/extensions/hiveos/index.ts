import type { RouteRecordRaw } from 'vue-router';
import HiveOSView from './views/HiveOSView.vue';

const routes: RouteRecordRaw[] = [
  {
    path: '/extensions/hiveos',
    name: 'HiveOS',
    component: HiveOSView
  }
];

export default routes;
