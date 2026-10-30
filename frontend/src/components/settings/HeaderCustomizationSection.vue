<script setup lang="ts">
import { computed, ref } from 'vue'
import { UiButton, UiEditorForm, UiField } from '@/extension-ui/v1'
import SettingsSection from '@/components/SettingsSection.vue'
import ImageEditorModal from '@/components/ImageEditorModal.vue'
import { useI18n } from '@/utils/i18n'
import { useUiLabels } from '@/utils/ui-labels'
import type { ResolvedHeaderSettings } from '@/utils/header-settings'

const props = withDefaults(defineProps<{
  headerLanguage: string; availableLanguages: string[]; currentSiteName: string; currentHeaderMessage: string
  siteNameFallback: string; headerMessageFallback: string; headerSettings: ResolvedHeaderSettings
  savingHeader?: boolean; dirty?: boolean; disabled?: boolean; state?: 'idle' | 'unconfirmed'; error?: string
}>(), { savingHeader: false, dirty: false, disabled: false, state: 'idle', error: '' })
const emit = defineEmits<{
  'update:headerLanguage': [value: string]; 'update:currentSiteName': [value: string]; 'update:currentHeaderMessage': [value: string]
  'save-header-settings': []; 'logo-upload': [value: string]; 'logo-remove': []; discard: []; reload: []; 'open-theme': []
}>()
const { t } = useI18n()
const label = useUiLabels()
const languages = computed(() => props.availableLanguages.map(value => ({ value, label: value.toUpperCase() })))
const locked = computed(() => props.disabled || props.savingHeader || props.state !== 'idle')
const showImageEditor = ref(false)
const uploadError = ref('')
const editingImage = computed(() => props.headerSettings.logoUrl ? {
  url: props.headerSettings.logoUrl, name: props.headerSettings.logoUrl.split('/').pop()?.split('?')[0] || 'logo',
} : null)
const changeLogo = (value: string) => { if (!locked.value) { uploadError.value = ''; emit('logo-upload', value) } }
</script>

<template>
  <SettingsSection :title="t('settings.headerCustomization', 'Header Customization')">
    <div class="branding-workspace">
      <UiEditorForm :title="label('branding')" :description="label('brandingHelp')" :dirty="dirty" :busy="savingHeader"
        :disabled="disabled" :state="state" :error="error" :save-label="t('settings.saveHeaderSettings', 'Save Header Settings')"
        :cancel-label="label('discardDraft')" :dirty-label="label('brandingDraftHelp')" :saved-label="label('cleanDraft')"
        :unconfirmed-label="label('settingsUnconfirmed')" @save="emit('save-header-settings')" @cancel="emit('discard')">
        <UiField id="header-language" type="select" :label="t('settings.currentLanguage', 'Current Language')"
          :model-value="headerLanguage" :options="languages"
          @update:model-value="typeof $event === 'string' && emit('update:headerLanguage', $event)" />
        <UiField id="site-name" :label="`${t('settings.siteName', 'Site Name')} (${headerLanguage.toUpperCase()})`"
          :model-value="currentSiteName" :description="`${label('textFallback')}: ${siteNameFallback}`"
          @update:model-value="typeof $event === 'string' && emit('update:currentSiteName', $event)" />
        <UiField id="header-message" type="textarea" :label="`${t('settings.headerMessage', 'Header Message')} (${headerLanguage.toUpperCase()})`"
          :model-value="currentHeaderMessage" :description="`${label('textFallback')}: ${headerMessageFallback}`"
          @update:model-value="typeof $event === 'string' && emit('update:currentHeaderMessage', $event)" />
        <section class="ui-stack">
          <h3>{{ t('settings.logo', 'Logo') }}</h3>
          <p class="ui-help">{{ label('logoDraftHelp') }}</p>
          <img v-if="headerSettings.logoUrl" :src="headerSettings.logoUrl" :alt="t('settings.logo', 'Logo')" class="logo-preview" />
          <div class="ui-row">
            <UiButton data-action="edit-logo" @click="showImageEditor = true; uploadError = ''">
              {{ headerSettings.logoUrl ? t('settings.editLogo', 'Edit Logo') : t('settings.uploadLogo', 'Upload Logo') }}
            </UiButton>
            <UiButton v-if="headerSettings.logoUrl" data-action="remove-logo" variant="quiet" @click="emit('logo-remove')">{{ label('remove') }}</UiButton>
          </div>
          <p v-if="uploadError" role="alert">{{ uploadError }}</p>
        </section>
        <template #recovery><UiButton :disabled="savingHeader" data-action="reload-header" @click="emit('reload')">{{ label('reloadSaved') }}</UiButton></template>
      </UiEditorForm>
      <aside class="branding-preview ui-stack" :aria-label="label('brandingPreview')">
        <h3>{{ label('brandingPreview') }}</h3>
        <p class="ui-help">{{ label('draftPreviewOnly') }}</p>
        <div class="preview-card">
          <img v-if="headerSettings.logoUrl" :src="headerSettings.logoUrl" alt="" class="logo-preview" />
          <strong>{{ currentSiteName || siteNameFallback }}</strong>
          <span>{{ currentHeaderMessage || headerMessageFallback }}</span>
        </div>
        <UiButton data-action="theme-settings" @click="emit('open-theme')">{{ label('openThemeSettings') }}</UiButton>
        <UiButton v-if="disabled && error && state === 'idle'" :disabled="savingHeader" data-action="reload-header" @click="emit('reload')">{{ label('reloadSaved') }}</UiButton>
      </aside>
    </div>
    <ImageEditorModal v-model:show="showImageEditor" :model-value="headerSettings.logoUrl" :disabled="locked"
      extension-name="settings" upload-directory="settings" :max-size="2" :editing-image="editingImage"
      @update:model-value="changeLogo" @upload-error="uploadError = $event" />
  </SettingsSection>
</template>

<style scoped>
.branding-workspace { display: grid; grid-template-columns: minmax(0, 1fr) minmax(16rem, .8fr); align-items: start; gap: calc(var(--ui-space) * 5); }
.branding-workspace h3 { margin: 0; font-size: 1em; font-weight: 650; }
.branding-preview { min-width: 0; }
.logo-preview { max-height: 80px; max-width: min(240px, 100%); object-fit: contain; }
.preview-card { display: grid; gap: 10px; place-items: center; min-height: 150px; padding: 24px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-header-bg); color: var(--ui-header-text); overflow-wrap: anywhere; text-align: center; }
.preview-card strong { font-size: 1.2em; }
@media (max-width: 900px) { .branding-workspace { grid-template-columns: minmax(0, 1fr); } }
</style>
