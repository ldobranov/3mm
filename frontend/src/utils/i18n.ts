/**
 * Frontend internationalization (i18n) utilities
 */

import { ref, computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import http from '@/utils/http'

interface Translations {
  [key: string]: any
}

class FrontendI18n {
  private translations: Map<string, Translations> = new Map()
  private currentLanguage = ref('en')
  private defaultLanguage = 'en'
  private settingsStore: any = null

  constructor() {
    // Initialize with built-in English translations as fallback
    this.translations.set('en', this.getDefaultTranslations())
  }

  // Default English translations
  private getDefaultTranslations(): Translations {
    return {
      'common.login': 'Login',
      'common.register': 'Register',
      'common.logout': 'Logout',
      'common.save': 'Save',
      'common.cancel': 'Cancel',
      'common.edit': 'Edit',
      'common.delete': 'Delete',
      'common.create': 'Create',
      'common.update': 'Update',
      'common.settings': 'Settings',
      'common.language': 'Language',
      'common.english': 'English',
      'common.bulgarian': 'Bulgarian',
      'navigation.home': 'Home',
      'navigation.dashboard': 'Dashboard',
      'navigation.pages': 'Pages',
      'navigation.settings': 'Settings',
      'navigation.users': 'Users',
      'navigation.extensions': 'Extensions',
      'pages.title': 'Pages Management',
      'pages.createNew': 'Create New Page',
      'pages.existing': 'Existing Pages',
      'pages.noPages': 'No pages found.',
      'pages.public': 'Public',
      'pages.private': 'Private',
      'pages.titleLabel': 'Title',
      'pages.contentLabel': 'Content',
      'pages.slugLabel': 'Slug',
      'pages.makePublic': 'Make page public',
      'pages.editPage': 'Edit Page',
      'pages.createPage': 'Create New Page',
      'pages.confirmDelete': 'Confirm Delete',
      'pages.deleteConfirmMessage': 'Are you sure you want to delete the page "{title}"?',
      'widgets.clock': 'Clock',
      'widgets.systemMonitor': 'System Monitor',
      'widgets.rss': 'RSS Feed',
      'widgets.text': 'Text',
    }
  }

  setSettingsStore(store: any) {
    this.settingsStore = store
  }

  // Load translations from a language pack
  loadLanguagePack(languageCode: string, translations: Translations) {
    this.translations.set(languageCode, { ...this.getDefaultTranslations(), ...translations })
    console.log(`Loaded ${languageCode} translations:`, this.translations.get(languageCode))
  }

  // Set current language
  async setLanguage(languageCode: string) {
    if (languageCode === this.currentLanguage.value) {
      return
    }

    if (!this.translations.has(languageCode)) {
      // Try to load from backend
      await this.loadTranslationsFromBackend(languageCode)
    }

    if (this.translations.has(languageCode)) {
      this.currentLanguage.value = languageCode
      // Update setting in backend if settings store is available
      if (this.settingsStore) {
        try {
          await this.settingsStore.updateSetting('language', languageCode)
        } catch (error) {
          console.warn('Failed to update language setting:', error)
        }
      }
    } else {
      console.warn(`Language ${languageCode} not found, falling back to ${this.defaultLanguage}`)
      this.currentLanguage.value = this.defaultLanguage
    }
  }

  // Load translations from backend
  private async loadTranslationsFromBackend(languageCode: string) {
    try {
      // This would typically fetch from an API endpoint
      // For now, we'll just log the attempt
      console.log(`Attempting to load translations for ${languageCode} from backend`)
    } catch (error) {
      console.error('Failed to load translations from backend:', error)
    }
  }

  // Get current language
  getCurrentLanguage() {
    return this.currentLanguage.value
  }

  // Get available languages
  getAvailableLanguages() {
    return Array.from(this.translations.keys())
  }

  // Translate a key
  t(key: string, params?: Record<string, string>): string {
    let translation = this.getNestedValue(this.translations.get(this.currentLanguage.value) || {}, key)
    
    // Fallback to English
    if (!translation) {
      translation = this.getNestedValue(this.translations.get(this.defaultLanguage) || {}, key)
    }

    if (!translation) {
      return key // Return key if no translation found
    }

    // Replace parameters if provided
    if (params) {
      for (const [param, value] of Object.entries(params)) {
        translation = translation.replace(`{${param}}`, value)
      }
    }

    return translation
  }

  // Helper to get nested value using dot notation
  private getNestedValue(obj: any, key: string): string | null {
    return key.split('.').reduce((current: any, part: string) => {
      return current && current[part] !== undefined ? current[part] : null
    }, obj)
  }

  // Check if a language is available
  isLanguageAvailable(languageCode: string): boolean {
    return this.translations.has(languageCode)
  }
}

// Create global instance
export const i18n = new FrontendI18n()

// Helper function for component usage
export const useI18n = () => {
  const t = (key: string, params?: Record<string, string>) => i18n.t(key, params)
  const setLanguage = (language: string) => i18n.setLanguage(language)
  const currentLanguage = computed(() => i18n.getCurrentLanguage())
  const availableLanguages = computed(() => i18n.getAvailableLanguages())

  return {
    t,
    setLanguage,
    currentLanguage,
    availableLanguages
  }
}

// Initialize settings store
export const initializeI18n = async () => {
  const settingsStore = useSettingsStore()
  i18n.setSettingsStore(settingsStore)
  
  // Try to get current language from settings
  try {
    const response = await http.get('/settings/read')
    const settings = response.data.items || []
    const currentLangSetting = settings.find((s: any) => s.key === 'language')
    if (currentLangSetting && i18n.isLanguageAvailable(currentLangSetting.value)) {
      await i18n.setLanguage(currentLangSetting.value)
    }
  } catch (error) {
    console.warn('Failed to get language from settings:', error)
  }
}