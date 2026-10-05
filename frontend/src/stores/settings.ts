import { defineStore } from 'pinia'
import { ref, shallowRef, reactive, computed, watch, onScopeDispose } from 'vue'
import { useThemeStore } from '@/stores/theme'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { readSettings, upsertSettings } from '@/utils/settings-api'
import { resolveHeaderSettings } from '@/utils/header-settings'
import { BUILTIN_STYLES, buttonTextColor, resolveThemeStyle } from '@/utils/theme-extension'
import { adaptLegacyUi, parseUiDesign, uiDesignVariables, type UiDesign } from '@/utils/ui-design'
import { readInstalledTheme, loadThemeAssets, designLegacyStyle, type InstalledTheme, type LoadedThemeAssets } from '@/utils/theme-package-v2'

export const useSettingsStore = defineStore('settings', () => {
  const themeStore = useThemeStore()
  const { currentLanguage } = useI18n()

  const loaded = ref(false)
  const activeTheme = shallowRef<InstalledTheme | null>(null)
  const installedDesign = computed(() => activeTheme.value?.theme_extension_version === 2 ? activeTheme.value.design : null)
  const appearanceRecovery = ref(false)
  const themeAssets = shallowRef<LoadedThemeAssets | null>(null)
  const assetWarnings = computed(() => themeAssets.value?.warnings || [])
  let assetController: AbortController | null = null
  const clearAssets = () => {
    assetController?.abort()
    themeAssets.value?.dispose()
    themeAssets.value = null
  }
  onScopeDispose(clearAssets)
  // Browser-only preview, cleared on route exit; never persisted or sent to an API.
  const previewDesign = shallowRef<UiDesign | null>(null)
  const setDesignPreview = (value: unknown): boolean => {
    const design = value === null ? null : parseUiDesign(value)
    if (value !== null && !design) return false
    previewDesign.value = design
    updateCSSVariables()
    return true
  }
  let appearanceRequest = 0
  const loadThemeAppearance = async (signal?: AbortSignal) => {
    const request = ++appearanceRequest
    assetController?.abort()
    const controller = new AbortController()
    assetController = controller
    const abort = () => controller.abort()
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) abort()
    let definition: InstalledTheme | null = null
    let baseUrl = ''
    try {
      try {
        baseUrl = await http.getCurrentBackendUrl()
        if (controller.signal.aborted) return
        definition = await readInstalledTheme(baseUrl, controller.signal)
      } catch { /* Backend discovery failure also uses the built-in settings. */ }
      if (request !== appearanceRequest || controller.signal.aborted) return
      if (definition?.theme_extension_version === 2 && activeTheme.value?.theme_extension_version === 2 &&
        definition.package_sha256 === activeTheme.value.package_sha256 && themeAssets.value && !themeAssets.value.warnings.length) {
        activeTheme.value = definition
        updateCSSVariables()
        return // Already verified immutable resources; avoid font/logo churn on tab focus.
      }
      themeAssets.value?.dispose()
      themeAssets.value = null
      activeTheme.value = definition
      updateCSSVariables()
      if (definition?.theme_extension_version === 2) {
        const assets = await loadThemeAssets(definition, baseUrl, controller.signal)
        if (request !== appearanceRequest || controller.signal.aborted) { assets.dispose(); return }
        if (assets.font) document.fonts?.add(assets.font)
        themeAssets.value = assets
        updateCSSVariables()
      }
    } finally { signal?.removeEventListener('abort', abort) }
  }
  const currentLanguageCode = ref('en') // Default to English

  // Track language-specific settings
  const languageSettings = reactive(new Map<string, any[]>())
  
  // Settings that should be language-specific (text-based)
  const languageSpecificKeys = [
    'site_name',
    'header_message',
    'page_title_',
    'widget_title_'
  ]
  
  // Settings that should remain global (visual/technical)
  const globalKeys = [
    'logo_url', 'header_bg_color', 'header_text_color',
    'light_body_bg', 'light_content_bg', 'light_button_primary_bg',
    'light_button_secondary_bg', 'light_button_danger_bg', 'light_card_bg',
    'light_card_border', 'light_panel_bg', 'light_text_primary',
    'light_text_secondary', 'light_text_muted', 'light_border_radius_sm',
    'light_border_radius_md', 'light_border_radius_lg', 'dark_body_bg',
    'dark_content_bg', 'dark_button_primary_bg', 'dark_button_secondary_bg',
    'dark_button_danger_bg', 'dark_card_bg', 'dark_card_border', 'dark_panel_bg',
    'dark_text_primary', 'dark_text_secondary', 'dark_text_muted', 'dark_border_radius_sm',
    'dark_border_radius_md', 'dark_border_radius_lg'
  ]

  // Header settings
  const headerSettings = reactive({
    siteName: 'Mega Monitor',
    headerMessage: 'Welcome to Mega Monitor',
    logoUrl: '',
    backgroundColor: '#4CAF50',
    textColor: '#ffffff'
  })

  // Style settings for light theme
  const lightStyleSettings = reactive({ ...BUILTIN_STYLES.light })

  // Style settings for dark theme
  const darkStyleSettings = reactive({ ...BUILTIN_STYLES.dark })

  // Computed property to get current theme settings
  const styleSettings = computed(() => {
    if (installedDesign.value && !appearanceRecovery.value) return designLegacyStyle(installedDesign.value, themeStore.theme)
    const legacyTheme = activeTheme.value?.theme_extension_version === 1 && !appearanceRecovery.value ? activeTheme.value : null
    return resolveThemeStyle(legacyTheme, themeStore.theme,
      themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings)
  })
  const uiDesign = computed(() => previewDesign.value || (!appearanceRecovery.value && installedDesign.value) || adaptLegacyUi(styleSettings.value, themeStore.theme))
  const brandingLogo = computed(() => headerSettings.logoUrl ||
    (!appearanceRecovery.value && !previewDesign.value ? themeAssets.value?.logos[themeStore.theme] || '' : ''))

  const loading = ref(false)
  const error = ref('')

  // Load settings from backend
  const loadSettings = async (signal?: AbortSignal) => {
    try {
      loading.value = true
      const languageCode = currentLanguage.value || 'en'
      currentLanguageCode.value = languageCode
      
      // Load language-specific settings
      const [items, allItems] = await Promise.all([
        readSettings(languageCode, signal),
        readSettings(undefined, signal)
      ])
      if (signal?.aborted) return
      
      // Cache language-specific settings
      languageSettings.set(languageCode, items)

      // Load header settings
      const resolvedHeader = resolveHeaderSettings(items, allItems, languageCode)
      Object.assign(headerSettings, resolvedHeader)

      loaded.value = true

      // Load style settings for both themes
      // Light theme settings
      const lightButtonPrimaryBg = items.find((s: any) => s.key === 'light_button_primary_bg')
      const lightButtonSecondaryBg = items.find((s: any) => s.key === 'light_button_secondary_bg')
      const lightButtonDangerBg = items.find((s: any) => s.key === 'light_button_danger_bg')
      const lightCardBg = items.find((s: any) => s.key === 'light_card_bg')
      const lightCardBorder = items.find((s: any) => s.key === 'light_card_border')
      const lightPanelBg = items.find((s: any) => s.key === 'light_panel_bg')
      const lightBodyBg = items.find((s: any) => s.key === 'light_body_bg')
      const lightContentBg = items.find((s: any) => s.key === 'light_content_bg')
      const lightTextPrimary = items.find((s: any) => s.key === 'light_text_primary')
      const lightTextSecondary = items.find((s: any) => s.key === 'light_text_secondary')
      const lightTextMuted = items.find((s: any) => s.key === 'light_text_muted')
      const lightBorderRadiusSm = items.find((s: any) => s.key === 'light_border_radius_sm')
      const lightBorderRadiusMd = items.find((s: any) => s.key === 'light_border_radius_md')
      const lightBorderRadiusLg = items.find((s: any) => s.key === 'light_border_radius_lg')

      // Dark theme settings
      const darkButtonPrimaryBg = items.find((s: any) => s.key === 'dark_button_primary_bg')
      const darkButtonSecondaryBg = items.find((s: any) => s.key === 'dark_button_secondary_bg')
      const darkButtonDangerBg = items.find((s: any) => s.key === 'dark_button_danger_bg')
      const darkCardBg = items.find((s: any) => s.key === 'dark_card_bg')
      const darkCardBorder = items.find((s: any) => s.key === 'dark_card_border')
      const darkPanelBg = items.find((s: any) => s.key === 'dark_panel_bg')
      const darkBodyBg = items.find((s: any) => s.key === 'dark_body_bg')
      const darkContentBg = items.find((s: any) => s.key === 'dark_content_bg')
      const darkTextPrimary = items.find((s: any) => s.key === 'dark_text_primary')
      const darkTextSecondary = items.find((s: any) => s.key === 'dark_text_secondary')
      const darkTextMuted = items.find((s: any) => s.key === 'dark_text_muted')
      const darkBorderRadiusSm = items.find((s: any) => s.key === 'dark_border_radius_sm')
      const darkBorderRadiusMd = items.find((s: any) => s.key === 'dark_border_radius_md')
      const darkBorderRadiusLg = items.find((s: any) => s.key === 'dark_border_radius_lg')

      // Load light theme settings
      // console.log('Loading light theme settings from backend')
      lightStyleSettings.buttonPrimaryBg = lightButtonPrimaryBg?.value || '#007bff'
      lightStyleSettings.buttonSecondaryBg = lightButtonSecondaryBg?.value || '#6c757d'
      lightStyleSettings.buttonDangerBg = lightButtonDangerBg?.value || '#dc3545'
      lightStyleSettings.cardBg = lightCardBg?.value || '#ffffff'
      lightStyleSettings.cardBorder = lightCardBorder?.value || '#e3e3e3'
      lightStyleSettings.panelBg = lightPanelBg?.value || '#ffffff'
      lightStyleSettings.bodyBg = lightBodyBg?.value || '#ffffff'
      lightStyleSettings.contentBg = lightContentBg?.value || '#ffffff'
      lightStyleSettings.textPrimary = lightTextPrimary?.value || '#222222'
      lightStyleSettings.textSecondary = lightTextSecondary?.value || '#666666'
      lightStyleSettings.textMuted = lightTextMuted?.value || '#999999'
      lightStyleSettings.borderRadiusSm = Math.min(parseInt(lightBorderRadiusSm?.value ?? '') || 4, 20)
      lightStyleSettings.borderRadiusMd = Math.min(parseInt(lightBorderRadiusMd?.value ?? '') || 8, 30)
      lightStyleSettings.borderRadiusLg = Math.min(parseInt(lightBorderRadiusLg?.value ?? '') || 12, 50)
      // console.log('Light theme settings loaded:', lightStyleSettings)

      // Load dark theme settings
      // console.log('Loading dark theme settings from backend')
      darkStyleSettings.buttonPrimaryBg = darkButtonPrimaryBg?.value || '#3b82f6'
      darkStyleSettings.buttonSecondaryBg = darkButtonSecondaryBg?.value || '#6b7280'
      darkStyleSettings.buttonDangerBg = darkButtonDangerBg?.value || '#ef4444'
      darkStyleSettings.cardBg = darkCardBg?.value || '#374151'
      darkStyleSettings.cardBorder = darkCardBorder?.value || '#4b5563'
      darkStyleSettings.panelBg = darkPanelBg?.value || '#374151'
      darkStyleSettings.bodyBg = darkBodyBg?.value || '#1f2937'
      darkStyleSettings.contentBg = darkContentBg?.value || '#1f2937'
      darkStyleSettings.textPrimary = darkTextPrimary?.value || '#e5e7eb'
      darkStyleSettings.textSecondary = darkTextSecondary?.value || '#9ca3af'
      darkStyleSettings.textMuted = darkTextMuted?.value || '#6b7280'
      darkStyleSettings.borderRadiusSm = Math.min(parseInt(darkBorderRadiusSm?.value ?? '') || 4, 20)
      darkStyleSettings.borderRadiusMd = Math.min(parseInt(darkBorderRadiusMd?.value ?? '') || 8, 30)
      darkStyleSettings.borderRadiusLg = Math.min(parseInt(darkBorderRadiusLg?.value ?? '') || 12, 50)
      // console.log('Dark theme settings loaded:', darkStyleSettings)

      // Apply CSS variables immediately after loading
      updateCSSVariables()
      // console.log('Initial CSS variables applied on mount')
    } catch (err) {
      if (signal?.aborted) return
      console.error('Failed to load settings:', err)
      error.value = 'Failed to load settings'
    } finally {
      loading.value = false
    }
  }

  // Update CSS variables
  const updateCSSVariables = () => {
    const root = document.documentElement
    const currentSettings = styleSettings.value

    // console.log('Updating CSS variables for theme:', themeStore.theme, 'with settings:', currentSettings)

    // Force immediate update by clearing and re-setting
    const allVars = [
      '--body-bg', '--content-bg', '--button-primary-bg', '--button-secondary-bg', '--button-danger-bg',
      '--card-bg', '--card-border', '--panel-bg', '--text-primary', '--text-secondary', '--text-muted',
      '--border-radius-sm', '--border-radius-md', '--border-radius-lg',
      '--color-background', '--color-text', '--color-card-bg', '--color-border', '--color-input-bg',
      '--color-input-border', '--color-background-soft', '--button-primary-text', '--button-primary-hover',
      '--button-primary-border', '--button-secondary-text', '--button-secondary-hover', '--button-secondary-border',
      '--button-danger-text', '--button-danger-hover', '--button-danger-border', '--input-bg', '--input-border',
      '--input-focus-border', '--input-placeholder', '--modal-bg', '--modal-border', '--table-bg', '--table-border',
      '--table-header-bg', '--table-hover-bg', '--nav-bg', '--nav-border', '--nav-link-color',
      '--nav-link-hover-color', '--nav-link-active-color', '--card-shadow', '--card-hover-shadow'
    ]

    // Clear all variables first to force re-application
    allVars.forEach(varName => root.style.removeProperty(varName))

    // Set all CSS variables for current theme settings
    root.style.setProperty('--body-bg', currentSettings.bodyBg)
    root.style.setProperty('--content-bg', currentSettings.contentBg)
    root.style.setProperty('--button-primary-bg', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--button-secondary-bg', currentSettings.buttonSecondaryBg)
    root.style.setProperty('--button-danger-bg', currentSettings.buttonDangerBg)
    root.style.setProperty('--card-bg', currentSettings.cardBg)
    root.style.setProperty('--card-border', currentSettings.cardBorder)
    root.style.setProperty('--panel-bg', currentSettings.panelBg)
    root.style.setProperty('--text-primary', currentSettings.textPrimary)
    root.style.setProperty('--text-secondary', currentSettings.textSecondary)
    root.style.setProperty('--text-muted', currentSettings.textMuted)
    root.style.setProperty('--border-radius-sm', currentSettings.borderRadiusSm + 'px')
    root.style.setProperty('--border-radius-md', currentSettings.borderRadiusMd + 'px')
    root.style.setProperty('--border-radius-lg', currentSettings.borderRadiusLg + 'px')

    // Main theme colors
    root.style.setProperty('--color-background', currentSettings.bodyBg)
    root.style.setProperty('--color-text', currentSettings.textPrimary)
    root.style.setProperty('--color-card-bg', currentSettings.cardBg)
    root.style.setProperty('--color-border', currentSettings.cardBorder)
    root.style.setProperty('--color-input-bg', currentSettings.cardBg)
    root.style.setProperty('--color-input-border', currentSettings.cardBorder)
    root.style.setProperty('--color-background-soft', currentSettings.panelBg)
    root.style.setProperty('--surface-1', currentSettings.cardBg)
    root.style.setProperty('--surface-2', currentSettings.panelBg)
    root.style.setProperty('--surface-3', currentSettings.contentBg)
    root.style.setProperty('--surface-border', currentSettings.cardBorder)
    root.style.setProperty('--surface-hover', themeStore.theme === 'dark' ? '#263449' : '#f1f5f9')
    root.style.setProperty('--primary-color', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--secondary-color', currentSettings.buttonSecondaryBg)

    // Button colors
    root.style.setProperty('--button-primary-text', activeTheme.value ? buttonTextColor(currentSettings.buttonPrimaryBg) : '#ffffff')
    root.style.setProperty('--button-primary-hover', adjustColor(currentSettings.buttonPrimaryBg, -20))
    root.style.setProperty('--primary-hover', adjustColor(currentSettings.buttonPrimaryBg, -20))
    root.style.setProperty('--button-primary-border', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--button-secondary-text', activeTheme.value ? buttonTextColor(currentSettings.buttonSecondaryBg) : '#ffffff')
    root.style.setProperty('--button-secondary-hover', adjustColor(currentSettings.buttonSecondaryBg, -20))
    root.style.setProperty('--secondary-hover', adjustColor(currentSettings.buttonSecondaryBg, -20))
    root.style.setProperty('--button-secondary-border', currentSettings.buttonSecondaryBg)
    root.style.setProperty('--button-danger-text', activeTheme.value ? buttonTextColor(currentSettings.buttonDangerBg) : '#ffffff')
    root.style.setProperty('--button-danger-hover', adjustColor(currentSettings.buttonDangerBg, -20))
    root.style.setProperty('--button-danger-border', currentSettings.buttonDangerBg)

    // Input colors
    root.style.setProperty('--input-bg', currentSettings.cardBg)
    root.style.setProperty('--input-border', currentSettings.cardBorder)
    root.style.setProperty('--input-focus-border', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--input-placeholder', currentSettings.textMuted)

    // Modal colors
    root.style.setProperty('--modal-bg', currentSettings.cardBg)
    root.style.setProperty('--modal-border', currentSettings.cardBorder)

    // Table colors
    root.style.setProperty('--table-bg', currentSettings.cardBg)
    root.style.setProperty('--table-border', currentSettings.cardBorder)
    root.style.setProperty('--table-header-bg', currentSettings.panelBg)
    root.style.setProperty('--table-hover-bg', currentSettings.panelBg)

    // Navigation colors
    root.style.setProperty('--nav-bg', currentSettings.cardBg)
    root.style.setProperty('--nav-border', currentSettings.cardBorder)
    root.style.setProperty('--nav-link-color', currentSettings.textSecondary)
    root.style.setProperty('--nav-link-hover-color', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--nav-link-active-color', currentSettings.buttonPrimaryBg)

    // Card shadows
    root.style.setProperty('--card-shadow', themeStore.theme === 'dark' ? 'rgba(0, 0, 0, 0.3)' : 'rgba(0, 0, 0, 0.1)')
    root.style.setProperty('--card-hover-shadow', themeStore.theme === 'dark' ? 'rgba(0, 0, 0, 0.4)' : 'rgba(0, 0, 0, 0.15)')

    // Closed namespaced projection. Every owned variable is overwritten on mode,
    // preview and header changes; it cannot retain values from a previous theme.
    for (const [key, value] of Object.entries(uiDesignVariables(uiDesign.value, themeStore.theme, headerSettings))) {
      root.style.setProperty(key, value)
    }
    if (installedDesign.value && !previewDesign.value && !appearanceRecovery.value) {
      const colors = installedDesign.value[themeStore.theme]
      root.style.setProperty('--button-primary-text', colors.accent_text)
      root.style.setProperty('--button-secondary-text', colors.secondary_text)
      root.style.setProperty('--button-danger-text', colors.danger_text)
      if (themeAssets.value?.font) root.style.setProperty('--ui-font', `"${themeAssets.value.font.family}", ${root.style.getPropertyValue('--ui-font')}`)
    }

    // console.log('CSS variables updated')
  }

  watch(activeTheme, updateCSSVariables)
  watch(appearanceRecovery, updateCSSVariables)

  // Helper function to adjust color brightness
  const adjustColor = (color: string, amount: number): string => {
    // Simple color adjustment - darken by reducing RGB values
    const hex = color.replace('#', '')
    const r = Math.max(0, parseInt(hex.substr(0, 2), 16) + amount)
    const g = Math.max(0, parseInt(hex.substr(2, 2), 16) + amount)
    const b = Math.max(0, parseInt(hex.substr(4, 2), 16) + amount)
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
  }

  // Language-aware helper functions
  const isLanguageSpecific = (key: string): boolean => {
    return languageSpecificKeys.some(prefix => key.startsWith(prefix))
  }

  const isGlobal = (key: string): boolean => {
    return globalKeys.includes(key)
  }

  const shouldSaveAsLanguageSpecific = (key: string): boolean => {
    // Text-based settings should be language-specific
    return isLanguageSpecific(key)
  }

  // Language-aware save method
  const saveSettingWithLanguage = async (key: string, value: string, description?: string) => {
    const languageCode = currentLanguageCode.value
    const saveAsLanguageSpecific = shouldSaveAsLanguageSpecific(key)
    
    const settingData = {
      key,
      value,
      description: description || `${key} setting`,
      language_code: saveAsLanguageSpecific ? languageCode : null
    }

    await upsertSettings([settingData])

    // Update cache
    const currentItems = languageSettings.get(languageCode) || []
    const updatedItems = currentItems.filter(item =>
      item.key !== key ||
      (item.language_code ?? null) !== (settingData.language_code ?? null)
    )
    updatedItems.push(settingData)
    languageSettings.set(languageCode, updatedItems)
  }

  // Sync setting across multiple languages
  const syncSettingAcrossLanguages = async (key: string, values: Record<string, string>, description?: string) => {
    try {
      await http.post('/settings/sync', {
        key,
        values,
        description: description || `${key} setting`
      })
      
      // Refresh settings for all affected languages
      for (const langCode of Object.keys(values)) {
        languageSettings.delete(langCode) // Clear cache
      }
      
      // Reload current language settings
      await loadSettings()
      
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to sync setting across languages:', err)
      throw err
    }
  }

  // Get setting variations across languages
  const getSettingVariations = async (key: string) => {
    try {
      const response = await http.get(`/settings/keys/${key}`)
      return response.data.variations || {}
    } catch (err) {
      console.error('Failed to get setting variations:', err)
      return {}
    }
  }

  // Header visuals are shared across languages; only header text is localized.
  const saveHeaderSettings = async () => {
    try {
      const globalSettingsToSave = [
        {
          key: 'logo_url',
          value: headerSettings.logoUrl,
          description: 'Logo URL or base64 data',
          language_code: null
        },
        {
          key: 'header_bg_color',
          value: headerSettings.backgroundColor,
          description: 'Shared header background color',
          language_code: null
        },
        {
          key: 'header_text_color',
          value: headerSettings.textColor,
          description: 'Shared header text color',
          language_code: null
        }
      ]

      await upsertSettings(globalSettingsToSave)

      // Notify other components
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to save header settings:', err)
      throw err
    }
  }

  // Save light style settings
  const saveLightStyleSettings = async () => {
    try {
      const styleSettingsToSave = [
        { key: 'light_body_bg', value: lightStyleSettings.bodyBg, description: 'Light theme body background color' },
        { key: 'light_content_bg', value: lightStyleSettings.contentBg, description: 'Light theme content background color' },
        { key: 'light_button_primary_bg', value: lightStyleSettings.buttonPrimaryBg, description: 'Light theme primary button background color' },
        { key: 'light_button_secondary_bg', value: lightStyleSettings.buttonSecondaryBg, description: 'Light theme secondary button background color' },
        { key: 'light_button_danger_bg', value: lightStyleSettings.buttonDangerBg, description: 'Light theme danger button background color' },
        { key: 'light_card_bg', value: lightStyleSettings.cardBg, description: 'Light theme card background color' },
        { key: 'light_card_border', value: lightStyleSettings.cardBorder, description: 'Light theme card border color' },
        { key: 'light_panel_bg', value: lightStyleSettings.panelBg, description: 'Light theme panel background color' },
        { key: 'light_text_primary', value: lightStyleSettings.textPrimary, description: 'Light theme primary text color' },
        { key: 'light_text_secondary', value: lightStyleSettings.textSecondary, description: 'Light theme secondary text color' },
        { key: 'light_text_muted', value: lightStyleSettings.textMuted, description: 'Light theme muted text color' },
        { key: 'light_border_radius_sm', value: lightStyleSettings.borderRadiusSm.toString(), description: 'Light theme small border radius' },
        { key: 'light_border_radius_md', value: lightStyleSettings.borderRadiusMd.toString(), description: 'Light theme medium border radius' },
        { key: 'light_border_radius_lg', value: lightStyleSettings.borderRadiusLg.toString(), description: 'Light theme large border radius' }
      ]

      await upsertSettings(styleSettingsToSave)

      // Only update CSS variables if light theme is active
      if (themeStore.theme === 'light') {
        updateCSSVariables()
      }
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to save light style settings:', err)
      throw err
    }
  }

  // Save dark style settings
  const saveDarkStyleSettings = async () => {
    try {
      const styleSettingsToSave = [
        { key: 'dark_body_bg', value: darkStyleSettings.bodyBg, description: 'Dark theme body background color' },
        { key: 'dark_content_bg', value: darkStyleSettings.contentBg, description: 'Dark theme content background color' },
        { key: 'dark_button_primary_bg', value: darkStyleSettings.buttonPrimaryBg, description: 'Dark theme primary button background color' },
        { key: 'dark_button_secondary_bg', value: darkStyleSettings.buttonSecondaryBg, description: 'Dark theme secondary button background color' },
        { key: 'dark_button_danger_bg', value: darkStyleSettings.buttonDangerBg, description: 'Dark theme danger button background color' },
        { key: 'dark_card_bg', value: darkStyleSettings.cardBg, description: 'Dark theme card background color' },
        { key: 'dark_card_border', value: darkStyleSettings.cardBorder, description: 'Dark theme card border color' },
        { key: 'dark_panel_bg', value: darkStyleSettings.panelBg, description: 'Dark theme panel background color' },
        { key: 'dark_text_primary', value: darkStyleSettings.textPrimary, description: 'Dark theme primary text color' },
        { key: 'dark_text_secondary', value: darkStyleSettings.textSecondary, description: 'Dark theme secondary text color' },
        { key: 'dark_text_muted', value: darkStyleSettings.textMuted, description: 'Dark theme muted text color' },
        { key: 'dark_border_radius_sm', value: darkStyleSettings.borderRadiusSm.toString(), description: 'Dark theme small border radius' },
        { key: 'dark_border_radius_md', value: darkStyleSettings.borderRadiusMd.toString(), description: 'Dark theme medium border radius' },
        { key: 'dark_border_radius_lg', value: darkStyleSettings.borderRadiusLg.toString(), description: 'Dark theme large border radius' }
      ]

      await upsertSettings(styleSettingsToSave)

      // Only update CSS variables if dark theme is active
      if (themeStore.theme === 'dark') {
        updateCSSVariables()
      }
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to save dark style settings:', err)
      throw err
    }
  }

  return {
    activeTheme,
    installedDesign,
    appearanceRecovery,
    brandingLogo,
    assetWarnings,
    previewDesign,
    uiDesign,
    setDesignPreview,
    loadThemeAppearance,
    headerSettings,
    styleSettings,
    lightStyleSettings,
    darkStyleSettings,
    loading,
    error,
    loaded,
    currentLanguageCode,
    languageSettings,
    loadSettings,
    updateCSSVariables,
    saveHeaderSettings,
    saveLightStyleSettings,
    saveDarkStyleSettings,
    // New language-aware functions
    isLanguageSpecific,
    isGlobal,
    shouldSaveAsLanguageSpecific,
    saveSettingWithLanguage,
    syncSettingAcrossLanguages,
    getSettingVariations
  }
})
