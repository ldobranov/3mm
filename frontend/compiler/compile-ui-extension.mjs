import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import vue from '@vitejs/plugin-vue'
import { build } from 'vite'

const [, , workspaceArg, outputArg] = process.argv
if (!workspaceArg || !outputArg) throw new Error('usage: compile-ui-extension.mjs <workspace> <output>')
const workspace = resolve(workspaceArg)
const output = resolve(outputArg)
const contract = JSON.parse(await readFile(resolve(workspace, 'compiled-ui.json'), 'utf8'))
const input = Object.fromEntries(contract.entrypoints.map(item => [item.entrypoint_id, resolve(workspace, item.source)]))
await mkdir(output, { recursive: true })
const result = await build({
  configFile: false, root: workspace, publicDir: false, plugins: [vue()],
  build: {
    outDir: output, emptyOutDir: true, cssCodeSplit: false, minify: true, sourcemap: false,
    rollupOptions: {
      input, external: ['vue'], preserveEntrySignatures: 'strict',
      output: { format: 'es', entryFileNames: 'assets/[name]-[hash].mjs', chunkFileNames: 'assets/chunk-[hash].mjs', assetFileNames: 'assets/[name]-[hash][extname]' }
    }
  }
})
const entries = {}
const styles = new Set()
for (const buildResult of (Array.isArray(result) ? result : [result])) {
  for (const item of buildResult.output) {
    if (item.type === 'chunk' && item.isEntry && item.name in input) entries[item.name] = item.fileName
    if (item.type === 'asset' && item.fileName.endsWith('.css')) styles.add(item.fileName)
  }
}
for (const item of contract.entrypoints) {
  if (!entries[item.entrypoint_id]) throw new Error(`compiler did not emit entrypoint: ${item.entrypoint_id}`)
}
await writeFile(resolve(output, 'entrypoints.json'), `${JSON.stringify({ entries, styles: [...styles].sort() }, null, 2)}\n`, 'utf8')
