# Theme Platform v2 — V6 / DashboardList

Дата: 2026-10-07. Source baseline: `427f32e` плюс локалните промени.
Статус: **готов локално; визуално одобрен от собственика на 2026-10-07**.
Това е първият екран от V6, не приключване на V6 или Milestone 17.

## Обхват

- Dashboard cards, празен списък, брой табла и ясно отделени метаданни.
- Общите theme tokens, card/button варианти и reusable UI classes; без локални
  inline цветове и без конкретни theme имена в production компонента.
- Public/private/shared статус с текст и икона, не само цвят.
- Подравнени действия при дълги заглавия/URL; mobile layout без хоризонтално преливане.
- Create/Delete със споделения native `UiDialog`; достъпни заглавия и labels,
  required полета, Escape/Cancel, backdrop dismissal и връщане на focus.
- Delete започва с focus върху Cancel; компактният card бутон има преведен
  accessible name и остава видим само за собственика.

Запазени са list/fallback заявките, create/delete payloads, ownership логиката,
shared View, public Preview и editor destinations. Няма промяна на backend,
authorization, router, SDK, extension lifecycle или deployment архитектурата.

Production файлови промени: `frontend/src/views/DashboardList.vue` и неговият
`DashboardList.component.test.ts`; документацията описва този отделен етап.
Несвързаните локални installer и roadmap промени не са част от тази реализация.

## Проверки

- 8 DashboardList component теста: list/ownership, create, delete, theme variants,
  destinations, Escape/Cancel, empty state и backdrop dismissal.
- 2 shared UI primitive теста: общо **10 passed**.
- `npm run type-check` — успешно.
- `npm run build-only` — успешно, 326 modules.
- Browser: 1440×900 desktop и 390×844 mobile; BG/EN, light/dark,
  sidebar/top navigation, дълги labels/URL, Create/Delete dialogs.
- Native keyboard check: focus в Create title, Tab wrap, Escape към opener;
  Delete Cancel autofocus и връщане към card Delete при отказ.
- Built-in/legacy adapter е проверен визуално отделно.

Визуалният fixture използва реалните Vue компоненти, stores и theme renderer,
със синтетични данни и забранени mutations. Graphite Mint/Slate Copper descriptor
и палитра са използвани за вариантите. Това не повтаря V5 ZIP/font инсталацията:
package WOFF2 loading, live authentication, реални credentials, recovery и
offline icon availability **не са доказани от този fixture**. Full release suite
не е стартиран за тази scoped UI задача.

## Локални визуални доказателства

Снимките са ignored review artifacts, не се включват в Core release:

- [Desktop Graphite Mint / light / BG](../.runtime/theme-v6-dashboard/desktop-graphite-light-bg.png)
- [Mobile Graphite Mint / light / BG](../.runtime/theme-v6-dashboard/mobile-graphite-light-bg.png)
- [Mobile Slate Copper / dark / BG](../.runtime/theme-v6-dashboard/mobile-copper-dark-bg.png)
- [Delete / mobile / dark / Cancel focus](../.runtime/theme-v6-dashboard/delete-dialog-mobile-dark-bg.png)
- [Built-in / legacy / light / BG](../.runtime/theme-v6-dashboard/desktop-legacy-light-bg.png)

## Следващ gate

DashboardList е одобрен. V6 / Extensions е готов локално и чака отделен визуален
преглед: [отчет](THEME_PLATFORM_V2_V6_EXTENSIONS_REPORT.md). След него остават
Settings и Display Editor, V7 extension UI contract и V8 реално upgrade/recovery
приемане. Няма deploy, commit, push, release или live reset в тази задача.
