import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const toolchain = resolve(process.env.THREE_MM_FRONTEND_DIR || resolve(root, '../../frontend'))
const requireCore = createRequire(resolve(toolchain, 'package.json'))
const { defineConfig } = await import(pathToFileURL(requireCore.resolve('vitest/config')).href)
const { default: vue } = await import(pathToFileURL(requireCore.resolve('@vitejs/plugin-vue')).href)
export default defineConfig({
  root, plugins: [vue()], server: { fs: { allow: [root, toolchain] } },
  resolve: { alias: {
    '@3mm/ui/v1': resolve(toolchain, 'src/extension-ui/v1.ts'),
    '@3mm/application-ui/v1': resolve(toolchain, 'src/extension-ui/application-v1.ts'),
    vue: resolve(toolchain, 'node_modules/vue/dist/vue.runtime.esm-bundler.js'),
    vitest: resolve(toolchain, 'node_modules/vitest/dist/index.js'),
    '@vue/test-utils': resolve(toolchain, 'node_modules/@vue/test-utils/dist/vue-test-utils.esm-bundler.mjs'),
  } }, test: { environment: 'jsdom', include: ['tests/ui.test.ts'] },
})
