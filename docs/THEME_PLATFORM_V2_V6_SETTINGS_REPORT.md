# Theme Platform v2 — V6 / Settings

Дата: 2026-10-07. Source baseline: `427f32e` плюс локалните промени.
Статус: **двете части са одобрени; последното продължение на собственика е от 2026-10-08**.
DashboardList и Extensions са одобрени. Това не приключва V6 или Milestone 17.

## Обхват

- Компактна desktop навигация и именуван native select на mobile, със същите
  секции, permission filtering, anchors и theme bookmark.
- Общите Settings panels използват semantic tokens и theme card варианти;
  Application/Header формите използват общите controls и button варианти.
- Application: default mode/language, session duration и AI полетата запазват
  досегашните save handlers. Добавени са асоциирани labels; няма промяна на
  auth, продължителностите, keys или backend validation.
- Header: localized text drafts са отделни от споделеното лого. Цветовете и
  layout остават в Theme Customization. Upload/crop endpoints са непроменени.
- Mobile навигацията не размонтира останалите секции; незаписаните form drafts
  остават при смяна на секция. Няма нов router или дублиран settings store.
- Image editor: upload hover използва theme surface/text tokens вместо светъл
  legacy hover фон; Close има достъпно име. Canvas/crop/upload логиката не е
  променяна. Това не е пълна миграция на image editor към общия native dialog.

След одобрението на първата част са довършени вътрешните форми:

- Menu: native controls, компактни item cards, достъпни labels, подредба на
  действията и mobile stacking. Запазени са localization, dynamic route choices,
  audience ограниченията, drag reorder и съществуващите confirmations.
- Network: общият SettingsSection, тематични forms/status/actions и responsive
  recovery cards. Премахнати са оставащите Bootstrap `text-muted` класове,
  които правеха описанията почти невидими в dark mode.
- Backup: theme surfaces/actions, ясни preview metrics, portable file recovery
  и wrapping на дългите backup identifiers. Няма промяна на export/restore.
- Diagnostics: статусите имат текст и semantic color, не само цветна точка;
  download и redaction поведението са непроменени.
- Device control: отделени normal/danger действия, четими предупреждения и
  mobile buttons. Native confirm/prompt и точният `FACTORY RESET` са запазени.
- Built-in palette: тематични color/radius controls, save button и непроменени
  live bindings. Legacy ограничението от 150px на hex полето се отменя само в
  `.ui-v2`, без глобално CSS пренаписване. Package-specific options остават в
  съществуващия Theme workspace, не са подменени с тези legacy настройки.

Допълнителни production файлове: MenuConfigurationSection, MenuEditor,
NetworkConfigurationSection, BackupRecoverySection, DiagnosticsSection,
SystemControlSection, ThemeCustomizationSection и ColorPicker.
Първата част включва Settings, SettingsSection, ApplicationSettingsSection,
HeaderCustomizationSection, LanguageSelector, ThemeSelector и ImageEditorModal.
Няма backend, SDK, database, routing или deployment промяна.

## Проверки

- 51 целеви frontend теста в 10 файла: Settings (7), theme selection/preview (6),
  appearance (12), backup (4), image editor (5), network (3), diagnostics (3),
  device controls (5), MenuEditor (4) и built-in palette (2).
- Settings тестовете проверяват непроменени API payloads, dynamic route choices,
  visibility, language/shared-logo разделението, drafts и theme bookmark.
  Това не е нова backend authorization проверка.
- Новите проверки покриват menu language/custom path/admin defaults/reorder,
  отказ от restart/reset, текстовите diagnostic states и color/radius/save
  bindings. Използват mock API; не изпълняват destructive операции.
- Type-check и `npm run build-only`: успешни, 325 modules.
- Browser: Graphite Mint/light/desktop/BG, Slate Copper/dark/390px/BG,
  built-in adapter/light/desktop и mobile/EN. Освен първата част са проверени
  Menu, Network, Backup, Diagnostics, Device control и built-in color controls.
- При 390px няма хоризонтално преливане. Desktop rail и mobile select не се
  дублират. Диалогът за логото е четим и след посочване в dark mode.
- Съществуващите ThemePackages unit fixtures издават RouterLink warning;
  тестовете са успешни. Не е променян test harness извън този обхват.

Browser fixture използва реалните UI компоненти със синтетични settings/theme
projection данни. Всички mutations са блокирани; няма изпратен logo, записани
credentials, network промени или live reset/backup операции. Това не доказва
ZIP/font delivery, live install, реален auth или V8 recovery приемане.
Някои съществуващи преводи използват EN fallback; не са добавяни конкретни
бизнес extensions или hardcoded theme имена в Core.

## Визуални доказателства

Ignored review artifacts; не се включват в Core release:

- [Theme / desktop / light / BG](../.runtime/theme-v6-dashboard/settings-theme-desktop-light-bg.png)
- [Application / desktop / light / BG](../.runtime/theme-v6-dashboard/settings-application-desktop-light-bg.png)
- [Header / desktop / light / BG](../.runtime/theme-v6-dashboard/settings-header-desktop-light-bg.png)
- [Application / mobile / dark / BG](../.runtime/theme-v6-dashboard/settings-application-mobile-dark-bg.png)
- [Header / mobile / dark / BG](../.runtime/theme-v6-dashboard/settings-header-mobile-dark-bg.png)
- [Theme / mobile / dark / BG](../.runtime/theme-v6-dashboard/settings-theme-mobile-dark-bg.png)
- [Logo modal / mobile / dark / BG](../.runtime/theme-v6-dashboard/settings-logo-modal-mobile-dark-bg.png)
- [Built-in adapter / desktop / light / EN](../.runtime/theme-v6-dashboard/settings-builtin-desktop-light-en.png)
- [Menu / desktop / light](../.runtime/theme-v6-dashboard/settings-menu-graphite-light-desktop.png)
- [Network / desktop / light](../.runtime/theme-v6-dashboard/settings-network-graphite-light-desktop.png)
- [Backup / desktop / light](../.runtime/theme-v6-dashboard/settings-backup-graphite-light-desktop.png)
- [Diagnostics / desktop / light](../.runtime/theme-v6-dashboard/settings-diagnostics-graphite-light-desktop.png)
- [Device control / desktop / light](../.runtime/theme-v6-dashboard/settings-system-graphite-light-desktop.png)
- [Menu / mobile / dark](../.runtime/theme-v6-dashboard/settings-menu-copper-dark-mobile.png)
- [Network / mobile / dark](../.runtime/theme-v6-dashboard/settings-network-copper-dark-mobile.png)
- [Backup / mobile / dark](../.runtime/theme-v6-dashboard/settings-backup-copper-dark-mobile.png)
- [Diagnostics / mobile / dark](../.runtime/theme-v6-dashboard/settings-diagnostics-copper-dark-mobile.png)
- [Device control / mobile / dark](../.runtime/theme-v6-dashboard/settings-system-copper-dark-mobile.png)
- [Built-in colors / desktop / light](../.runtime/theme-v6-dashboard/settings-colors-builtin-light-desktop.png)
- [Built-in colors / mobile / light](../.runtime/theme-v6-dashboard/settings-colors-builtin-light-mobile.png)

## Следващ gate

Settings е приет визуално; следващата visual gate е Display Editor.
Не се твърди пълна миграция на native browser confirmations към UI dialog:
защитните prompt/confirm действия в Settings умишлено остават непроменени.
След Display Editor следват V7 UI contract и V8, като отделни задачи.
Няма deploy, commit, push, release или live reset в тази задача. M17 остава отворен.
