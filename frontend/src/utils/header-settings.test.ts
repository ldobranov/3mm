import { describe, expect, it } from 'vitest'
import {
  DEFAULT_HEADER_SETTINGS,
  editableHeaderTextValue,
  headerTextFallback,
  resolveHeaderSettings
} from './header-settings'
import type { SettingRecord } from './settings-api'

describe('header settings', () => {
  it('localizes text while keeping logo and colors global', () => {
    const allSettings: SettingRecord[] = [
      { key: 'site_name', value: 'Mega Monitor', language_code: 'en' },
      { key: 'site_name', value: 'Мега Монитор', language_code: 'bg' },
      { key: 'header_message', value: 'Welcome', language_code: 'en' },
      { key: 'header_message', value: 'Добре дошли', language_code: 'bg' },
      { key: 'logo_url', value: '/uploads/settings/logo.svg', language_code: null },
      { key: 'header_bg_color', value: '#123456', language_code: null },
      { key: 'header_bg_color', value: '#abcdef', language_code: 'bg' },
      { key: 'header_text_color', value: '#fedcba', language_code: null }
    ]

    expect(resolveHeaderSettings(allSettings, allSettings, 'bg')).toEqual({
      siteName: 'Мега Монитор',
      headerMessage: 'Добре дошли',
      logoUrl: '/uploads/settings/logo.svg',
      backgroundColor: '#123456',
      textColor: '#fedcba'
    })
  })

  it('uses legacy English visual values as one shared fallback', () => {
    const allSettings: SettingRecord[] = [
      { key: 'header_bg_color', value: '#112233', language_code: 'en' },
      { key: 'header_bg_color', value: '#445566', language_code: 'bg' },
      { key: 'header_text_color', value: '#ffffff', language_code: 'en' }
    ]

    const resolved = resolveHeaderSettings([], allSettings, 'bg')

    expect(resolved.backgroundColor).toBe('#112233')
    expect(resolved.textColor).toBe('#ffffff')
  })

  it('keeps an intentionally empty global logo empty', () => {
    const allSettings: SettingRecord[] = [
      { key: 'logo_url', value: '', language_code: null },
      { key: 'logo_url', value: '/legacy-english-logo.svg', language_code: 'en' }
    ]

    expect(resolveHeaderSettings([], allSettings, 'bg').logoUrl).toBe('')
  })

  it('keeps missing translations empty in the editor and exposes English as fallback', () => {
    const english: SettingRecord[] = [
      { key: 'site_name', value: 'Control Center', language_code: 'en' }
    ]
    const bulgarian: SettingRecord[] = [
      { key: 'site_name', value: 'Legacy global name', language_code: null }
    ]
    const settingsByLanguage = new Map([
      ['en', english],
      ['bg', bulgarian]
    ])

    expect(editableHeaderTextValue(bulgarian, 'site_name', 'bg')).toBe('')
    expect(headerTextFallback(settingsByLanguage, 'site_name', DEFAULT_HEADER_SETTINGS.siteName))
      .toBe('Control Center')
  })
})
