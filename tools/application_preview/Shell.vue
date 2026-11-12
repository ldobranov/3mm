<script setup lang="ts">
import { computed, onUnmounted, provide, ref, watchEffect } from 'vue'
import { applicationHostKey } from '@platform/application-ui/v1'
import App from '@preview-app'
import { createPreview } from '@preview-host'
import info from '@preview-info'
import { builtinUiDesign, uiDesignVariables } from '@preview-design'

const preview = createPreview(info), instance = ref(0), scenario = ref(preview.scenarios[0].id)
const locale = ref('en'), mode = ref<'light' | 'dark'>('light'), narrow = ref(false)
provide(applicationHostKey, preview.host)
const title = computed(() => `${info.module_id} · ${info.active_version}`)
watchEffect(() => {
  const design = builtinUiDesign()
  const header = { siteName: '', headerMessage: '', logoUrl: '', backgroundColor: '#ffffff', textColor: '#111111' }
  for (const [key, value] of Object.entries(uiDesignVariables(design, mode.value, header))) {
    document.documentElement.style.setProperty(key, value as string)
  }
})
function reset() { preview.reset(); scenario.value = preview.scenarios[0].id; instance.value++ }
function language() { preview.setLocale(locale.value) }
onUnmounted(() => preview.dispose())
</script>

<template>
  <main class="preview-workspace">
    <header class="preview-toolbar">
      <div><strong>LOCAL SIMULATION · NOT AN INSTALLED APPLICATION</strong><p>{{ title }}</p></div>
      <p>Mock data lives only in this tab. This does not prove Core permissions, provider health or physical execution.</p>
      <div class="preview-controls">
        <label>Scenario<select v-model="scenario" @change="preview.selectScenario(scenario)">
          <option v-for="item in preview.scenarios" :key="item.id" :value="item.id">{{ item.label }}</option>
        </select></label>
        <label>Language<select v-model="locale" @change="language"><option>en</option><option>bg</option></select></label>
        <label>Theme<select v-model="mode"><option value="light">Light</option><option value="dark">Dark</option></select></label>
        <label class="preview-checkbox"><input v-model="narrow" type="checkbox">390px</label>
        <button @click="reset">Reset simulated data</button>
      </div>
      <p>Scenario changes affect the next app request. Use the app's Reload control; saves are never repeated automatically.</p>
    </header>
    <section class="preview-stage" :class="{ narrow }" aria-label="Simulated application">
      <App :key="instance" />
    </section>
  </main>
</template>

<style>
body { margin: 0; background: var(--ui-canvas); color: var(--ui-text); font-family: var(--ui-font); color-scheme: var(--ui-color-scheme); }
.preview-workspace { padding: 20px; }
.preview-toolbar { max-width: 1100px; margin: 0 auto 24px; padding: 20px; border: 2px solid var(--ui-warning); border-radius: 12px; background: var(--ui-surface); }
.preview-toolbar p { margin: 8px 0; line-height: 1.5; overflow-wrap: anywhere; }
.preview-controls { display: flex; flex-wrap: wrap; align-items: end; gap: 14px; margin: 16px 0; }
.preview-controls label { display: grid; gap: 6px; font-size: 14px; }
.preview-controls select, .preview-controls button { min-height: 40px; padding: 8px 12px; font: inherit; color: var(--ui-text); background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: 6px; max-width: 100%; }
.preview-controls .preview-checkbox { display: flex; align-items: center; min-height: 40px; }
.preview-stage { margin: auto; max-width: 1100px; }
.preview-stage.narrow { max-width: 390px; }
@media(max-width: 520px) { .preview-workspace { padding: 8px; } .preview-toolbar { padding: 12px; } .preview-controls { display: grid; } }
</style>
