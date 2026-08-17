import http from '@/utils/dynamic-http'

export interface SettingRecord {
  id?: number
  key: string
  value: string
  description?: string
  language_code?: string | null
}

export async function readSettings(languageCode?: string): Promise<SettingRecord[]> {
  const suffix = languageCode ? `?language=${encodeURIComponent(languageCode)}` : ''
  const response = await http.get(`/settings/read${suffix}`)
  return response.data.items || []
}

function matchesSetting(existing: SettingRecord, setting: SettingRecord): boolean {
  if (existing.key !== setting.key) return false
  if (setting.language_code === undefined) return true
  return (existing.language_code ?? null) === (setting.language_code ?? null)
}

export async function upsertSettings(settings: SettingRecord[]): Promise<void> {
  if (settings.length === 0) return

  const existingSettings = await readSettings()

  for (const setting of settings) {
    const existing = existingSettings.find(item => matchesSetting(item, setting))
    if (existing?.id !== undefined) {
      await http.put('/settings/update', { id: existing.id, ...setting })
    } else {
      await http.post('/settings/create', setting)
    }
  }
}
