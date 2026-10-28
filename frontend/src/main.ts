import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/js/dist/collapse';
// If using Tailwind, ensure the file exists and Tailwind is configured
// import '@/assets/tailwind.css';

import { captureKioskLink } from '@/utils/kiosk-session';
captureKioskLink();

import { initAuthLifecycle } from '@/utils/auth';
import { initializeI18n } from '@/utils/i18n';
import { createRouterWithDynamicRoutes } from '@/router';

async function bootstrap() {
  const app = createApp(App);

  // Install Pinia BEFORE using the router to ensure stores are available
  const pinia = createPinia();
  app.use(pinia);

  // Initialize i18n system FIRST (before router) to ensure language is set early
  await initializeI18n();

  const router = await createRouterWithDynamicRoutes();
  app.use(router);


  // Start auth lifecycle (activity-aware refresh + auto-logout on expiry)
  initAuthLifecycle();

  app.mount('#app');
}

bootstrap();
