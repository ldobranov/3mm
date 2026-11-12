import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: { alias: {
      '@platform/application-ui/v1': fileURLToPath(new URL('./src/extension-ui/application-v1.ts', import.meta.url)),
      '@platform/ui/v1': fileURLToPath(new URL('./src/extension-ui/v1.ts', import.meta.url)),
    } },
    test: {
      environment: 'jsdom',
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
