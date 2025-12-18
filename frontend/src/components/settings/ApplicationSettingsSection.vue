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

    return {
      t,
      defaultTheme,
      defaultLanguage,
      updateDefaultTheme,
      updateDefaultLanguage,
      isAuthenticated,
      isAdmin
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