import type { SettingRecord } from '@/utils/settings-api'

export const DEFAULT_HEADER_SETTINGS = {
  siteName: 'Mega Monitor',
  headerMessage: 'Welcome to Mega Monitor',
  logoUrl: '',
  backgroundColor: '#4CAF50',
  textColor: '#ffffff'
} as const

export type HeaderTextKey = 'site_name' | 'header_message'

export interface ResolvedHeaderSettings {
  siteName: string
  headerMessage: string
  logoUrl: string
  backgroundColor: string
  textColor: string
}

function valueOrEmpty(setting: SettingRecord | undefined): string {
  return setting?.value?.trim() ? setting.value : ''
}

function exactLanguageSetting(
  settings: SettingRecord[],
  key: string,
  languageCode: string
): SettingRecord | undefined {
  return settings.find(setting => setting.key === key && setting.language_code === languageCode)
}

function legacyGlobalSetting(settings: SettingRecord[], key: string): SettingRecord | undefined {
  return settings.find(setting => setting.key === key && setting.language_code == null)
}

function localizedTextValue(
  localizedSettings: SettingRecord[],
  allSettings: SettingRecord[],
  key: HeaderTextKey,
  languageCode: string,
  fallback: string
): string {
  const exactValue = valueOrEmpty(exactLanguageSetting(localizedSettings, key, languageCode))
  if (exactValue) return exactValue

  const englishValue = valueOrEmpty(exactLanguageSetting(allSettings, key, 'en'))
  if (englishValue) return englishValue

  return valueOrEmpty(legacyGlobalSetting(allSettings, key)) || fallback
}

function sharedVisualValue(
  allSettings: SettingRecord[],
  key: string,
  fallback: string,
  allowEmpty = false
): string {
  const globalSetting = legacyGlobalSetting(allSettings, key)
  if (globalSetting && (allowEmpty || globalSetting.value.trim())) {
    return globalSetting.value
  }

  // Older installations stored visual header settings per language. Treat the
  // English value as the single shared value until the next explicit save.
  return valueOrEmpty(exactLanguageSetting(allSettings, key, 'en')) || fallback
}

export function resolveHeaderSettings(
  localizedSettings: SettingRecord[],
  allSettings: SettingRecord[],
  languageCode: string
): ResolvedHeaderSettings {
  return {
    siteName: localizedTextValue(
      localizedSettings,
      allSettings,
      'site_name',
      languageCode,
      DEFAULT_HEADER_SETTINGS.siteName
    ),
    headerMessage: localizedTextValue(
      localizedSettings,
      allSettings,
      'header_message',
      languageCode,
      DEFAULT_HEADER_SETTINGS.headerMessage
    ),
    logoUrl: sharedVisualValue(allSettings, 'logo_url', DEFAULT_HEADER_SETTINGS.logoUrl, true),
    backgroundColor: sharedVisualValue(
      allSettings,
      'header_bg_color',
      DEFAULT_HEADER_SETTINGS.backgroundColor
    ),
    textColor: sharedVisualValue(
      allSettings,
      'header_text_color',
      DEFAULT_HEADER_SETTINGS.textColor
    )
  }
}

export function editableHeaderTextValue(
  settings: SettingRecord[],
  key: HeaderTextKey,
  languageCode: string
): string {
  const exactValue = exactLanguageSetting(settings, key, languageCode)?.value
  if (exactValue !== undefined) return exactValue

  // Pre-multilingual installations used global text. Expose it only as the
  // English editable value; other languages should remain visibly distinct.
  if (languageCode === 'en') {
    return legacyGlobalSetting(settings, key)?.value || ''
  }

  return ''
}

export function headerTextFallback(
  settingsByLanguage: Map<string, SettingRecord[]>,
  key: HeaderTextKey,
  fallback: string
): string {
  const englishSettings = settingsByLanguage.get('en') || []
  return editableHeaderTextValue(englishSettings, key, 'en') || fallback
}
