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

      <div class="admin-info session-settings-card">
        <div>
          <h3>{{ t('settings.sessionDuration.title', 'Signed-in session') }}</h3>
          <p>{{ t('settings.sessionDuration.help', 'Choose how long this device remembers a signed-in browser. Active sessions renew automatically.') }}</p>
        </div>
        <div class="form-group session-duration-control">
          <label class="form-label" for="session-duration-hours">
            {{ t('settings.sessionDuration.label', 'Session duration (hours)') }}
          </label>
          <input
            id="session-duration-hours"
            v-model.number="sessionDurationHours"
            class="input ui-control"
            type="number"
            :min="sessionDurationMinimum"
            :max="sessionDurationMaximum"
            step="1"
          />
          <small class="help-text">
            {{ t('settings.sessionDuration.range', 'Allowed range: 1 hour to 30 days.') }}
          </small>
        </div>
        <div class="settings-actions">
          <button class="ui-button ui-button--primary" :disabled="sessionDurationSaving" @click="saveSessionDuration">
            {{ sessionDurationSaving ? t('common.saving', 'Saving…') : t('settings.sessionDuration.save', 'Save session duration') }}
          </button>
          <span v-if="sessionDurationMessage" class="help-text" role="status">{{ sessionDurationMessage }}</span>
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

    const sessionDurationHours = ref<number>(168)
    const sessionDurationMinimum = ref<number>(1)
    const sessionDurationMaximum = ref<number>(720)
    const sessionDurationSaving = ref(false)
    const sessionDurationMessage = ref('')

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

        // Load Core session settings for administrators
        if (isAdmin.value) {
          try {
            const sessionRes = await http.get('/api/admin/session-settings')
            sessionDurationHours.value = sessionRes.data?.duration_hours || 168
            sessionDurationMinimum.value = sessionRes.data?.minimum_hours || 1
            sessionDurationMaximum.value = sessionRes.data?.maximum_hours || 720
          } catch (e) {
            console.error('Failed to load session settings:', e)
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

    const saveSessionDuration = async () => {
      sessionDurationMessage.value = ''
      sessionDurationSaving.value = true
      try {
        const res = await http.put('/api/admin/session-settings', {
          duration_hours: sessionDurationHours.value
        })
        sessionDurationHours.value = res.data.duration_hours
        sessionDurationMessage.value = t('settings.sessionDuration.saved', 'Session duration saved')
      } catch (e: any) {
        sessionDurationMessage.value = e?.response?.data?.detail || t('settings.saveFailed', 'Save failed')
      } finally {
        sessionDurationSaving.value = false
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

      sessionDurationHours,
      sessionDurationMinimum,
      sessionDurationMaximum,
      sessionDurationSaving,
      sessionDurationMessage,
      saveSessionDuration,
    }
  }
})
</script>

<style scoped>
.admin-info, .user-preferences-info, .guest-info { display: grid; gap: calc(var(--ui-space) * 4); padding: calc(var(--ui-space) * 4); background: var(--ui-surface-alt); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); margin-bottom: calc(var(--ui-space) * 4); min-width: 0; }
.user-preferences-info p, .admin-info p, .guest-info p { margin: 0; color: var(--ui-text-secondary); }
.admin-info h3 { margin: 0; font-size: 1rem; font-weight: 650; color: var(--ui-text); }
.session-duration-control { max-width: 22rem; }
.settings-actions { display: flex; flex-wrap: wrap; gap: calc(var(--ui-space) * 3); align-items: center; }
.admin-info .form-group { display: grid; gap: calc(var(--ui-space) * 2); margin-bottom: 0; min-width: 0; }
</style>
