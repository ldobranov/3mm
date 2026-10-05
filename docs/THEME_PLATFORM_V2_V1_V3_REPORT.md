# Theme Platform v2 — V1, V2, V3 report

Статус: реализирано локално; frontend build/type-check и целеви проверки.
Продължава [V0 baseline](THEME_PLATFORM_V2_BASELINE.md).
Договор: [Design API 2](THEME_DESIGN_API_V2.md).

## Доставен обхват

- V1: strict versioned frontend design parser, bounded values/contrast,
  наследяване, v1 adapter без загуба на legacy palette/radii, затворени tokens,
  изрична header precedence и asset budget за бъдещия V4 loader.
- V2: native Vue Button/Dialog, scoped CSS primitives за forms/cards/status/
  tables, демонстрационна страница с локална validation и безопасни actions.
- V3: opt-in sidebar/top shell, mobile drawer, същите Menu registrations и
  filtering/handlers, i18n, palette, protected preview recovery и stable content
  mount. Legacy shell остава default за съществуващите инсталации.

Не са променяни backend, DB, auth policy, device protocol, SDK 1.3, immutable
deployment или Child Center. Не са инсталирани v2 пакети, правени live операции,
deploy, commit, push, release или version bump.

## Проверки и видими корекции

65 целеви теста в 11 файла: design/legacy compatibility, header/menu,
shell audience/modes/state preservation, actual router guard за admin/user/guest,
dialog/button, preview locale и dynamic runtime/compiled UI/theme picker.
Допълнителната focus проверка е в същия dialog test, не нов full-suite run.
Frontend build и `npm run type-check` са успешни.

Browser review използва реалните App/Menu/router/components с изолирани,
синтетични API fixtures; mutation calls са блокирани. Това не е live проверка
на истински account/device/extension инсталации.

Проверени: 1440×1000 desktop, 390×844 mobile, light/dark, BG/EN, дълги menu
labels, sidebar/top, forms/loading/disabled, native modal validation,
Tab/Shift+Tab containment, Escape/focus restore, palette open/close, saved
header colors, recovery/restore и излизане към legacy shell с началния език/mode.
При 390 px document clientWidth и scrollWidth са 375 px — няма horizontal overflow.

Поправени от визуалната проверка: CSS specificity на desktop hamburger и
language select, cramped mobile branding, Table wrapper scrollbar и explicit
modal Tab wrapping. Mobile branding и controls вече са на отделни редове.

Локални screenshot доказателства (ignored `.runtime`, не package assets):

- `../.runtime/theme-v123-review/desktop-light.png`
- `../.runtime/theme-v123-review/desktop-dark-bg.png`
- `../.runtime/theme-v123-review/desktop-top-dark-bg.png`
- `../.runtime/theme-v123-review/mobile-dark-bg.png`
- `../.runtime/theme-v123-review/mobile-navigation-dark-bg.png`
- `../.runtime/theme-v123-review/mobile-recovery.png`
- `../.runtime/theme-v123-review/dialog-error-dark-bg.png`

Temporary browser tab, viewport override, server и fixture entry files са
премахнати след проверката; screenshots остават локално.

## Build budget

| Chunk | V0 size / gzip | V1–V3 size / gzip |
| --- | --- | --- |
| Main JS | 250.39 / 79.09 kB | 268.05 / 85.26 kB |
| Main CSS | 250.57 / 34.68 kB | 259.62 / 36.43 kB |
| Lazy preview JS | няма | 7.18 / 2.39 kB |
| Lazy preview CSS | няма | 1.07 / 0.46 kB |

Vite: 314 modules, около 4 секунди. Съществуващото mixed static/dynamic import
warning за `dynamic-http` остава; няма нов build error.
Няма нови dependencies, assets или font CDN. Existing Bootstrap Icons не е
преработен; screenshot fixture използва съществуващата icon доставка.

## Следваща граница

Потребителят преглежда shell-а, преди следващ major screen redesign.
После V4 свързва Design API 2 с общия **Extensions** installer/catalog,
bounded assets, immutable selection, lifecycle и recovery. V5 доставя два
различни reference ZIP пакета. Реалните installed extensions, logout/login,
Raspberry/VM upgrade и portable backup/restore остават live gates за V4–V8.

Администраторски preview след локален `npm run dev`: `/settings/ui-preview`.
На Raspberry тази страница няма да съществува до отделно поискана доставка.
