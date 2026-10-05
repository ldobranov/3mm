import { useI18n } from './i18n'

const en = {
  navigation: 'Navigation', openMenu: 'Open navigation', closeMenu: 'Close navigation', skip: 'Skip to content',
  language: 'Language', search: 'Search commands', recovery: 'Built-in appearance recovery',
  preview: 'Appearance preview', previewNote: 'Browser-only preview. Nothing is saved to the installation.',
  exit: 'Back to Settings', restore: 'Restore built-in preview', recoveryNote: 'The preview has been cleared. Your installed theme and saved settings are unchanged.',
  restoreInstalled: 'Use built-in permanently', restoreFailed: 'Could not change the theme. Please retry.', restoreDone: 'Built-in selected. Saved settings are preserved.',
  layout: 'Navigation layout', sidebar: 'Sidebar', top: 'Top navigation', density: 'Density',
  compact: 'Compact', comfortable: 'Comfortable', header: 'Use theme header colors',
  buttons: 'Button style', solid: 'Solid', outline: 'Outline', cards: 'Card style', bordered: 'Bordered', raised: 'Raised',
  mode: 'Color mode', light: 'Light', dark: 'Dark', primitives: 'Shared controls',
  primary: 'Primary action', secondary: 'Secondary action', danger: 'Danger action', disabled: 'Disabled', loading: 'Loading',
  forms: 'Form controls', name: 'Name', namePlaceholder: 'A clear, descriptive name',
  description: 'Description', descriptionPlaceholder: 'Optional details', error: 'Please enter a name.',
  enabled: 'Enable this example', enabledHelp: 'Demonstration only — no hardware or application operations.',
  dialog: 'Open test dialog', dialogTitle: 'Review example settings', cancel: 'Cancel', confirm: 'Validate example',
  close: 'Close', ready: 'Ready', pending: 'Pending', status: 'Status', resource: 'Resource', owner: 'Owner',
  table: 'Table and status', example: 'Example resource with a longer label', currentUser: 'Current user',
  validated: 'Example validated. No data was saved.', preferences: 'Preview controls',
} as const
const bg: Record<keyof typeof en, string> = {
  navigation: 'Навигация', openMenu: 'Отвори навигацията', closeMenu: 'Затвори навигацията', skip: 'Към съдържанието',
  language: 'Език', search: 'Търси команди', recovery: 'Връщане към вградения изглед',
  preview: 'Преглед на оформлението', previewNote: 'Временен преглед в този браузър. Нищо не се записва в инсталацията.',
  exit: 'Назад към Настройки', restore: 'Възстанови вградения преглед', recoveryNote: 'Прегледът е изчистен. Инсталираната тема и запазените настройки не са променени.',
  restoreInstalled: 'Използвай вградената тема постоянно', restoreFailed: 'Темата не може да се промени. Опитай отново.', restoreDone: 'Избрана е вградената тема. Запазените настройки са съхранени.',
  layout: 'Разположение на навигацията', sidebar: 'Странична лента', top: 'Горна навигация', density: 'Плътност',
  compact: 'Компактна', comfortable: 'Свободна', header: 'Използвай цветовете на темата за хедъра',
  buttons: 'Стил на бутоните', solid: 'Плътни', outline: 'Контурни', cards: 'Стил на картите', bordered: 'С рамка', raised: 'Със сянка',
  mode: 'Цветови режим', light: 'Светъл', dark: 'Тъмен', primitives: 'Общи контроли',
  primary: 'Основно действие', secondary: 'Вторично действие', danger: 'Опасно действие', disabled: 'Неактивно', loading: 'Зареждане',
  forms: 'Полета на формата', name: 'Име', namePlaceholder: 'Ясно и описателно име',
  description: 'Описание', descriptionPlaceholder: 'Допълнителни подробности', error: 'Моля, въведи име.',
  enabled: 'Включи този пример', enabledHelp: 'Само демонстрация — без операции с хардуер или приложения.',
  dialog: 'Отвори тестов диалог', dialogTitle: 'Преглед на примерните настройки', cancel: 'Отказ', confirm: 'Провери примера',
  close: 'Затвори', ready: 'Готово', pending: 'Изчаква', status: 'Статус', resource: 'Ресурс', owner: 'Собственик',
  table: 'Таблица и статус', example: 'Примерен ресурс с по-дълъг етикет', currentUser: 'Текущ потребител',
  validated: 'Примерът е проверен. Няма записани данни.', preferences: 'Контроли за прегледа',
}
export function useUiLabels() {
  const { t, currentLanguage } = useI18n()
  return (key: keyof typeof en) => t(`uiPlatform.${key}`, (currentLanguage.value === 'bg' ? bg : en)[key])
}
