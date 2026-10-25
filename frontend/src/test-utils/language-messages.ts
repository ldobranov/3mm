import languagePack from '../../../modules/language-bg/language-extension.json'
/** Component tests load the same dictionaries delivered by the language extension. */
export function movedLanguageLabel(key: string, fallback: string, language: string): string {
  const [namespace, name] = key.split('.')
  if (language !== 'bg' || !['uiPlatform', 'applicationAuthority'].includes(namespace)) return fallback
  const dictionaries = languagePack.frontend as unknown as Record<string, Record<string, string>>
  return dictionaries[namespace]?.[name] || fallback
}
