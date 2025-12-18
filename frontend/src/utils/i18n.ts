/**
 * Clean, simple internationalization (i18n) utilities
 */

import { ref, computed } from 'vue'
import http from '@/utils/dynamic-http'

interface Translations {
  [key: string]: any
}

class FrontendI18n {
  private translations: Map<string, Translations> = new Map()
  private currentLanguage = ref('en')
  private version = ref(0)

  constructor() {
    // Initialize with empty English translations (will be populated by extensions)
    this.translations.set('en', {})
  }

  // Load translations from local extension files using dynamic scanning
  private async loadLocalTranslations(languageCode: string): Promise<Translations> {
    let allTranslations: Translations = {}

    try {
      // Use a comprehensive glob to capture all extension JSON files
      const allExtensionModules = import.meta.glob('../extensions/**/*.json', { eager: true }) as Record<string, any>

      // Find the language pack directory for this language code
      let languagePackBaseDir = ''

      for (const path in allExtensionModules) {
        if (path.includes('manifest.json')) {
          try {
            const manifest = allExtensionModules[path].default
            if (manifest.type === 'language' && manifest.language?.code === languageCode) {
              // Extract the base directory path (e.g., '../extensions/BulgarianLanguagePack_1.0.0')
              const pathParts = path.split('/')
              languagePackBaseDir = pathParts.slice(0, -1).join('/') // Remove manifest.json
              break
            }
          } catch (error) {
            // Continue
          }
        }
      }

      if (!languagePackBaseDir) {
        // No language pack found for this language, try loading from backend
        return await this.loadBackendTranslations(languageCode)
      }

      // Load all translation files from this language pack directory
      for (const path in allExtensionModules) {
        // Check if this file is in our language pack directory and not a manifest
        if (path.startsWith(languagePackBaseDir) && !path.includes('manifest.json')) {
          try {
            const translationData = allExtensionModules[path].default
            allTranslations = { ...allTranslations, ...translationData }
          } catch (error) {
            console.error(`Failed to load ${path}:`, error)
          }
        }
      }


      // If no translations loaded from local files, try backend
      if (Object.keys(allTranslations).length === 0) {
        allTranslations = await this.loadBackendTranslations(languageCode)
      }
    } catch (error) {
      console.error(`Failed to load local translations for ${languageCode}, trying backend:`, error)
      // Try loading from backend as fallback
      allTranslations = await this.loadBackendTranslations(languageCode)
    }

    return allTranslations
  }


  // Load translations from backend API
  private async loadBackendTranslations(languageCode: string): Promise<Translations> {
    try {
      // Import http dynamically to avoid circular dependency
      const { default: http } = await import('@/utils/dynamic-http')
      const response = await http.get(`/api/translations/${languageCode}`)
      const data = response.data
      return data.frontend || {}
    } catch (error) {
      console.error(`Failed to load backend translations for ${languageCode}:`, error)
      return {}
    }
  }

  // Deep merge function for nested objects
  private deepMerge(target: any, source: any): any {
    const result = { ...target }
    for (const key in source) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = this.deepMerge(result[key] || {}, source[key])
      } else {
        result[key] = source[key]
      }
    }
    return result
  }

  // Load translations for a language
  async loadTranslations(languageCode: string) {
    try {
      const localTranslations = await this.loadLocalTranslations(languageCode)
      const extensionTranslations = await this.loadExtensionTranslationsForLanguage(languageCode)
      const allTranslations = this.deepMerge(localTranslations, extensionTranslations)
      this.translations.set(languageCode, allTranslations)
      this.version.value++
    } catch (error) {
      console.error(`Failed to load translations for ${languageCode}:`, error)
    }
  }

  // Load extension translations for a specific language
  private async loadExtensionTranslationsForLanguage(languageCode: string): Promise<Translations> {
    let extensionTranslations: Translations = {}

    try {
      // Use glob to find all extension modules
      const allExtensionModules = import.meta.glob('../extensions/**/*.json', { eager: true }) as Record<string, any>

      // Find all extension directories that have locales
      const extensionDirs = new Set<string>()

      for (const path in allExtensionModules) {
        if (path.includes('manifest.json')) {
          try {
            const manifest = allExtensionModules[path].default
            if (manifest.locales && manifest.locales.supported?.includes(languageCode)) {
              // Extract the base directory path
              const pathParts = path.split('/')
              const baseDir = pathParts.slice(0, -1).join('/') // Remove manifest.json
              extensionDirs.add(baseDir)
            }
          } catch (error) {
            // Continue
          }
        }
      }

      // Load translations from each extension's locales directory
      for (const baseDir of extensionDirs) {
        const localesPath = `${baseDir}/locales/${languageCode}.json`
        if (localesPath in allExtensionModules) {
          try {
            const translationData = allExtensionModules[localesPath].default
            // Merge extension translations directly into root namespace for easier access
            extensionTranslations = this.deepMerge(extensionTranslations, translationData)
          } catch (error) {
            console.error(`Failed to load extension translations from ${localesPath}:`, error)
          }
        }
      }
    } catch (error) {
      console.error(`Failed to load extension translations for ${languageCode}:`, error)
    }

    return extensionTranslations
  }

  // Load extension translations for a specific extension (called when extension is loaded)
  async loadExtensionTranslationsForExtension(extensionName: string, languageCode: string) {
    try {
      // Use glob to find the extension's locale file
      const extensionGlob = import.meta.glob('../extensions/**/*.json', { eager: true }) as Record<string, any>

      // Find the correct locale file for this extension and language
      let localeFile = null
      for (const path in extensionGlob) {
        if (path.includes(`/${extensionName}_`) &&
            path.includes(`/locales/${languageCode}.json`)) {
          localeFile = path
          break
        }
      }

      if (localeFile && localeFile in extensionGlob) {
        const translationData = extensionGlob[localeFile].default

        // Merge extension translations directly into the root namespace
        const currentTranslations = this.translations.get(languageCode) || {}
        const merged = this.deepMerge(currentTranslations, translationData)
        this.translations.set(languageCode, merged)
        this.version.value++
      }
    } catch (error) {
      console.warn(`Failed to load translations for extension ${extensionName} in ${languageCode}:`, error)
    }
  }

  // Add custom translations to a language (public method for components)
  addTranslations(languageCode: string, translations: Translations) {
    const currentTranslations = this.translations.get(languageCode) || {}
    const merged = this.deepMerge(currentTranslations, translations)
    this.translations.set(languageCode, merged)
    this.version.value++
  }

  // Load extension translations for all enabled extensions
  async loadExtensionTranslationsForEnabledExtensions() {
    try {
      // Get enabled extensions from API
      const { default: http } = await import('@/utils/dynamic-http')
      const response = await http.get('/api/extensions/public')
      const extensions = response.data?.items || []

      const currentLanguage = this.getCurrentLanguage()

      // Load translations for each enabled extension
      for (const ext of extensions) {
        if (ext.name) {
          await this.loadExtensionTranslationsForExtension(ext.name, currentLanguage)
        }
      }
    } catch (error) {
      console.warn('Failed to load extension translations for enabled extensions:', error)
    }
  }


  // Set current language
  async setLanguage(languageCode: string) {
    if (languageCode === this.currentLanguage.value) return

    localStorage.setItem('preferredLanguage', languageCode)
    this.currentLanguage.value = languageCode

    await this.loadTranslations(languageCode)

    // Load extension translations for enabled extensions in the new language
    await this.loadExtensionTranslationsForEnabledExtensions()

    // Save to backend (async)
    try {
      await http.post('/api/user/language', { language: languageCode })
    } catch (error) {
      // Ignore backend errors
    }

    window.dispatchEvent(new CustomEvent('language-changed', { detail: { language: languageCode } }))
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
    const available = Array.from(this.translations.keys())
    // Always include English
    if (!available.includes('en')) available.push('en')
    return available
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
    return this.translations.has(languageCode)
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

  return {
    t,
    setLanguage,
    currentLanguage,
    availableLanguages
  }
}

// Initialize i18n
export const initializeI18n = async () => {
  const savedLanguage = localStorage.getItem('preferredLanguage')

  if (savedLanguage && i18n.isLanguageAvailable(savedLanguage)) {
    await i18n.setLanguage(savedLanguage)
  } else {
    // For new users, don't set localStorage yet, let loadDefaults set the default
    await i18n.setLanguage('en')
  }

  // Load extension translations for enabled extensions
  await i18n.loadExtensionTranslationsForEnabledExtensions()
}