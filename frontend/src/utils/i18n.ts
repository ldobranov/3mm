/**
 * Clean, simple internationalization (i18n) utilities
 */

import { ref, computed } from 'vue'
import { readAvailableLanguages, readFrontendTranslations, saveCurrentUserLanguage } from '@/utils/language-api'
import coreEnglish from '@/locales/en.json'

interface Translations {
  [key: string]: any
}

class FrontendI18n {
  private translations: Map<string, Translations> = new Map()
  private currentLanguage = ref('en')
  private available = ref<string[]>(['en'])
  private version = ref(0)
  private languageGeneration = 0

  constructor() {
    this.translations.set('en', coreEnglish)
  }

  // Deep merge function for nested objects
  private deepMerge(target: any, source: any): any {
    const result = { ...target }
    for (const key in source) {
      if (['__proto__', 'prototype', 'constructor'].includes(key)) continue;
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = this.deepMerge(result[key] || {}, source[key])
      } else {
        result[key] = source[key]
      }
    }
    return result
  }

  async refreshLanguages() {
    this.available.value = await readAvailableLanguages()
    if (!this.available.value.includes(this.currentLanguage.value)) {
      await this.setLanguage('en', false)
    } else if (this.currentLanguage.value !== 'en') {
      await this.loadTranslations(this.currentLanguage.value)
    }
    this.version.value++
  }

  async loadTranslations(languageCode: string) {
    const content = languageCode === 'en' ? {} : await readFrontendTranslations(languageCode)
    this.translations.set(languageCode, this.deepMerge(coreEnglish, content))
    this.version.value++
  }

  // Add custom translations to a language (public method for components)
  addTranslations(languageCode: string, translations: Translations) {
    const currentTranslations = this.translations.get(languageCode) || {}
    const merged = this.deepMerge(currentTranslations, translations)
    this.translations.set(languageCode, merged)
    this.version.value++
  }

  async setLanguage(languageCode: string, persistPreference = true) {
    const generation = ++this.languageGeneration
    if (languageCode === this.currentLanguage.value && this.translations.has(languageCode)) return
    try {
      await this.loadTranslations(languageCode)
    } catch {
      languageCode = 'en'
    }
    if (generation !== this.languageGeneration) return
    this.currentLanguage.value = languageCode
    if (persistPreference) {
      localStorage.setItem('preferredLanguage', languageCode)
      try { await saveCurrentUserLanguage(languageCode) } catch { /* Local language remains usable. */ }
    }
    if (generation === this.languageGeneration) {
      window.dispatchEvent(new CustomEvent('language-changed', { detail: { language: languageCode } }))
    }
  }

  // Get current language
  getCurrentLanguage() {
    return this.currentLanguage.value
  }

  // Get version for reactivity
  getVersion() {
    return this.version.value
  }

  // Get available languages
  getAvailableLanguages() {
    return [...this.available.value]
  }

  // Translate a key
  t(key: string, defaultValue?: string, params?: Record<string, string>): string {
    const translations = this.translations.get(this.currentLanguage.value) || {}

    // Try nested access (both EN and BG use nested structure)
    let translation = this.getNestedValue(translations, key)

    if (!translation) {
      // Try English as fallback if current language is not English
      if (this.currentLanguage.value !== 'en') {
        const englishTranslations = this.translations.get('en') || {}
        translation = this.getNestedValue(englishTranslations, key)
      }

      if (!translation) {
        return defaultValue || key
      }
    }

    // Replace parameters
    if (params) {
      for (const [param, value] of Object.entries(params)) {
        translation = translation.replace(`{${param}}`, value)
      }
    }

    return translation
  }

  // Get nested value using dot notation
  private getNestedValue(obj: any, key: string): string | null {
    const keys = key.split('.')
    let current = obj

    for (const k of keys) {
      if (current && typeof current === 'object' && k in current) {
        current = current[k]
      } else {
        return null
      }
    }

    return typeof current === 'string' ? current : null
  }

  // Check if language is available
  isLanguageAvailable(languageCode: string): boolean {
    return this.available.value.includes(languageCode)
  }
}

// Create global instance
export const i18n = new FrontendI18n()

// Helper function for components
export const useI18n = () => {
  const currentLanguage = computed(() => i18n.getCurrentLanguage())
  const availableLanguages = computed(() => i18n.getAvailableLanguages())
  const version = computed(() => i18n.getVersion())

  const t = (key: string, defaultValue?: string, params?: Record<string, string>) => {
    const _ = currentLanguage.value
    const __ = version.value
    return i18n.t(key, defaultValue, params)
  }

  const setLanguage = (language: string) => i18n.setLanguage(language)
  const setPreviewLanguage = (language: string) => i18n.setLanguage(language, false)

  return {
    t,
    setLanguage,
    setPreviewLanguage,
    currentLanguage,
    availableLanguages
  }
}

// Initialize i18n
export const initializeI18n = async () => {
  try { await i18n.refreshLanguages() } catch { /* Core English remains usable offline. */ }
  const savedLanguage = localStorage.getItem('preferredLanguage')
  await i18n.setLanguage(savedLanguage && i18n.isLanguageAvailable(savedLanguage) ? savedLanguage : 'en')
}
