import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@/extensions': fileURLToPath(new URL('./src/extensions', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
      },
      external: ['@vueup/vue-quill'],
    },
  },
  server: {
    fs: {
      allow: ['..'], // Allow serving files from parent directories
    },
    proxy: {
      '/api/extensions/hiveos/api': {
        target: 'http://localhost:8887',
        changeOrigin: false,
        secure: true,
        rewrite: (path) => path.replace(/^\/api\/extensions\/hiveos\/api/, '/api')
      },
    },
  },
})
