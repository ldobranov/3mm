import http from '@/utils/dynamic-http'
import { normalizeAvailableLanguages } from '@/utils/menu-navigation'
import type { SettingRecord } from '@/utils/settings-api'

export interface Translations {
  [key: string]: any
}

export type LanguageSetting = Omit<SettingRecord, 'language_code'> & {
  language_code?: string
}

export async function readAvailableLanguages(): Promise<string[]> {
  const response = await http.get('/language/available')
  return normalizeAvailableLanguages(response.data.languages)
}

export async function readFrontendTranslations(languageCode: string): Promise<Translations> {
  const response = await http.get(`/api/translations/${encodeURIComponent(languageCode)}`)
  return response.data.frontend || {}
}

export async function readLanguageSettings(languageCode: string): Promise<LanguageSetting[]> {
  const response = await http.get(`/settings/language/${encodeURIComponent(languageCode)}`)
  return (response.data.items || []).map((setting: SettingRecord) => ({
    ...setting,
    language_code: setting.language_code ?? undefined
  }))
}

export async function saveCurrentUserLanguage(languageCode: string): Promise<void> {
  await http.post('/api/user/language', { language: languageCode })
}
