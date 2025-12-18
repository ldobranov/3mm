import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import routerPromise from './router';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
// If using Tailwind, ensure the file exists and Tailwind is configured
// import '@/assets/tailwind.css';

import { initAuthLifecycle } from '@/utils/auth';
import { initializeI18n, i18n } from '@/utils/i18n';
import { extensionRelationships } from '@/utils/extension-relationships';
import { reloadExtensionRoutes } from '@/router';

async function bootstrap() {
  const app = createApp(App);

  // Install Pinia BEFORE using the router to ensure stores are available
  const pinia = createPinia();
  app.use(pinia);

  // Initialize i18n system FIRST (before router) to ensure language is set early
  await initializeI18n();

  // Initialize extension relationships system
  await extensionRelationships.initialize();

  const router = await routerPromise; // Wait for the router to be initialized
  app.use(router);

  // Reload extension routes with full dynamic discovery now that extensions are initialized
  await reloadExtensionRoutes(router);

  // Start auth lifecycle (activity-aware refresh + auto-logout on expiry)
  initAuthLifecycle();

  // Refresh extensions now that auth is initialized (to load enabled extensions from database)
  await extensionRelationships.refreshExtensions();

  // Reload extension translations now that enabled extensions are known
  await i18n.loadExtensionTranslationsForEnabledExtensions();

  app.mount('#app');
}

bootstrap();