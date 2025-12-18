<template>
  <SettingsSection :title="t('settings.headerCustomization', 'Header Customization')">
    <LanguageSelector
      :model-value="headerLanguage"
      :available-languages="availableLanguages"
      @update:model-value="handleLanguageChange"
      :label="t('settings.currentLanguage', 'Current Language')"
    />

    <form @submit.prevent="saveHeaderSettings">
      <div class="form-group">
        <label for="site-name" class="form-label">
          {{ t('settings.siteName', 'Site Name') }} ({{ headerLanguage.toUpperCase() }})
        </label>
        <input
          id="site-name"
          :value="currentSiteName"
          @input="handleSiteNameChange"
          type="text"
          class="input"
          :placeholder="`Site name in ${headerLanguage.toUpperCase()}`"
        />
        <small class="help-text">
          {{ t('settings.current', 'Current') }}: {{ getSettingValueForLanguage('site_name', headerLanguage) || 'Mega Monitor' }}
        </small>
      </div>

      <div class="form-group">
        <label for="header-message" class="form-label">
          {{ t('settings.headerMessage', 'Header Message') }} ({{ headerLanguage.toUpperCase() }})
        </label>
        <input
          id="header-message"
          :value="currentHeaderMessage"
          @input="handleHeaderMessageChange"
          type="text"
          class="input"
          :placeholder="`Header message in ${headerLanguage.toUpperCase()}`"
        />
        <small class="help-text">
          {{ t('settings.current', 'Current') }}: {{ getSettingValueForLanguage('header_message', headerLanguage) || 'Welcome to Mega Monitor' }}
        </small>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('settings.logo', 'Logo') }}</label>
        <div class="logo-upload-container">
          <img
            v-if="headerSettings.logoUrl"
            :src="headerSettings.logoUrl"
            alt="Logo"
            class="logo-preview"
          />
          <div class="image-upload-wrapper">
            <div class="upload-controls">
              <button
                type="button"
                class="button button-primary button-sm"
                @click="openImageEditor"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                  <polyline points="14,2 14,8 20,8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10,9 9,9 8,9"/>
                </svg>
                {{ headerSettings.logoUrl ? t('settings.editLogo', 'Edit Logo') : t('settings.uploadLogo', 'Upload Logo') }}
              </button>
              <button
                v-if="headerSettings.logoUrl"
                type="button"
                class="button button-danger button-sm"
                @click="removeLogo"
              >
                {{ t('settings.remove', 'Remove') }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="form-group">
        <ColorPicker
          label="Header Background Color"
          v-model="headerSettings.backgroundColor"
        />
        <ColorPicker
          label="Header Text Color"
          v-model="headerSettings.textColor"
        />
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('settings.preview', 'Preview') }}</label>
        <div class="preview-card">
          <img
            v-if="headerSettings.logoUrl"
            :src="headerSettings.logoUrl"
            alt="Logo"
            class="preview-logo"
          />
          <div class="preview-title">{{ currentSiteName || 'Site Name' }}</div>
          <div class="preview-message">{{ currentHeaderMessage || 'Your message here' }}</div>
        </div>
      </div>

      <button type="submit" class="button button-primary" :disabled="savingHeader">
        {{ savingHeader ? t('settings.saving', 'Saving...') : t('settings.saveHeaderSettings', 'Save Header Settings') }}
      </button>
    </form>

    <!-- Image Editor Modal -->
    <ImageEditorModal
      v-model:show="showImageEditorModal"
      v-model="headerSettings.logoUrl"
      :extension-name="'settings'"
      :upload-directory="'settings'"
      :max-size="2"
      :editing-image="editingImage"
      @upload-success="handleUploadSuccess"
      @upload-error="handleUploadError"
      @close="handleModalClose"
    />
  </SettingsSection>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'
import type { PropType } from 'vue'
import { useI18n } from '@/utils/i18n'
import SettingsSection from '@/components/SettingsSection.vue'
import LanguageSelector from '@/components/LanguageSelector.vue'
import ColorPicker from '@/components/ColorPicker.vue'
import ImageUpload from '@/components/ImageUpload.vue'
import ImageEditorModal from '@/components/ImageEditorModal.vue'

interface Setting {
  id?: number
  key: string
  value: string
  description?: string
  language_code?: string
}

export default defineComponent({
  name: 'HeaderCustomizationSection',
  components: {
    SettingsSection,
    LanguageSelector,
    ColorPicker,
    ImageUpload,
    ImageEditorModal
  },
  props: {
    headerLanguage: {
      type: String,
      required: true
    },
    availableLanguages: {
      type: Array as PropType<string[]>,
      required: true
    },
    currentSiteName: {
      type: String,
      required: true
    },
    currentHeaderMessage: {
      type: String,
      required: true
    },
    headerSettings: {
      type: Object,
      required: true
    },
    logoImages: {
      type: Array as PropType<string[]>,
      default: () => []
    },
    savingHeader: {
      type: Boolean,
      default: false
    },
    languageSettingsMap: {
      type: Object as PropType<Map<string, Setting[]>>,
      required: true
    },
  },
  emits: [
    'update:headerLanguage',
    'update:currentSiteName',
    'update:currentHeaderMessage',
    'header-language-change',
    'save-header-settings',
    'logo-upload',
    'logo-remove'
  ],
  setup(props, { emit }) {
      const { t } = useI18n()
  
      // Modal state
      const showImageEditorModal = ref(false)
      const editingImage = ref<{ url: string; name: string } | null>(null)
  
      const handleLogoUpload = (e: Event) => {
      const target = e.target as HTMLInputElement
      const file = target.files?.[0]

      if (!file) return

      if (file.size > 2 * 1024 * 1024) {
        // Error handling would be done in parent
        return
      }

      const reader = new FileReader()
      reader.onload = (event) => {
        const result = event.target?.result as string
        emit('logo-upload', result)
      }
      reader.readAsDataURL(file)
    }

    const removeLogo = () => {
      emit('logo-remove')
    }

    const logoImages = ref<string[]>([])

    const handleUploadSuccess = (file: { url: string; filename: string; size: number }) => {
      const uploadedUrl = file.url
      emit('logo-upload', uploadedUrl)
      // Update the logo URL in header settings
      props.headerSettings.logoUrl = uploadedUrl
    }

    const handleUploadError = (error: string) => {
      console.error('Upload error:', error)
      // You might want to show an error message to the user
    }

    const handleFileRemoved = (index: number) => {
      // Clear the logo URL when file is removed
      props.headerSettings.logoUrl = ''
      emit('logo-remove')
    }

    const handleImageSelected = (image: { url: string; filename: string; size: number }) => {
      const selectedUrl = image.url
      emit('logo-upload', selectedUrl)
      // Update the logo URL in header settings
      props.headerSettings.logoUrl = selectedUrl
    }

    const handleLanguageChange = (value: string) => {
      emit('update:headerLanguage', value)
      emit('header-language-change')
    }

    const handleSiteNameChange = (e: Event) => {
      const target = e.target as HTMLInputElement
      emit('update:currentSiteName', target.value)
    }

    const handleHeaderMessageChange = (e: Event) => {
      const target = e.target as HTMLInputElement
      emit('update:currentHeaderMessage', target.value)
    }

    const onHeaderLanguageChange = () => {
      emit('header-language-change')
    }

    const saveHeaderSettings = () => {
      emit('save-header-settings')
    }

    const getSettingValueForLanguage = (key: string, languageCode: string): string => {
      const langSettings = props.languageSettingsMap.get(languageCode) || []
      const setting = langSettings.find((s: Setting) => s.key === key)
      return setting?.value || ''
    }

    const openImageEditor = () => {
      if (props.headerSettings.logoUrl) {
        // Editing existing image
        const imageName = props.headerSettings.logoUrl.split('/').pop()?.split('?')[0] || 'logo'
        editingImage.value = {
          url: props.headerSettings.logoUrl,
          name: imageName
        }
      } else {
        // Uploading new image
        editingImage.value = null
      }
      showImageEditorModal.value = true
    }

    const handleModalClose = () => {
      showImageEditorModal.value = false
      editingImage.value = null
    }

    return {
      t,
      showImageEditorModal,
      editingImage,
      handleLanguageChange,
      handleSiteNameChange,
      handleHeaderMessageChange,
      handleLogoUpload,
      removeLogo,
      onHeaderLanguageChange,
      saveHeaderSettings,
      getSettingValueForLanguage,
      logoImages,
      handleUploadSuccess,
      handleUploadError,
      handleFileRemoved,
      handleImageSelected,
      openImageEditor,
      handleModalClose
    }
  }
})
</script>

<style scoped>
.logo-upload-container {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo-preview {
  max-height: 60px;
  max-width: 200px;
}

.preview-card {
  padding: 1rem;
  border-radius: 8px;
  text-align: center;
  background-color: v-bind('headerSettings.backgroundColor');
  color: v-bind('headerSettings.textColor');
  border: 1px solid var(--color-border);
}

.preview-logo {
  max-height: 60px;
  margin-bottom: 10px;
  display: block;
  margin-left: auto;
  margin-right: auto;
}

.preview-title {
  font-weight: bold;
  font-size: 1.25rem;
  margin-bottom: 0.5rem;
}

.preview-message {
  font-size: 0.875rem;
}
</style>

<style scoped>
.image-upload-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

</style>
