import { createApp } from 'vue';
import App from './App.vue';
import routerPromise from './router';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';

async function bootstrap() {
  const app = createApp(App);
  const router = await routerPromise; // Wait for the router to be initialized
  app.use(router);
  app.mount('#app');
}

bootstrap();