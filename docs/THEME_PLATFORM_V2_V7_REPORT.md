# Theme Platform v2 — V7 / Extension UI contract

Дата: 2026-10-08. Статус: изпълнен, одобрен и публикуван с beta.43.
V6 / Display Editor е одобрен на същата дата. След публикацията собственикът
прие резултата за приключен; M17 е затворен, без претенция за пълен live recovery отчет.

## Реализирано

- Публичен browser entry `@3mm/ui/v1`: `UI_CONTRACT_VERSION`, `UiSurface`,
  `UiButton`, `UiDialog`. Button/Dialog са същите Core primitives, не копия.
- Host build генерира hashed ESM asset и неговия import map; extension-ът не
  записва физически URL. Използва се съществуващият общ Vue browser runtime.
- Shell предоставя само read-only button/card варианти. Цветове, типография,
  размери и focus идват от общите host CSS tokens. Няма достъп до Core stores,
  credentials, router, permissions или API handlers чрез публичните exports.
- Съществуващият install-time compiler/validator допуска точно този import
  заедно с `vue`; private source imports и други UI versions/subpaths се отказват.
- [Публичен договор](EXTENSION_UI_V1.md): компоненти, native classes, tokens,
  ownership, съвместимост и ограничения. Application SDK остава **1.3**;
  Device Protocol, database, catalog, route authorization и API са непроменени.
- [Неутрален UI Reference](../modules/ui-reference/README.md): детерминистичен
  UI-only ZIP, без business service, device binding, credentials или API операции.
  Използва съществуващия compiled UI route contract с admin guard.

Старите Vue-only пакети остават съвместими. Не се прекомпилират автоматично,
не се променят техните handlers и hardcoded CSS не става автоматично theme-aware.
Compiled UI остава reviewed executable code, **не security sandbox**.

## Проверки

| Проверка | Резултат |
| --- | --- |
| Public exports, fallback, theme switch/draft, button semantics | 4 frontend теста |
| Shared Button/Dialog, shell audiences/mounting, existing compiled loader | 13 frontend теста |
| Compiler/import boundary и детерминистичен reference package | 9 backend теста |
| Type-check и production frontend build | Успешни |
| Истински ZIP validator + install-time Node/Vue compiler | Успешни |
| Browser: действителен compiled artifact + финален host UI module | Успешно зареждане, без наблюдавани console errors/warnings |

Общо **17 frontend + 9 backend** целеви теста. Full suite не е повторен за тази
локална стъпка; остава release gate. Провереният production build публикува
`extension-ui-v1-CaKcusZs.js` (0.48 kB / gzip 0.32 kB) и общ component/context
chunk (2.61 kB / gzip 1.34 kB). Това е размер на конкретния build, не гарантиран
постоянен hash или пълен performance benchmark. Не е добавен втори framework,
runtime CDN, theme registry или dependency download.

## Browser proof и граници

Изолираният preview на `127.0.0.1:5141/ui-reference` използва действителния
production public module, съществуващия frontend compiled loader и reference
artifact от истинския compiler. Core API responses и identity са синтетични;
всички mutation calls в fixture се отказват. Не са използвани live данни.

Проверени са Graphite/sidebar/solid/raised, Copper/top/outline/bordered и
built-in/legacy adapter; desktop 1440×900 и mobile 390×844, light/dark и EN/BG.
Това са изолирани design projections; реалният installer/lifecycle за тези
theme ZIP-ове е отделно V5 доказателство, не нов live V7 тест.

- Формата валидира празно име; loading/disabled semantics са покрити с тестове.
- Theme/shell промяна запазва незаписаното име и checkbox, без remount.
- Dialog: безопасен Cancel autofocus, Escape, Tab containment и focus return.
- Дългите BG текстове се пренасят; няма хоризонтално page overflow на 390px.
- Reference stylesheet съдържа само scoped layout; няма hardcoded тема по име.
- Финалният build е презареден в browser и повторно проверен с theme switch,
  BG draft и mobile dialog. Preview viewport override е върнат към нормалния.

Локални снимки (QA artifacts, извън release payload):

- [Graphite / light / desktop](../.runtime/theme-v7-ui/reference-graphite-light-desktop.png)
- [Copper / dark / mobile dialog](../.runtime/theme-v7-ui/reference-copper-dark-mobile-dialog.png)
- [Built-in / light / mobile](../.runtime/theme-v7-ui/reference-builtin-light-mobile.png)

Reference ZIP остава в `.runtime/ui-reference-1.0.0.zip`, не е auto-installed
и не е задължителна част от release. Изисква Core build, публикуващ този UI
entry; стар release без него не може да зареди новите imports.

## Доставка и финално приемане

Поисканите release/full suite минаха; beta.43 е публикуван от `4415cee` с
успешни CI/release workflows и Hub/Node пакети. На 2026-10-08 собственикът
потвърди, че резултатът му харесва, и изрично прие работата за приключена.
Разширените restart/rollback/portable recovery проби не са потвърдени с отделен
live отчет; остават общи platform-stability проверки. Destructive reset изисква
отделно одобрение и проверен backup. V7 сам по себе си не доказва live auth/lifecycle,
реални business actions или recovery.

Самата V7 реализация не извърши commit, push, release или deploy. Последвалата
заявка за beta.43 разрешава публикацията, не обновяване или reset на устройство.
M17 е затворен по последвалото финално приемане; виж [записа V8](THEME_PLATFORM_V2_PLAN.md#v8--реално-upgraderecovery-приемане-и-доставка).
