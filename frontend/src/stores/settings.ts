import { defineStore } from 'pinia'
import { ref, shallowRef, reactive, computed, watch, onScopeDispose } from 'vue'
import { useThemeStore } from '@/stores/theme'
import http from '@/utils/dynamic-http'
import { useI18n } from '@/utils/i18n'
import { readSettings, upsertSettings } from '@/utils/settings-api'
import { resolveHeaderSettings } from '@/utils/header-settings'
import { getToken } from '@/utils/auth'
import { BUILTIN_STYLES, resolveThemeStyle, readThemeProjection } from '@/utils/theme-extension'
import { adaptLegacyUi, builtinUiDesign, buttonHoverBackground, parseUiDesign, uiDesignVariables, type UiDesign } from '@/utils/ui-design'
import { parseInstalledTheme, loadThemeAssets, designLegacyStyle, type InstalledTheme, type LoadedThemeAssets } from '@/utils/theme-package-v2'
import { applyThemePreferences, parseThemePreferences, themePreferencesValid, themeCustomizationOptions, type ThemePreferences } from '@/utils/theme-customization'

export const useSettingsStore = defineStore('settings', () => {
  const themeStore = useThemeStore()
  const { currentLanguage } = useI18n()

  const loaded = ref(false)
  const activeTheme = shallowRef<InstalledTheme | null>(null)
  const appearanceUnavailable = ref(false)
  // The installed selection is never overwritten by a browser-only package preview.
  const packagePreview = shallowRef<{ theme: InstalledTheme | null; preferences: ThemePreferences | null; assets: LoadedThemeAssets | null } | null>(null)
  const isPackagePreview = computed(() => packagePreview.value !== null)
  const displayTheme = computed(() => packagePreview.value ? packagePreview.value.theme : activeTheme.value)
  const installedDesign = computed(() => displayTheme.value?.theme_extension_version === 2 ? displayTheme.value.design : null)
  const appearanceRecovery = ref(false)
  const themePreferences = shallowRef<ThemePreferences | null>(null)
  const themeAssets = shallowRef<LoadedThemeAssets | null>(null)
  const assetWarnings = computed(() => themeAssets.value?.warnings || [])
  const previewAssetWarnings = computed(() => packagePreview.value?.assets?.warnings || [])
  let previewController: AbortController | null = null
  let previewRequest = 0
  const clearPackagePreview = () => {
    ++previewRequest
    previewController?.abort()
    previewController = null
    packagePreview.value?.assets?.dispose()
    packagePreview.value = null
    updateCSSVariables()
  }
  const previewThemeAppearance = async (projection: unknown, baseUrl: string, signal: AbortSignal): Promise<boolean> => {
    clearPackagePreview()
    if (!projection || typeof projection !== 'object' || !('theme' in projection) || signal.aborted) return false
    const definition = parseInstalledTheme(projection)
    if (!definition && projection.theme !== null) return false
    const preferences = 'customization' in projection ? parseThemePreferences(projection.customization) : null
    const request = previewRequest
    const controller = new AbortController()
    previewController = controller
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    packagePreview.value = { theme: definition, preferences, assets: null }
    updateCSSVariables()
    try {
      if (definition?.theme_extension_version === 2) {
        const token = getToken()
        if (!token && definition.assets.length) throw new Error('Preview requires authentication')
        const assets = await loadThemeAssets(definition, baseUrl, controller.signal, token)
        if (request !== previewRequest || controller.signal.aborted) {
          assets.dispose()
          if (request === previewRequest) clearPackagePreview()
          return false
        }
        if (assets.font) document.fonts?.add(assets.font)
        packagePreview.value = { theme: definition, preferences, assets }
        updateCSSVariables()
      }
      return request === previewRequest && !controller.signal.aborted
    } catch {
      if (request === previewRequest) clearPackagePreview()
      return false
    } finally { signal.removeEventListener('abort', abort) }
  }
  let assetController: AbortController | null = null
  const clearAssets = () => {
    assetController?.abort()
    themeAssets.value?.dispose()
    themeAssets.value = null
  }
  onScopeDispose(clearAssets)
  onScopeDispose(clearPackagePreview)
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
    let preferences: ThemePreferences | null = null
    let baseUrl = ''
    try {
      try {
        baseUrl = await http.getCurrentBackendUrl()
        if (controller.signal.aborted) return
        const projection = await readThemeProjection(baseUrl, controller.signal)
        definition = parseInstalledTheme(projection)
        // A failed request is not an explicit built-in selection. Keep the last
        // verified theme, preferences and decoded resources across tab wake-up.
        if (!projection || typeof projection !== 'object' || !('theme' in projection) ||
            (!definition && projection.theme !== null)) {
          if (request === appearanceRequest && !controller.signal.aborted) appearanceUnavailable.value = true
          return
        }
        if (projection && typeof projection === 'object' && 'theme' in projection &&
          (definition || projection.theme === null) && 'customization' in projection) {
          preferences = parseThemePreferences(projection.customization)
        }
      } catch {
        if (request === appearanceRequest && !controller.signal.aborted) appearanceUnavailable.value = true
        return
      }
      if (request !== appearanceRequest || controller.signal.aborted) return
      appearanceUnavailable.value = false
      themePreferences.value = preferences
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

  // One built-in Design API palette. Retired light_*/dark_* settings are not
  // another default and are never imported into it or erased automatically.
  const baseUiDesign = computed(() => {
    if (!appearanceRecovery.value && installedDesign.value) return installedDesign.value
    const legacyTheme = displayTheme.value?.theme_extension_version === 1 && !appearanceRecovery.value ? displayTheme.value : null
    if (!legacyTheme) return builtinUiDesign()
    const design = adaptLegacyUi(resolveThemeStyle(legacyTheme, themeStore.theme, BUILTIN_STYLES[themeStore.theme]), themeStore.theme)
    for (const mode of ['light', 'dark'] as const) {
      design[mode] = adaptLegacyUi(resolveThemeStyle(legacyTheme, mode, BUILTIN_STYLES[mode]), mode)[mode]
    }
    return design
  })
  const baseStyleSettings = computed(() => designLegacyStyle(baseUiDesign.value, themeStore.theme))
  const effectivePreferences = computed(() => {
    const value = !appearanceRecovery.value ? (packagePreview.value ? packagePreview.value.preferences : themePreferences.value) : null
    return value && themePreferencesValid(baseUiDesign.value, value, displayTheme.value?.theme_extension_version ?? null, themeCustomizationOptions(displayTheme.value)) ? value : null
  })
  const customizedDesign = computed(() => !appearanceRecovery.value && effectivePreferences.value
    ? applyThemePreferences(baseUiDesign.value, effectivePreferences.value, displayTheme.value?.theme_extension_version === 1) : null)
  const menuLayout = computed(() => effectivePreferences.value?.menu_layout ?? null)
  const styleSettings = computed(() => customizedDesign.value && effectivePreferences.value?.colors
    ? designLegacyStyle(customizedDesign.value, themeStore.theme) : baseStyleSettings.value)
  const uiDesign = computed(() => previewDesign.value || customizedDesign.value || baseUiDesign.value)
  const appearanceHeader = computed(() => !previewDesign.value && effectivePreferences.value ? {
    ...headerSettings, backgroundColor: effectivePreferences.value.header_background_color,
    textColor: effectivePreferences.value.header_text_color,
  } : headerSettings)
  const brandingLogo = computed(() => headerSettings.logoUrl ||
    (!appearanceRecovery.value && !previewDesign.value ? (packagePreview.value ? packagePreview.value.assets : themeAssets.value)?.logos[themeStore.theme] || '' : ''))

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

    // Remaining Core consumers use the same readable button pairs as the SDK.
    const colors = uiDesign.value[themeStore.theme]
    for (const [name, background, foreground] of [
      ['primary', colors.accent, colors.accent_text],
      ['secondary', colors.secondary, colors.secondary_text],
      ['danger', colors.danger, colors.danger_text],
    ] as const) {
      const hover = buttonHoverBackground(background, foreground)
      root.style.setProperty(`--button-${name}-bg`, background)
      root.style.setProperty(`--button-${name}-text`, foreground)
      root.style.setProperty(`--button-${name}-hover`, hover)
      root.style.setProperty(`--button-${name}-border`, background)
      if (name !== 'danger') {
        root.style.setProperty(`--${name}-color`, background)
        root.style.setProperty(`--${name}-hover`, hover)
      }
    }

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
    for (const [key, value] of Object.entries(uiDesignVariables(uiDesign.value, themeStore.theme, appearanceHeader.value))) {
      root.style.setProperty(key, value)
    }
    if (installedDesign.value && !previewDesign.value && !appearanceRecovery.value) {
      root.style.setProperty('--input-focus-border', colors.focus)
      const assets = packagePreview.value ? packagePreview.value.assets : themeAssets.value
      if (assets?.font) root.style.setProperty('--ui-font', `"${assets.font.family}", ${root.style.getPropertyValue('--ui-font')}`)
    }

    // console.log('CSS variables updated')
  }

  watch(activeTheme, updateCSSVariables)
  watch(appearanceRecovery, updateCSSVariables)
  watch(themePreferences, updateCSSVariables)

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
  const saveHeaderSettings = async (includeColors = true) => {
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

      await upsertSettings(includeColors ? globalSettingsToSave : globalSettingsToSave.slice(0, 1))

      // Notify other components
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to save header settings:', err)
      throw err
    }
  }

  return {
    activeTheme,
    appearanceUnavailable,
    isPackagePreview,
    previewAssetWarnings,
    previewThemeAppearance,
    clearPackagePreview,
    installedDesign,
    baseUiDesign,
    customizedDesign,
    themePreferences,
    menuLayout,
    appearanceRecovery,
    brandingLogo,
    assetWarnings,
    previewDesign,
    uiDesign,
    setDesignPreview,
    loadThemeAppearance,
    headerSettings,
    styleSettings,
    loading,
    error,
    loaded,
    currentLanguageCode,
    languageSettings,
    loadSettings,
    updateCSSVariables,
    saveHeaderSettings,
    // New language-aware functions
    isLanguageSpecific,
    isGlobal,
    shouldSaveAsLanguageSpecific,
    saveSettingWithLanguage,
    syncSettingAcrossLanguages,
    getSettingVariations
  }
})
