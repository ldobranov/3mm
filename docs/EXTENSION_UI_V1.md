# Public Extension UI v1

Статус: V7, реализиран локално; доставка и live приемане са отделни.
Това е **browser presentation contract**, независим от Application SDK 1.3,
Device Protocol 1.0, `compiled_ui_version: 1` и Theme Design API 2.

## Публичен вход

Reviewed compiled UI source използва:

```vue
<script setup>
import { UiSurface, UiButton, UiDialog, UI_CONTRACT_VERSION } from '@3mm/ui/v1'
</script>

<template>
  <UiSurface class="my-extension ui-stack">
    <section class="ui-section ui-stack">
      <h2>My extension</h2>
      <UiButton variant="primary" @click="handleExistingAction">Action</UiButton>
    </section>
  </UiSurface>
</template>
```

`handleExistingAction` е съществуващият handler на extension-а, не действие на UI
библиотеката. Реален самостоятелен пример: [UI Reference](../modules/ui-reference/README.md).

Core frontend build публикува versioned module и hashed chunks. Host import map
свързва `@3mm/ui/v1` с точния hashed ESM asset от този build.
Не записвайте физическия URL/hash в extension source. Installer compiler оставя
`vue` и `@3mm/ui/v1` external; browser зарежда същия host Vue runtime. Няма втори
Vue, Pinia, theme store, CSS framework, CDN или runtime dependency download.

Публичните exports са **само** `UI_CONTRACT_VERSION = 1`, `UiSurface`, `UiButton`,
`UiDialog`. Вътрешни source paths, stores, router, theme loader, injection key,
HTTP clients и permission helpers **не са публичен API**. Не импортвайте
`@/components/...`, `@/stores/...`, `@3mm/ui/v1/context` или package subpaths.
Compiler allowlist допуска точно `@3mm/ui/v1`, не произволен `@3mm/*` namespace.

Използвайте този договор върху Core build, който действително го публикува.
Старите releases без него не могат да заредят новите imports; няма автоматична
миграция или фалшив fallback към друг SDK. За локално end-to-end приемане се
използва **prebuilt frontend** и действителният install-time compiler, не само
директен import на Vue source в Vite dev server. Минималният manifest-v2 Core
version range не различава beta revisions; версията на UI entry е отделната граница.

## Компоненти

| Export | Поддържан интерфейс |
| --- | --- |
| `UiSurface` | Един `div` с default slot и forwarded attrs/classes. Включва `.ui-v2` и наследява актуалните host button/card варианти. |
| `UiButton` | `variant`: primary, secondary (default), danger, quiet; `type`: button (default), submit, reset; `disabled`, `loading`; default slot и forwarded native attrs/listeners. |
| `UiDialog` | `v-model:open`, задължителни `title` и `close-label`; default content и `#actions` slots; labelled native modal. |

`UiSurface` се поставя около route/widget/editor UI; не сменя shell, menu или
route authorization. Наследява live theme/preview варианти без повторно монтиране
на страницата. Без shell provider използва solid/bordered; цветовете и размерите
продължават да идват от host CSS variables. Не е самостоятелна външна библиотека
без Core styles. Legacy/built-in темите работят чрез съществуващия adapter.

`UiButton` при loading е disabled и има `aria-busy`. UI компонентът не изпраща
API заявки, не решава права и не заменя идемпотентност или backend validation.

`UiDialog` трябва да остане **вътре в UiSurface**, без teleport извън него.
Има inert background, Tab/Shift+Tab containment, Escape/close request и връщане
на focus към launcher. Не извършва потвърждение/изтриване вместо extension-а.
Поставете `autofocus` върху безопасния Cancel control при опасни операции;
extension-ът остава собственик на pending/cancel policy и защитната фраза.

## Native classes v1

Вътре в `UiSurface` използвайте същите Core-owned primitives:

- `.ui-stack`, `.ui-row`: grid stack и wrapping action row;
- `.ui-section`: semantic surface, border/radius и host card variant;
- `.ui-field`: label wrapper; първият `span` е label;
- `.ui-control`: native input/select/textarea; `.ui-check`: label + checkbox;
- `.ui-help`, `.ui-error`, `.ui-muted`: помощ, грешка и вторичен текст;
- `.ui-badge`, `.ui-badge--success`, `.ui-badge--warning`: текстови статуси;
- `.ui-table-wrap`, `.ui-table`: локално scrollable semantic table.

Controls запазват native model/events. Формата предоставя labels, validation,
`aria-invalid`, `aria-describedby`, required и error/status text. Статусът не
трябва да разчита само на цвят. Mobile controls са минимум 44 px, focus е видим,
а reduced-motion се управлява от host styles.

Не копирайте CSS реализациите на `.ui-*`; Core ги притежава. Extension stylesheet
е scoped и namespace-нат за собственото layout съдържание. Например responsive
columns с `minmax(0, 1fr)` и gap чрез tokens. Не override-вайте `html`, `body`,
`.ui-shell`, Core menu/dialog selectors или theme variables глобално.

## Read-only CSS tokens v1

| Роля | Tokens |
| --- | --- |
| Surfaces | `--ui-canvas`, `--ui-content`, `--ui-surface`, `--ui-surface-alt`, `--ui-border` |
| Text | `--ui-text`, `--ui-text-secondary`, `--ui-text-muted` |
| Actions | `--ui-accent`, `--ui-accent-text`, `--ui-secondary`, `--ui-secondary-text`, `--ui-danger`, `--ui-danger-text` |
| States | `--ui-success`, `--ui-warning`, `--ui-focus` |
| Type/scale | `--ui-font`, `--ui-font-size`, `--ui-line-height`, `--ui-space`, `--ui-radius-sm`, `--ui-radius-md`, `--ui-radius-lg`, `--ui-control-height` |

Host притежава стойностите, font/assets, light/dark, cleanup и preview precedence.
Extension-ът ги **чете** чрез CSS, не записва нов global theme, не извлича друга
конфигурация и не създава собствен registry. Layout/shell/internal aliases извън
този списък не са v1 extension API. Не hardcode-вайте име/ID на текущата тема.

## Съвместимост и trust boundary

Съществуващите Vue-only compiled пакети, artifact paths, catalog/route guards и
package hashes не се променят или прекомпилират от V7. Legacy CSS продължава да
работи, но hardcoded цветовете не стават автоматично theme-aware. UI migration
се прави поотделно в съответния extension, без промяна на business handlers.

Новите exports и backward-compatible разширения остават под v1. Премахване или
несъвместима промяна на описания интерфейс изисква нов публичен UI major, който
не подменя мълчаливо imports на старите пакети. Нов UI version не означава нов
Application SDK или Device Protocol version.

Compiled UI е **reviewed executable application code**, не security sandbox.
Import allowlist и този supported styling contract не могат да направят
произволен JavaScript/CSS безопасен. Theme ZIP остава отделният декларативен
договор без executable CSS/JS. UI primitive не предоставя/отменя permissions;
реалните операции продължават през съществуващата Core/backend граница.

## Проверки и следващ gate

V7 reference ZIP минава през истинския validator/compiler и се зарежда с
действителния hashed public module през съществуващия frontend compiled loader.
Двете themes и legacy adapter използват един и същ compiled artifact.
[Отчет](THEME_PLATFORM_V2_V7_REPORT.md). Live installed-package/upgrade/recovery
приемането е V8; не се подразбира от локални unit/browser проверки.
