import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const settings = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const frontend = settings.frontend, assets = dirname(fileURLToPath(import.meta.url))
const require = createRequire(resolve(frontend, 'package.json'))
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
const { default: vue } = await import(pathToFileURL(require.resolve('@vitejs/plugin-vue')).href)
const origin = `http://127.0.0.1:${settings.port}`
const server = await createServer({
  configFile: false, envFile: false, envPrefix: 'THREE_MM_PREVIEW_PUBLIC_',
  root: settings.root, publicDir: false, cacheDir: resolve(settings.root, 'vite-cache'),
  plugins: [vue(), { name: '3mm-local-preview-info', resolveId(id) {
    if (id === '@preview-info') return '\0preview-info'
  }, load(id) { if (id === '\0preview-info') return `export default ${JSON.stringify(settings.info)}` } }],
  optimizeDeps: { entries: [resolve(settings.root, 'main.ts')] },
  resolve: { dedupe: ['vue'], alias: {
    '@preview-shell': resolve(assets, 'Shell.vue'), '@preview-app': settings.source,
    '@preview-host': settings.mock, '@preview-design': resolve(frontend, 'src/utils/ui-design.ts'),
    '@3mm/ui/v1': resolve(frontend, 'src/extension-ui/v1.ts'),
    '@3mm/application-ui/v1': resolve(frontend, 'src/extension-ui/application-v1.ts'),
    vue: resolve(frontend, 'node_modules/vue/dist/vue.runtime.esm-bundler.js'),
  } },
  server: { host: '127.0.0.1', port: settings.port, strictPort: true, open: false, cors: false,
    allowedHosts: ['127.0.0.1'], hmr: { host: '127.0.0.1' },
    fs: { strict: true, allow: [settings.root, resolve(settings.project, 'source/frontend'), resolve(settings.project, 'preview'), assets,
      resolve(frontend, 'src'), resolve(frontend, 'node_modules'), resolve(frontend, '../three_mm_protocol')] },
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws://127.0.0.1:${settings.port}; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` },
  },
})
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, async () => { await server.close(); process.exit(0) })
try {
  await server.listen()
  console.log(`Local application SIMULATION: ${origin}`)
  console.log('In-memory mock only. No Core login, installation, grants or hardware. Ctrl+C stops this preview.')
} catch (error) {
  console.error(`Preview could not start (${error?.code || 'toolchain'}). No port fallback or installation was attempted.`)
  await server.close()
  process.exitCode = 1
}
