import { useI18n } from '@/utils/i18n'

const en = {
  title: 'Command resources', help: 'Choose a device for an application command. Review the change before restarting the application.',
  binding: 'Application command', device: 'Device', provider: 'Provider', contract: 'Contract', action: 'Action',
  loading: 'Loading resources…', refresh: 'Refresh status', close: 'Close', more: 'Load more devices',
  empty: 'This application declares no device commands.', current: 'Current device', target: 'New device',
  choose: 'Choose a compatible device', review: 'Review change', before: 'Current resource', after: 'New resource',
  chooseAgain: 'Change selection', unsupported: 'This change affects shared resources or an unsupported command profile. It cannot be made through this screen.',
  restart: 'The application will restart with this resource. Its selected permissions are retained.',
  acknowledge: 'I approve this resource change and the application restart.', apply: 'Change resource and restart',
  expired: 'This review has expired. Refresh and review the change again.',
  ready: 'Ready', unavailable: 'Currently unavailable', unknown: 'Readiness unknown', incompatible: 'Does not meet the command requirements',
  blocked: 'Cannot be selected', details: 'Requirement details', noCandidates: 'No matching resources are available in this page.',
  needsAccess: 'The application must be running with current access to this command. Use Application access to review its permissions.',
  failed: 'Resources could not be read. Refresh to check the current state.',
  stale: 'The application or its resources changed. Refresh and create a new review.',
  actor: 'A current administrator login is required.', uncertain: 'The change could not be confirmed. Check its status before taking another action.',
  pending: 'This resource change is unfinished. Execution remains blocked until its outcome is resolved.',
  recoverAcknowledgment: 'I have reviewed outstanding device operations and want to stop and verify the application runtime.',
  recover: 'Stop and verify runtime', completed: 'The resource change completed. Refresh to inspect current availability.',
  recovered: 'The application is stopped. Review its access, then explicitly activate it to use the selected resource.',
  external: 'Already started device operations may still finish on the original device. They are not repeated on the new resource.',
} as const
const bg: Record<keyof typeof en, string> = {
  title: 'Ресурси за команди', help: 'Изберете устройство за команда на приложението. Прегледайте промяната преди рестартирането му.',
  binding: 'Команда на приложението', device: 'Устройство', provider: 'Доставчик', contract: 'Договор', action: 'Операция',
  loading: 'Зареждане на ресурсите…', refresh: 'Проверка на състоянието', close: 'Затвори', more: 'Още устройства',
  empty: 'Приложението не декларира команди към устройства.', current: 'Текущо устройство', target: 'Ново устройство',
  choose: 'Изберете съвместимо устройство', review: 'Преглед на промяната', before: 'Текущ ресурс', after: 'Нов ресурс',
  chooseAgain: 'Промени избора', unsupported: 'Промяната засяга общи ресурси или неподдържан профил на команда. Тя не може да бъде извършена през този екран.',
  restart: 'Приложението ще се рестартира с този ресурс. Избраните му разрешения се запазват.',
  acknowledge: 'Одобрявам смяната на ресурса и рестартирането на приложението.', apply: 'Смени ресурса и рестартирай',
  expired: 'Прегледът е изтекъл. Опреснете състоянието и прегледайте промяната отново.',
  ready: 'Готов', unavailable: 'Временно недостъпен', unknown: 'Готовността е неизвестна', incompatible: 'Не отговаря на изискванията на командата',
  blocked: 'Не може да бъде избран', details: 'Подробности за изискванията', noCandidates: 'На тази страница няма подходящи ресурси.',
  needsAccess: 'Приложението трябва да работи с актуален достъп до тази команда. Прегледайте разрешенията му в „Достъп на приложението“.',
  failed: 'Ресурсите не могат да бъдат прочетени. Опреснете, за да проверите текущото състояние.',
  stale: 'Приложението или ресурсите му са променени. Опреснете и създайте нов преглед.',
  actor: 'Необходим е актуален администраторски вход.', uncertain: 'Промяната не е потвърдена. Проверете състоянието ѝ преди следващо действие.',
  pending: 'Смяната на ресурса е незавършена. Изпълнението остава блокирано до изясняване на резултата.',
  recoverAcknowledgment: 'Прегледах незавършените операции на устройствата и искам да спра и проверя процеса на приложението.',
  recover: 'Спри и провери процеса', completed: 'Смяната на ресурса е завършена. Опреснете, за да проверите текущата наличност.',
  recovered: 'Приложението е спряно. Прегледайте достъпа му и след това го активирайте изрично с избрания ресурс.',
  external: 'Вече започнатите операции може да завършат върху първоначалното устройство. Те не се повтарят върху новия ресурс.',
}
export function useCommandResourceLabels() {
  const { t, currentLanguage } = useI18n()
  return (key: keyof typeof en) => t(`commandResources.${key}`, currentLanguage.value.startsWith('bg') ? bg[key] : en[key])
}
