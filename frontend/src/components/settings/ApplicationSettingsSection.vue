<template>
  <SettingsSection :title="t('applicationSettings', 'Application Settings')">
    <template v-if="isAdmin">
      <ThemeSelector
        :model-value="defaultTheme"
        @update:model-value="updateDefaultTheme"
        :label="t('settings.defaultTheme', 'Default Theme')"
      />

      <LanguageSelector
        :model-value="defaultLanguage"
        :available-languages="availableLanguages"
        @update:model-value="updateDefaultLanguage"
        :label="t('settings.defaultLanguage', 'Default Language')"
      />
      <div class="admin-info">
        <p>{{ t('settings.adminInfo', 'These settings apply to new and unregistered users.') }}</p>
        <p>{{ t('settings.adminInfo2', 'Logged-in users can set their own preferences using the header selectors.') }}</p>
      </div>

      <div class="admin-info" style="margin-top: 1rem;">
        <h3 style="margin: 0 0 0.5rem;">{{ t('settings.aiProvider.title', 'AI Provider (Extension Builder)') }}</h3>

        <div class="form-group">
          <label class="form-label">{{ t('settings.aiProvider.provider', 'Provider') }}</label>
          <select class="input" v-model="aiProvider">
            <option value="">{{ t('settings.aiProvider.auto', 'Auto') }}</option>
            <option value="groq">Groq</option>
            <option value="openrouter">OpenRouter</option>
          </select>
          <small class="help-text">
            {{ t('settings.aiProvider.providerHelp', 'Auto prefers Groq when configured, otherwise OpenRouter.') }}
          </small>
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('settings.aiProvider.groqKey', 'Groq API Key') }}</label>
          <input
            class="input"
            type="password"
            v-model="groqKeyInput"
            :placeholder="t('settings.aiProvider.keyPlaceholder', 'Leave blank to keep current')"
          />
          <small class="help-text">
            {{ t('settings.aiProvider.groqStatus', 'Configured:') }}
            <strong>{{ aiStatus.has_groq_key ? t('common.yes', 'Yes') : t('common.no', 'No') }}</strong>
          </small>
          <button class="button button-secondary" @click="clearGroqKey" style="margin-top: 0.5rem;">
            {{ t('settings.aiProvider.clearGroq', 'Clear Groq key') }}
          </button>
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('settings.aiProvider.openrouterKey', 'OpenRouter API Key') }}</label>
          <input
            class="input"
            type="password"
            v-model="openrouterKeyInput"
            :placeholder="t('settings.aiProvider.keyPlaceholder', 'Leave blank to keep current')"
          />
          <small class="help-text">
            {{ t('settings.aiProvider.openrouterStatus', 'Configured:') }}
            <strong>{{ aiStatus.has_openrouter_key ? t('common.yes', 'Yes') : t('common.no', 'No') }}</strong>
          </small>
          <button class="button button-secondary" @click="clearOpenRouterKey" style="margin-top: 0.5rem;">
            {{ t('settings.aiProvider.clearOpenrouter', 'Clear OpenRouter key') }}
          </button>
        </div>

        <div style="display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem;">
          <button class="button button-primary" @click="saveAiSettings">
            {{ t('settings.aiProvider.save', 'Save AI settings') }}
          </button>
          <span v-if="aiSaveMessage" class="help-text">{{ aiSaveMessage }}</span>
        </div>
      </div>
    </template>
    <template v-else-if="isAuthenticated">
      <div class="user-preferences-info">
        <p>{{ t('settings.userPreferencesInfo', 'Your language and theme preferences are managed through the header selectors.') }}</p>
        <p>{{ t('settings.headerSelectorsInfo', 'Use the language dropdown and theme toggle in the header to customize your personal preferences.') }}</p>
      </div>
    </template>
    <template v-else>
      <div class="guest-info">
        <p>{{ t('settings.guestInfo', 'Please log in to access application settings.') }}</p>
      </div>
    </template>
  </SettingsSection>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue'
import type { PropType } from 'vue'
import { useI18n } from '@/utils/i18n'
import http from '@/utils/dynamic-http'
import SettingsSection from '@/components/SettingsSection.vue'
import ThemeSelector from '@/components/ThemeSelector.vue'
import LanguageSelector from '@/components/LanguageSelector.vue'

interface Setting {
  id?: number
  key: string
  value: string
  description?: string
  language_code?: string
}

export default defineComponent({
  name: 'ApplicationSettingsSection',
  components: {
    SettingsSection,
    ThemeSelector,
    LanguageSelector
  },
  props: {
    availableLanguages: {
      type: Array as PropType<string[]>,
      required: true
    }
  },
  // No emits needed since we handle saving internally
  setup(props, { emit }) {
    const { t } = useI18n()
    const defaultTheme = ref<'light' | 'dark'>('light')
    const defaultLanguage = ref('en')
    const isAuthenticated = ref(!!localStorage.getItem('authToken'))
    const isAdmin = ref(localStorage.getItem('role') === 'admin')

    const aiProvider = ref<string>('')
    const groqKeyInput = ref<string>('')
    const openrouterKeyInput = ref<string>('')
    const aiSaveMessage = ref<string>('')

    const aiStatus = ref<{ provider: string | null; has_groq_key: boolean; has_openrouter_key: boolean }>({
      provider: null,
      has_groq_key: false,
      has_openrouter_key: false
    })

    // Load current defaults on mount
    onMounted(async () => {
      try {
        const response = await http.get('/settings/read')
        const items = response.data.items || []
        const themeSetting = items.find((s: any) => s.key === 'default_theme')
        const langSetting = items.find((s: any) => s.key === 'default_language')
        if (themeSetting && (themeSetting.value === 'light' || themeSetting.value === 'dark')) {
          defaultTheme.value = themeSetting.value
        }
        if (langSetting) {
          defaultLanguage.value = langSetting.value
        }

        // Load AI settings status (admin only)
        if (isAdmin.value) {
          try {
            const aiRes = await http.get('/api/admin/ai-settings')
            aiStatus.value = aiRes.data
            aiProvider.value = aiRes.data?.provider || ''
          } catch (e) {
            console.error('Failed to load AI settings:', e)
          }
        }
      } catch (e) {
        console.error('Failed to load defaults:', e)
      }
    })

    const updateDefaultTheme = async (newTheme: 'light' | 'dark') => {
      defaultTheme.value = newTheme
      await saveDefault('default_theme', newTheme)
    }

    const updateDefaultLanguage = async (newLanguage: string) => {
      defaultLanguage.value = newLanguage
      await saveDefault('default_language', newLanguage)
    }

    const saveDefault = async (key: string, value: string) => {
      try {
        await http.post('/settings/create', {
          key,
          value,
          description: `Default ${key.replace('default_', '')} for new users`,
          language_code: ''
        })
      } catch (e) {
        console.error(`Failed to save ${key}:`, e)
      }
    }

    const saveAiSettings = async () => {
      aiSaveMessage.value = ''
      try {
        const payload: any = { provider: aiProvider.value }

        // Only send keys if user typed something; blank means keep current.
        if (groqKeyInput.value.trim().length > 0) payload.groq_api_key = groqKeyInput.value.trim()
        if (openrouterKeyInput.value.trim().length > 0) payload.openrouter_api_key = openrouterKeyInput.value.trim()

        const res = await http.post('/api/admin/ai-settings', payload)
        aiStatus.value = res.data
        groqKeyInput.value = ''
        openrouterKeyInput.value = ''
        aiSaveMessage.value = t('settings.saved', 'Saved')
      } catch (e) {
        console.error('Failed to save AI settings:', e)
        const err: any = e
        aiSaveMessage.value = err?.response?.data?.detail || t('settings.saveFailed', 'Save failed')
      }
    }

    const clearGroqKey = async () => {
      try {
        const res = await http.post('/api/admin/ai-settings', { provider: aiProvider.value, groq_api_key: '' })
        aiStatus.value = res.data
        aiSaveMessage.value = t('settings.saved', 'Saved')
      } catch (e) {
        console.error('Failed to clear Groq key:', e)
        const err: any = e
        aiSaveMessage.value = err?.response?.data?.detail || t('settings.saveFailed', 'Save failed')
      }
    }

    const clearOpenRouterKey = async () => {
      try {
        const res = await http.post('/api/admin/ai-settings', { provider: aiProvider.value, openrouter_api_key: '' })
        aiStatus.value = res.data
        aiSaveMessage.value = t('settings.saved', 'Saved')
      } catch (e) {
        console.error('Failed to clear OpenRouter key:', e)
        const err: any = e
        aiSaveMessage.value = err?.response?.data?.detail || t('settings.saveFailed', 'Save failed')
      }
    }

    return {
      t,
      defaultTheme,
      defaultLanguage,
      updateDefaultTheme,
      updateDefaultLanguage,
      isAuthenticated,
      isAdmin,

      aiProvider,
      groqKeyInput,
      openrouterKeyInput,
      aiStatus,
      aiSaveMessage,
      saveAiSettings,
      clearGroqKey,
      clearOpenRouterKey
    }
  }
})
</script>

<style scoped>
/* Uses existing .form-group, .form-label, .input, .help-text, .button, .button-primary classes */

.user-preferences-info,
.admin-info,
.guest-info {
  padding: 1rem;
  background-color: var(--color-background-soft);
  border-radius: var(--border-radius-sm);
  margin-bottom: 1rem;
}

.user-preferences-info p,
.admin-info p,
.guest-info p {
  margin: 0.5rem 0;
  color: var(--color-text-secondary);
}

.admin-info {
  background-color: var(--color-background-soft);
  border-left: 3px solid var(--color-primary);
}

.guest-info {
  background-color: var(--color-background-soft);
  border-left: 3px solid var(--color-warning);
}
</style>
