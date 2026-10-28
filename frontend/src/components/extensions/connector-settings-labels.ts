import { useI18n } from '@/utils/i18n'

const en = {
  title: 'Application settings', connector: 'Connector', origin: 'Service address', path: 'Allowed path',
  help: 'Configure the connection in Core. Saving does not contact the service or start the application.',
  access: 'Saving requires fresh access approval. If the application is running, switch it off, review Application access, then activate it again.',
  credential: 'Credential', existing: 'Use an existing credential', create: 'Create a new credential', choose: 'Choose a credential',
  label: 'Credential name', username: 'Username', password: 'Password', token: 'Token / API key', header: 'API key header',
  save: 'Save connection', rotate: 'Rotate credential', revoke: 'Revoke credential', cancel: 'Cancel', close: 'Close',
  confirm: 'I confirm this credential change for the affected connectors.', affected: 'Affected connectors',
  confirmRotate: 'Confirm rotation', confirmRevoke: 'Confirm revocation', refresh: 'Refresh', check: 'Check result',
  loading: 'Loading settings…', configured: 'Configured', unconfigured: 'Not configured', disabled: 'Disabled', unavailable: 'Unavailable',
  applied: 'Saved. Review access before restarting. This is not a connection test.',
  uncertain: 'The result is unknown. Check this request; do not repeat Save.', request: 'Request',
  failed: 'Settings could not be read. Try refreshing.', actor: 'A current administrator login is required.',
  invalid: 'Check the service address and credential fields. No new change was saved.',
  stale: 'The package or settings changed. Refresh before making another change.',
  stopFirst: 'Switch off the application before configuring this package. Its data is preserved.',
  key: 'Credential encryption is unavailable. Core must have its configured encryption key before saving credentials.',
  empty: 'This package has no connector settings.',
} as const
const bg: Record<keyof typeof en, string> = {
  title: 'Настройки на приложението', connector: 'Връзка', origin: 'Адрес на услугата', path: 'Разрешен път',
  help: 'Настройвате връзката в Core. Записът не се свързва с услугата и не стартира приложението.',
  access: 'Записът изисква ново одобрение на правата. Ако приложението работи, изключете го, прегледайте правата и го активирайте отново.',
  credential: 'Данни за вход', existing: 'Използвай съществуващи данни', create: 'Създай нови данни за вход', choose: 'Изберете данни за вход',
  label: 'Име на данните за вход', username: 'Потребителско име', password: 'Парола', token: 'Токен / API ключ', header: 'HTTP поле за API ключа',
  save: 'Запази връзката', rotate: 'Смени данните за вход', revoke: 'Отмени данните за вход', cancel: 'Отказ', close: 'Затвори',
  confirm: 'Потвърждавам тази промяна на данните за вход за засегнатите връзки.', affected: 'Засегнати връзки',
  confirmRotate: 'Потвърди смяната', confirmRevoke: 'Потвърди отмяната', refresh: 'Обнови', check: 'Провери резултата',
  loading: 'Зареждане на настройките…', configured: 'Настроена', unconfigured: 'Не е настроена', disabled: 'Изключена', unavailable: 'Недостъпна',
  applied: 'Записано. Прегледайте правата преди рестартиране. Това не е проба на връзката.',
  uncertain: 'Резултатът е неизвестен. Проверете тази заявка; не повтаряйте записа.', request: 'Заявка',
  failed: 'Настройките не могат да бъдат прочетени. Опитайте обновяване.', actor: 'Необходим е текущ вход като администратор.',
  invalid: 'Проверете адреса и данните за вход. Не е записана нова промяна.',
  stale: 'Пакетът или настройките са променени. Обновете преди следваща промяна.',
  stopFirst: 'Изключете приложението преди настройване на този пакет. Данните му се запазват.',
  key: 'Шифроването на данните за вход е недостъпно. Core трябва да има настроения си ключ за шифроване.',
  empty: 'Този пакет няма настройки за връзки.',
}
export function useConnectorSettingsLabels() {
  const { currentLanguage } = useI18n()
  return (key: keyof typeof en): string => currentLanguage.value.toLowerCase().split(/[-_]/)[0] === 'bg' ? bg[key] : en[key]
}
