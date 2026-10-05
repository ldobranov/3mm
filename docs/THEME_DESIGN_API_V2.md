# Theme Design API 2 — UI contract

Статус: реализиран локално UI договор, built-in preview и V4 installed v2 loader.
ZIP envelope/assets са отделно в [Theme extension v2](THEME_EXTENSION_V2.md).
Общият installer/catalog приема v1/v2. Device protocol и SDK 1.3 не се променят.

## Версия, default стойности и validation

Defaults: `three_mm_protocol/theme_design_defaults.json`, общ за backend/browser.
Parser: `frontend/src/utils/ui-design.ts`. Входът е plain JSON object с
`design_api_version: 2`. Неподдържана версия, неизвестни root/nested fields,
неправилен тип или стойност извън диапазона отказват целия дизайн. Последният
валиден preview остава активен. Не се приемат CSS, JS, templates, handlers,
произволни variables, remote URL или `assets` в този договор.

Пропусната група/стойност наследява built-in defaults. `null` наследява default
за отделен color или поле в typography/scale/layout/components; самата група
не може да е `null`. `header_style` приема само `saved` или `theme`.
Числото `0` за radius е реална стойност, не липсваща настройка.

Минимален валиден пример, без installer envelope:

```json
{
  "design_api_version": 2,
  "layout": { "navigation": "top", "density": "comfortable" },
  "components": { "button": "outline", "card": "raised" },
  "header_style": "theme"
}
```

| Група | Полета и разрешени стойности | Default |
| --- | --- | --- |
| `light`, `dark` | Allowlisted semantic colors, само `#RRGGBB` | Built-in palette за съответния режим |
| `typography.font` | `system`, `sans`, `mono` — локални font stacks | `system` |
| `typography.base_size` | Integer 12–18 px | 14 |
| `typography.line_height` | Number 1.35–1.8 | 1.5 |
| `scale.unit` | Integer 2–8 px | 4 |
| `scale.radius_sm/md/lg` | Integer 0–50 px | 6 / 10 / 14 |
| `layout.navigation` | `sidebar`, `top` | `sidebar` |
| `layout.density` | `compact`, `comfortable` | `compact` |
| `layout.content_width` | Integer 960–1800 px, responsive maximum | 1440 |
| `layout.sidebar_width` | Integer 216–320 px | 248 |
| `components.button` | `solid`, `outline` | `solid` |
| `components.card` | `bordered`, `raised` | `bordered` |
| `header_style` | `saved`, `theme` | `saved` |

Цветовете са `canvas`, `content`, `surface`, `surface_alt`, `text`,
`text_secondary`, `text_muted`, `border`, `accent`, `accent_text`, `secondary`,
`secondary_text`, `danger`, `danger_text`, `success`, `warning`, `focus`.

Validation проверява поне 4.5:1 за text/secondary/muted/status/accent/danger върху
четирите surfaces и за foreground/background на action buttons; focus има
минимум 3:1 върху surfaces. Това не е сертификат за пълна WCAG съвместимост на
всяка страница. Layout, labels и семантика също се проверяват отделно.

## Projection и съвместимост

Един settings store притежава installed v1/v2 theme и временния `previewDesign`.
Няма втори theme registry/store. Projection записва затворения набор `--ui-*`
variables, като заменя всички owned values при смяна/clear. Legacy variables
се проектират и от v2 semantic colors; v1 поведението остава.

`adaptLegacyUi` копира ефективните 11 v1 цвята и 3 радиуса точно, включително
zero radii. Legacy palette не минава през новото contrast ограничение, за да
не се отказват работещи стари настройки. Adapter **не включва новия shell**.
V1 пакети, custom colors и legacy layout продължават да работят.

Branding текст/logo и menu labels/visibility принадлежат на съществуващите
Header/Menu настройки. `header_style: saved` използва запазените header colors
за branding блока; `theme` използва surface/text на избрания режим. Никой
вариант не изтрива настройките или не сменя преводите и content colors.

## Core-owned UI primitives и shell

`ui-platform.css` е scoped към `.ui-v2`, не глобална подмяна на Bootstrap:

- `UiButton`: native button, variants primary/secondary/danger/quiet,
  forwarded attrs/actions, loading, disabled, default `type="button"`.
- `.ui-control`, `.ui-field`, `.ui-help`, `.ui-error`: native input/select/
  textarea с видими borders; validation и model принадлежат на формата.
- `.ui-section`, `.ui-stack`, `.ui-row`: cards/sections и layout primitives.
- `.ui-badge`, `.ui-table-wrap`, `.ui-table`: status и responsive таблици;
  status има текст/символ, не само цвят.
- `UiDialog`: labelled native modal, inert background, Tab/Shift+Tab wrapping,
  Escape cancellation и връщане на focus към launcher.

Mobile controls са минимум 44 px; focus е видим; reduced-motion премахва
анимациите. Няма нов component framework.

`ApplicationShell` използва същия `Menu` registry чрез scoped slot. Данните,
audience/route filtering, динамичните registrations, език, logout и palette
handlers не са дублирани. Content parent остава mounted при layout/preview
switch, за да не се губи state на страницата.

Shell modes: `application`, `auth`, `public`, `kiosk`, `display`. `uiShell`
route metadata избира изрично mode; без него се използват generic auth/kiosk
metadata. Само application има sidebar/top navigation. Display няма toolbar.
Това е frontend presentation, не промяна на router authorization.

Desktop предлага sidebar или top navigation; mobile предлага Core-owned drawer
със същите разрешени items. Нови title/action/contextual-panel layouts не са
част от текущия renderer. Няма имена на конкретни extensions в договора.

## Preview и recovery — текущ обхват

Администратор отваря `/settings/ui-preview` след локален frontend build.
Маршрутът не се добавя принудително в Menu Editor. Може да се пробват layout,
density, button/card variants, mode и header precedence. Demo validation не
изпълнява device/application действия и не сменя installed theme selection.

Preview езикът не записва account/browser preference. Preview mode не се
записва като нова browser preference, а ThemeToggle не записва account preference.
На route exit preview се изчиства и началните locale/mode се възстановяват.
Нормалната app initialization и действията извън preview запазват досегашното
си поведение. Preview не е sandbox за произволно browsing по live страници.

`/settings/ui-preview?recovery=1` е също admin-only. Изчиства временния дизайн
и показва статичен четим recovery panel с built-in preview restore. От V4 отделен
бутон **Use built-in permanently** изчиства installed selection през admin API;
Header/Menu/custom colors остават. Live recovery acceptance е V8.

## Assets — V4 пакетен слой, отделен от `design`

До 16 файла / общо 4 MiB; font до 512 KiB, image до 1 MiB и 2048 px за
всяка страна. Типове: WOFF2 и PNG/WebP. V4 налага limits,
path/hash/type/container validation преди serving от immutable
artifact store. Няма raw SVG, CSS, HTML, JS, remote fonts или arbitrary URL.

V4 налага тези limits в validator и browser loader. Декларациите са в envelope
`assets`, не в `design`. Точните профили, font/WebP codec границата, selected-only
serving и portable restore са описани в package договора.
