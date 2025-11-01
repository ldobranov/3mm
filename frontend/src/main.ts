import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import routerPromise from './router';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
// If using Tailwind, ensure the file exists and Tailwind is configured
// import '@/assets/tailwind.css';

import { initAuthLifecycle } from '@/utils/auth';

async function bootstrap() {
  const app = createApp(App);

  // Install Pinia BEFORE using the router to ensure stores are available
  const pinia = createPinia();
  app.use(pinia);

  const router = await routerPromise; // Wait for the router to be initialized
  app.use(router);

  // Start auth lifecycle (activity-aware refresh + auto-logout on expiry)
  initAuthLifecycle();

  app.mount('#app');
}

bootstrap();