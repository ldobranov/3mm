# Theme Platform v2 — V0 baseline и зависимости

Дата: 2026-10-05. Статус: **V0 завършен локално**, без redesign.
План: [THEME_PLATFORM_V2_PLAN.md](THEME_PLATFORM_V2_PLAN.md).
Отправна точка: commit `0f0ca97f824aec4b9807f7b0df506d650f704d6e`,
`v0.3.0-beta.36`. Няма промяна на production код, backend, SDK или deployment.

## 1. Собственици и граници

| Област | Сегашен собственик | Какво запазваме |
| --- | --- | --- |
| Startup | `frontend/src/main.ts` | Ред на Pinia/i18n/router, extension refresh и auth lifecycle |
| Shell | `App.vue` и `Menu.vue` | RouterView, branding, responsive navigation и Command Palette |
| Меню | `Menu.vue`, `utils/menu-navigation.ts`, router registrations | Data-driven items, audience/role filtering, динамични маршрути |
| Режим | `stores/theme.ts` | Browser light/dark preference и `dark-mode` върху html/body |
| Appearance | `stores/settings.ts`, `utils/theme-extension.ts` | Един loader/store, публична безопасна projection, v1 validation/fallback |
| Header | `utils/header-settings.ts`, Header/Menu Customization | Локализирани текстове; отделни глобални визуални overrides |
| Extension UI | `utils/compiled-ui.ts`, `utils/extension-components.ts` | Съществуващ loader и dynamic registrations; не вътрешни Core imports |

Core продължава да притежава разрешените действия и маршрути. Theme contract не
трябва да променя login, роли, menu visibility, API handlers или business данни.
Необходимата обща UI граница още не е библиотека от публични Core компоненти:
compiled UI зарежда extension код/CSS, а legacy extensions могат да имат собствени
глобални и hardcoded стилове. Автоматично тематизиране на всички тях не е доказано.

## 2. Зависимости, които V1–V3 трябва да адресират

1. **Две места за header loading.** App зарежда resolved header във свои refs,
   а Menu използва settings store. При нов shell консолидираме собствеността,
   без да променяме локализираното съдържание или сегашната precedence.
2. **Тема и header не са едно и също.** V1 пакетът има 11 цвята и 3 радиуса;
   header/menu overrides са отделни. V2 трябва да има изричен избор за styling,
   а не тихо да изтрие запазените цветове.
3. **CSS overlap.** Bootstrap, global CSS, scoped CSS и inline styles едновременно
   оформят `.btn`, `.card`, `.form-control`, `.table`, navigation и layouts.
   Новите primitives трябва да имат ясни собствени класове; legacy остава работещ.
4. **Непълен semantic договор.** Focus, hover, success/error, typography, spacing
   и density не са изцяло theme-controlled. Settings генерира множество CSS
   aliases; списъкът за cleanup не покрива всички записвани aliases. V1 adapter
   трябва да определи цялата собственост и cleanup, включително нулевите радиуси.
5. **Външни и липсващи assets.** `frontend/index.html` зарежда Bootstrap Icons
   1.11.1 от jsDelivr. Inter е в font stack, но няма деклариран локален font asset.
   Това не е offline baseline. По-късно icons/fonts трябва да са локални и bounded.
6. **Palette извън общия styling.** Command Palette използва собствени фиксирани
   цветове и статични command labels. Запазваме Ctrl+K, Escape, focus и handlers;
   включването му в tokens/i18n е отделна scoped промяна, не премахване на функции.
7. **Bootstrap mobile collapse.** Menu зависи от Bootstrap JS. V3 drawer може да
   замени presentation механизма, но трябва да използва същите navigation данни.

Tailwind dependency и `assets/tailwind.css` съществуват, но не са активният entry
pipeline. V0 не добавя framework и не премахва несвързани dependencies.

### CSS census

Read-only regex census на 53 Vue файла, включително bundled modules:

- 17 файла с inline style attributes, общо 126 срещания;
- 22 файла с Bootstrap class heuristic;
- 26 файла с hex color literals, включително валидни CSS fallback стойности.

Това са ориентири, не AST анализ и не брой дефекти.

| Начален екран/компонент | Inline style attributes | Hex literals |
| --- | ---: | ---: |
| App | 2 | 5 |
| Menu | 10 | 0 |
| CommandPalette | 0 | 26 |
| DashboardList | 9 | 2 |
| Settings | 3 | 8 |
| Extensions | 0 | 1 |
| DisplayEditor | 10 | 0 |

## 3. Build и целеви проверки

Среда: Windows checkout; Node 24.19.0, npm 11.17.0, Vite 6.4.3.
`npm run build-only` е успешен: Vite 4.07 s, общ command wall time 7.05 s,
301 transformed modules. Не е benchmark на Raspberry или browser page load.

| Production assets | Брой | Bytes | Сбор gzip bytes |
| --- | ---: | ---: | ---: |
| `dist/assets/*.js` | 21 | 775637 | 233624 |
| `dist/assets/*.css` | 18 | 385611 | 61615 |

Main entry: JS 250.39 kB / gzip 79.09 kB; CSS 250.57 kB / gzip 34.68 kB.
Сборът включва lazy chunks; не е initial download budget. Външният icon font и
отделните compiled-UI runtime assets не влизат в тази таблица. Gzip е измерен
локално по файл, не от HTTP server. Няма LCP/CPU/memory/offline измерване.

Съществуващ build warning: `dynamic-http.ts` е едновременно static/dynamic import
и няма да стане отделен chunk. Не блокира build.

**8 test files / 37 tests passed**, Vitest 3.2.7, 23.64 s:

```text
src/utils/theme-extension.test.ts
src/utils/menu-navigation.test.ts
src/utils/header-settings.test.ts
src/router/application-routes.test.ts
src/utils/compiled-ui.test.ts
src/utils/runtime-extensions.test.ts
src/views/DashboardList.component.test.ts
src/components/settings/ThemePackagesSection.test.ts
```

Application routes fixture има fallback fetch warnings; тестовете са успешни.
Full suite, backend security tests и live upgrade/recovery не са изпълнявани за V0.

## 4. Browser baseline

Computer-use проверката използва actual App/Menu/router/theme stores, DashboardList,
Login и Command Palette с временен локален UI fixture. Данните са синтетични;
transport mutations са блокирани. Не са изпълнявани create/delete/device/payment
операции и не е променяна реална инсталация. Fixture не изпълнява целия production
startup/auth lifecycle и не доказва backend authorization или live extension load.

Viewport: desktop 1440×900; mobile 390×844; light/dark; EN/BG; дълги labels.
Локалните screenshots са ignored artifacts, не release assets и не са налични
автоматично в друг checkout:

- [Desktop light](../.runtime/theme-v0-baseline/desktop-light.png)
- [Desktop dark BG](../.runtime/theme-v0-baseline/desktop-dark-bg.png)
- [Mobile light](../.runtime/theme-v0-baseline/mobile-light.png)
- [Mobile dark BG](../.runtime/theme-v0-baseline/mobile-dark-bg.png)
- [Mobile expanded menu](../.runtime/theme-v0-baseline/mobile-dark-menu.png)
- [Create dialog, без submit](../.runtime/theme-v0-baseline/desktop-light-dialog.png)
- [Command Palette](../.runtime/theme-v0-baseline/desktop-light-palette.png)
- [Guest/login](../.runtime/theme-v0-baseline/desktop-light-guest.png)

### Видими проблеми за следващите етапи

- Dark mode: outline actions и private/public badges са с визуално слаб контраст.
  Точни accessibility contrast ratios не са измервани в V0.
- Delete action изглежда като синия Edit outline action; липсва ясна визуална
  danger семантика. Не променяме действието или потвърждението.
- Desktop card actions не се подравняват еднакво при различна дължина на заглавията.
- Mobile menu се побира, но expanded header е много висок и controls са разпокъсани.
  След стабилизиране няма horizontal overflow в проверения 390px fixture.
- Create dialog: checkbox/label layout е неравномерен; initial focus остава върху
  launcher button. Focus trap не е проверен. V2 dialog primitive трябва да го докаже.
- Palette работи с Ctrl+K/Escape и фокусира search input; labels остават EN и при BG.

Devtools control в local screenshots е dev-server artifact, не production UI.
Това са снимки на **сегашния интерфейс**, не приет v2 дизайн.

## 5. Минимална regression матрица

| Сценарий | V0 доказателство | Следващ gate |
| --- | --- | --- |
| Admin / ограничен user / guest menu | Browser fixture + menu unit tests | V3 с реални accounts и router guards |
| Guest protected route | Fixture redirect към Login | Live auth и public/display/kiosk сценарии |
| Kiosk audience | Menu unit tests | V3 browser/live review |
| Light/dark, BG/EN, дълги labels | Desktop/mobile screenshots | Всеки мигриран екран |
| Header content/style precedence | Header unit tests и source audit | V1 adapter + V3 shell |
| V1 selection/fallback/zero radii | Theme/package tests | V1 equivalence и V4 lifecycle |
| Dynamic routes / compiled UI / runtime catalog | Целеви tests | V3/V7 live neutral extension |
| Palette и dialog | Отваряне/затваряне, без submit | V2 keyboard/focus и semantic states |
| Portable recovery / immutable update | Не е проверено в V0 | V8 отделно одобрена live проба |

## 6. Следваща scoped задача

**V1**, не преработка на App/Menu: versioned design contract, token ranges,
semantic variants, shell modes, asset budgets и header override precedence.
После v1 adapter и целеви equivalence/validation tests към съществуващия loader.
Един source of truth, запазени legacy настройки и без SDK/device промяна.
V2/V3 започват след тази граница; визуалните проблеми по-горе не са поправени във V0.
