import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import http from '@/utils/http'

export const useSettingsStore = defineStore('settings', () => {
  const themeStore = useThemeStore()

  const loaded = ref(false)

  // Header settings
  const headerSettings = reactive({
    siteName: 'Mega Monitor',
    headerMessage: 'Welcome to Mega Monitor',
    logoUrl: '',
    backgroundColor: '#4CAF50',
    textColor: '#ffffff'
  })

  // Style settings for light theme
  const lightStyleSettings = reactive({
    bodyBg: '#ffffff',
    contentBg: '#ffffff',
    buttonPrimaryBg: '#007bff',
    buttonSecondaryBg: '#6c757d',
    buttonDangerBg: '#dc3545',
    cardBg: '#ffffff',
    cardBorder: '#e3e3e3',
    panelBg: '#ffffff',
    textPrimary: '#222222',
    textSecondary: '#666666',
    textMuted: '#999999',
    borderRadiusSm: 4,
    borderRadiusMd: 8,
    borderRadiusLg: 12
  })

  // Style settings for dark theme
  const darkStyleSettings = reactive({
    bodyBg: '#1f2937',
    contentBg: '#1f2937',
    buttonPrimaryBg: '#3b82f6',
    buttonSecondaryBg: '#6b7280',
    buttonDangerBg: '#ef4444',
    cardBg: '#374151',
    cardBorder: '#4b5563',
    panelBg: '#374151',
    textPrimary: '#e5e7eb',
    textSecondary: '#9ca3af',
    textMuted: '#6b7280',
    borderRadiusSm: 4,
    borderRadiusMd: 8,
    borderRadiusLg: 12
  })

  // Computed property to get current theme settings
  const styleSettings = computed(() => {
    if (!loaded.value) {
      // Return default settings if not loaded yet
      return themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings
    }
    return themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings
  })

  const loading = ref(false)
  const error = ref('')

  // Load settings from backend
  const loadSettings = async () => {
    try {
      loading.value = true
      const response = await http.get('/settings/read')
      const items = response.data.items || []

      // Load header settings
      const siteName = items.find((s: any) => s.key === 'site_name')
      const headerMessage = items.find((s: any) => s.key === 'header_message')
      const logoUrl = items.find((s: any) => s.key === 'logo_url')
      const bgColor = items.find((s: any) => s.key === 'header_bg_color')
      const textColor = items.find((s: any) => s.key === 'header_text_color')

      headerSettings.siteName = siteName?.value || 'Mega Monitor'
      headerSettings.headerMessage = headerMessage?.value || 'Welcome to Mega Monitor'
      headerSettings.logoUrl = logoUrl?.value || ''
      headerSettings.backgroundColor = bgColor?.value || '#4CAF50'
      headerSettings.textColor = textColor?.value || '#ffffff'

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
      console.log('Loading light theme settings from backend')
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
      lightStyleSettings.borderRadiusSm = parseInt(lightBorderRadiusSm?.value) || 4
      lightStyleSettings.borderRadiusMd = parseInt(lightBorderRadiusMd?.value) || 8
      lightStyleSettings.borderRadiusLg = parseInt(lightBorderRadiusLg?.value) || 12
      console.log('Light theme settings loaded:', lightStyleSettings)

      // Load dark theme settings
      console.log('Loading dark theme settings from backend')
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
      darkStyleSettings.borderRadiusSm = parseInt(darkBorderRadiusSm?.value) || 4
      darkStyleSettings.borderRadiusMd = parseInt(darkBorderRadiusMd?.value) || 8
      darkStyleSettings.borderRadiusLg = parseInt(darkBorderRadiusLg?.value) || 12
      console.log('Dark theme settings loaded:', darkStyleSettings)

      // For backward compatibility, also load old settings into current theme
      // Commented out to prevent overwriting theme-specific settings
      /*
      const buttonPrimaryBg = items.find((s: any) => s.key === 'button_primary_bg')
      const buttonSecondaryBg = items.find((s: any) => s.key === 'button_secondary_bg')
      const buttonDangerBg = items.find((s: any) => s.key === 'button_danger_bg')
      const cardBg = items.find((s: any) => s.key === 'card_bg')
      const cardBorder = items.find((s: any) => s.key === 'card_border')
      const panelBg = items.find((s: any) => s.key === 'panel_bg')
      const bodyBg = items.find((s: any) => s.key === 'body_bg')
      const contentBg = items.find((s: any) => s.key === 'content_bg')
      const textPrimary = items.find((s: any) => s.key === 'text_primary')
      const textSecondary = items.find((s: any) => s.key === 'text_secondary')
      const textMuted = items.find((s: any) => s.key === 'text_muted')
      const borderRadiusSm = items.find((s: any) => s.key === 'border_radius_sm')
      const borderRadiusMd = items.find((s: any) => s.key === 'border_radius_md')
      const borderRadiusLg = items.find((s: any) => s.key === 'border_radius_lg')

      // Load into the appropriate theme settings based on current theme (for backward compatibility)
      const currentSettings = themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings

      if (buttonPrimaryBg?.value) currentSettings.buttonPrimaryBg = buttonPrimaryBg.value
      if (buttonSecondaryBg?.value) currentSettings.buttonSecondaryBg = buttonSecondaryBg.value
      if (buttonDangerBg?.value) currentSettings.buttonDangerBg = buttonDangerBg.value
      if (cardBg?.value) currentSettings.cardBg = cardBg.value
      if (cardBorder?.value) currentSettings.cardBorder = cardBorder.value
      if (panelBg?.value) currentSettings.panelBg = panelBg.value
      if (bodyBg?.value) currentSettings.bodyBg = bodyBg.value
      if (contentBg?.value) currentSettings.contentBg = contentBg.value
      if (textPrimary?.value) currentSettings.textPrimary = textPrimary.value
      if (textSecondary?.value) currentSettings.textSecondary = textSecondary.value
      if (textMuted?.value) currentSettings.textMuted = textMuted.value
      if (borderRadiusSm?.value) currentSettings.borderRadiusSm = parseInt(borderRadiusSm.value)
      if (borderRadiusMd?.value) currentSettings.borderRadiusMd = parseInt(borderRadiusMd.value)
      if (borderRadiusLg?.value) currentSettings.borderRadiusLg = parseInt(borderRadiusLg.value)
      */

      // Apply CSS variables immediately after loading
      updateCSSVariables()
      console.log('Initial CSS variables applied on mount')
    } catch (err) {
      console.error('Failed to load settings:', err)
      error.value = 'Failed to load settings'
    } finally {
      loading.value = false
    }
  }

  // Update CSS variables
  const updateCSSVariables = () => {
    const root = document.documentElement
    const currentSettings = themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings

    console.log('Updating CSS variables for theme:', themeStore.theme, 'with settings:', currentSettings)

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

    // Button colors
    root.style.setProperty('--button-primary-text', '#ffffff')
    root.style.setProperty('--button-primary-hover', adjustColor(currentSettings.buttonPrimaryBg, -20))
    root.style.setProperty('--button-primary-border', currentSettings.buttonPrimaryBg)
    root.style.setProperty('--button-secondary-text', '#ffffff')
    root.style.setProperty('--button-secondary-hover', adjustColor(currentSettings.buttonSecondaryBg, -20))
    root.style.setProperty('--button-secondary-border', currentSettings.buttonSecondaryBg)
    root.style.setProperty('--button-danger-text', '#ffffff')
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

    console.log('CSS variables updated')
  }

  // Helper function to adjust color brightness
  const adjustColor = (color: string, amount: number): string => {
    // Simple color adjustment - darken by reducing RGB values
    const hex = color.replace('#', '')
    const r = Math.max(0, parseInt(hex.substr(0, 2), 16) + amount)
    const g = Math.max(0, parseInt(hex.substr(2, 2), 16) + amount)
    const b = Math.max(0, parseInt(hex.substr(4, 2), 16) + amount)
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
  }

  // Save header settings
  const saveHeaderSettings = async () => {
    try {
      const headerSettingsToSave = [
        { key: 'site_name', value: headerSettings.siteName, description: 'Site name displayed in header' },
        { key: 'header_message', value: headerSettings.headerMessage, description: 'Header welcome message or tagline' },
        { key: 'logo_url', value: headerSettings.logoUrl, description: 'Logo URL or base64 data' },
        { key: 'header_bg_color', value: headerSettings.backgroundColor, description: 'Header background color' },
        { key: 'header_text_color', value: headerSettings.textColor, description: 'Header text color' }
      ]

      const response = await http.get('/settings/read')
      const existingSettings = response.data.items || []

      for (const setting of headerSettingsToSave) {
        const existing = existingSettings.find((s: any) => s.key === setting.key)

        if (existing) {
          await http.put('/settings/update', {
            id: existing.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        } else {
          await http.post('/settings/create', {
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        }
      }

      // Notify other components
      window.dispatchEvent(new Event('settings-updated'))
    } catch (err) {
      console.error('Failed to save header settings:', err)
      throw err
    }
  }

  // Save style settings
  const saveStyleSettings = async () => {
    try {
      const currentSettings = themeStore.theme === 'dark' ? darkStyleSettings : lightStyleSettings
      const styleSettingsToSave = [
        { key: 'body_bg', value: currentSettings.bodyBg, description: 'Body background color' },
        { key: 'content_bg', value: currentSettings.contentBg, description: 'Content background color' },
        { key: 'button_primary_bg', value: currentSettings.buttonPrimaryBg, description: 'Primary button background color' },
        { key: 'button_secondary_bg', value: currentSettings.buttonSecondaryBg, description: 'Secondary button background color' },
        { key: 'button_danger_bg', value: currentSettings.buttonDangerBg, description: 'Danger button background color' },
        { key: 'card_bg', value: currentSettings.cardBg, description: 'Card background color' },
        { key: 'card_border', value: currentSettings.cardBorder, description: 'Card border color' },
        { key: 'panel_bg', value: currentSettings.panelBg, description: 'Panel background color' },
        { key: 'text_primary', value: currentSettings.textPrimary, description: 'Primary text color' },
        { key: 'text_secondary', value: currentSettings.textSecondary, description: 'Secondary text color' },
        { key: 'text_muted', value: currentSettings.textMuted, description: 'Muted text color' },
        { key: 'border_radius_sm', value: currentSettings.borderRadiusSm.toString(), description: 'Small border radius' },
        { key: 'border_radius_md', value: currentSettings.borderRadiusMd.toString(), description: 'Medium border radius' },
        { key: 'border_radius_lg', value: currentSettings.borderRadiusLg.toString(), description: 'Large border radius' }
      ]

      const response = await http.get('/settings/read')
      const existingSettings = response.data.items || []

      for (const setting of styleSettingsToSave) {
        const existing = existingSettings.find((s: any) => s.key === setting.key)

        if (existing) {
          await http.put('/settings/update', {
            id: existing.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        } else {
          await http.post('/settings/create', {
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        }
      }

      // Update CSS variables immediately - but only if light theme is active
      if (themeStore.theme === 'light') {
        updateCSSVariables()
      }

      // Notify other components
      window.dispatchEvent(new Event('settings-updated'))

      console.log('Light style settings saved successfully')
    } catch (err) {
      console.error('Failed to save style settings:', err)
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

      const response = await http.get('/settings/read')
      const existingSettings = response.data.items || []

      for (const setting of styleSettingsToSave) {
        const existing = existingSettings.find((s: any) => s.key === setting.key)

        if (existing) {
          await http.put('/settings/update', {
            id: existing.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        } else {
          await http.post('/settings/create', {
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        }
      }

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

      const response = await http.get('/settings/read')
      const existingSettings = response.data.items || []

      for (const setting of styleSettingsToSave) {
        const existing = existingSettings.find((s: any) => s.key === setting.key)

        if (existing) {
          await http.put('/settings/update', {
            id: existing.id,
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        } else {
          await http.post('/settings/create', {
            key: setting.key,
            value: setting.value,
            description: setting.description
          })
        }
      }

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
    headerSettings,
    styleSettings,
    lightStyleSettings,
    darkStyleSettings,
    loading,
    error,
    loaded,
    loadSettings,
    updateCSSVariables,
    saveHeaderSettings,
    saveStyleSettings,
    saveLightStyleSettings,
    saveDarkStyleSettings
  }
})