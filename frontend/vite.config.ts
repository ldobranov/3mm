import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import vueDevTools from 'vite-plugin-vue-devtools'

// Load config from root config.json
const configPath = join(__dirname, '..', 'config.json')
let config
try {
  config = JSON.parse(readFileSync(configPath, 'utf-8'))
} catch (error) {
  console.warn('Could not load config.json, using defaults:', error)
  config = {
    frontend: {
      backend_url: 'http://localhost:8887',
      frontend_url: 'http://localhost:5173'
    },
    backend: {
      database_url: 'postgresql://lazar:admin@localhost:5432/mega_monitor',
      host: '0.0.0.0',
      port: 8887
    }
  }
}
const backendUrl = config.frontend.backend_url

// Define global constants for frontend
const defineConstants = {
  __BACKEND_URL__: JSON.stringify(backendUrl),
  __FRONTEND_URL__: JSON.stringify(config.frontend.frontend_url)
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueJsx(),
    vueDevTools(),
  ],
  define: defineConstants,
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
    host: 'localhost', // Bind to localhost for local development
    fs: {
      allow: ['..'] // Allow serving files from parent directories
    },
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      '/frontend-config': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      '/display': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      '/marketplace': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      '/monitoring': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      '/api/extensions/hiveos/api': {
        target: backendUrl,
        changeOrigin: false,
        secure: true,
        rewrite: (path) => path.replace(/^\/api\/extensions\/hiveos\/api/, '/api')
      },
      '/uploads': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
