import { useI18n } from '@/utils/i18n'

const en = {
  action: 'Recover application', title: 'Recover application', close: 'Close', refresh: 'Refresh status',
  help: 'Stop and verify the application runtime. Its data, configuration and uploaded packages are preserved.',
  boundary: 'Stopping does not undo migrations or external effects. Check any unfinished work before continuing.',
  confirm: 'I have reviewed the possible external effects and want to stop the application for recovery.',
  stopped: 'The application is stopped. Review access before activating a package. Activation remains a separate action.',
  status: 'Current stage', loading: 'Checking current stage…', working: 'Stopping and verifying…',
  unavailable: 'Current stage could not be loaded. Refresh before recovery.',
  uncertain: 'Recovery could not be confirmed. Refresh status before taking another action.',
  missing: 'This installation is no longer present. Close and refresh Extensions.',
  inactive: 'This stage does not need lifecycle recovery. Close and use the normal application controls.',
  notice: 'An unfinished lifecycle needs recovery. Recover to a verified stopped state, or uninstall while preserving data.',
  catalog: 'Some package details are unavailable. Installed applications can still be recovered.',
  keyRecoveryTitle: 'Restore application access reviews',
  keyRecoveryHelp: 'Core was recovered and its previous review key is no longer current. Create a fresh key so applications can be reviewed again.',
  keyRecoveryConfirm: 'I understand that old approvals will not be restored and no application will be started.',
  keyRecoveryAction: 'Restore review access',
  keyRecoveryReady: 'Reviews are available again. Review each affected application’s access before activating it.',
  keyRecoveryUnavailable: 'Recovery is not currently available. Refresh the status or check Core recovery before continuing.',
  keyRecoveryUnconfirmed: 'Recovery was not confirmed. Refresh the status before taking another action.',
  keyRecoveryRequired: 'Core access reviews need recovery. Close this dialog and use “Restore application access reviews” on Extensions.',
}
const bg: typeof en = {
  action: 'Възстанови приложението', title: 'Възстановяване на приложение', close: 'Затвори', refresh: 'Обнови състоянието',
  help: 'Спиране и проверка на приложението. Данните, настройките и качените пакети се запазват.',
  boundary: 'Спирането не отменя миграции или външни ефекти. Провери незавършените действия, преди да продължиш.',
  confirm: 'Прегледах възможните външни ефекти и искам да спра приложението за възстановяване.',
  stopped: 'Приложението е спряно. Прегледай достъпа преди активиране на пакет. Активирането е отделно действие.',
  status: 'Текущ етап', loading: 'Проверка на текущия етап…', working: 'Спиране и проверка…',
  unavailable: 'Текущият етап не може да бъде зареден. Обнови го преди възстановяване.',
  uncertain: 'Възстановяването не е потвърдено. Обнови състоянието преди следващо действие.',
  missing: 'Тази инсталация вече не съществува. Затвори и обнови Extensions.',
  inactive: 'Този етап не изисква възстановяване. Затвори и използвай обичайните действия за приложението.',
  notice: 'Незавършената операция изисква възстановяване. Възстанови до проверено спряно състояние или деинсталирай със запазване на данните.',
  catalog: 'Част от данните за пакетите не са достъпни. Инсталираните приложения могат да бъдат възстановени.',
  keyRecoveryTitle: 'Възстановяване на прегледите за достъп',
  keyRecoveryHelp: 'Core е възстановен и предишният ключ за прегледи вече не е актуален. Създай нов ключ, за да могат приложенията да бъдат прегледани отново.',
  keyRecoveryConfirm: 'Разбирам, че старите одобрения няма да се върнат и няма да се стартира приложение.',
  keyRecoveryAction: 'Възстанови прегледите',
  keyRecoveryReady: 'Прегледите отново са достъпни. Прегледай достъпа на всяко засегнато приложение преди активиране.',
  keyRecoveryUnavailable: 'Възстановяването не е достъпно в момента. Обнови състоянието или провери възстановяването на Core.',
  keyRecoveryUnconfirmed: 'Възстановяването не е потвърдено. Обнови състоянието, преди да продължиш.',
  keyRecoveryRequired: 'Прегледите за достъп в Core трябва да бъдат възстановени. Затвори прозореца и използвай „Възстановяване на прегледите за достъп“ в „Разширения“.',
}
export const interruptedLifecycleStatuses = new Set(['activating', 'disabling', 'uninstalling', 'recovering', 'recovery_required'])
export function useRecoveryLabels() {
  const { currentLanguage } = useI18n()
  return (key: keyof typeof en) => (currentLanguage.value.startsWith('bg') ? bg : en)[key]
}
