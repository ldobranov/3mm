# Public Extension UI v1

Статус: V7 основа с първа CAP09 част от 2026-10-26, доставена на Raspberry.
Собственикът потвърди успешните ръчни проби с `org.3mm.cap09-ui-check` 1.0.0:
общи полета/форми, таблица и UI състояния. Това затваря избрания ограничен
резултат; останалият CAP09 каталог и други browser/device профили са отделни.
Това е **browser presentation contract**, независим от Application SDK 1.3,
Device Protocol 1.0, `compiled_ui_version: 1` и Theme Design API 2.

Локално допълнение CAP09, 2026-10-29: подготвени са `UiEditorForm`,
`UiRecordPicker` и `UiCollectionEditor` с одобрена Reka UI 2.11.0. Собственикът
изпълни успешно чистите Node 22/pnpm проверки: 780 frontend теста, type-check,
build и по 13 tooling/Python UI теста. Core кандидатът е внедрен на Raspberry;
собственикът потвърди работата на примера, Unconfirmed/Conflict/Resolve, EN/BG,
светъл/тъмен и тесен изглед. Това е приемане на този ограничен редакторски срез,
не на целия CAP09 каталог или на мигрирани бизнес приложения. Точната snapshot
среда и deployment са в WORKING_STATE.

## Публичен вход

### Единен изглед със Settings (CAP09, 2026-10-27)

Settings preview използва същите публични `UiSurface`, `UiButton`, `UiField`,
`UiForm`, `UiTable`, `UiState` и `UiDialog`, които се доставят на приложенията.
Визуалните правила са в общия `ui-platform.css`, включен и в CSS closure на
публичния import-map entry. Компонентите не поддържат втори набор цветове,
отстояния или височини. `--ui-color-scheme` се проектира от ефективната палитра,
включително светъл preview в тъмен Core; не се определя от OS media query.

Полета с help/error текст не разтягат съседните контроли. Едноредовите полета
следват плътността на Core (36/44 px); под 600 px целта за докосване е поне 44 px.
Радиуси, шрифт, цвят на focus и състоянията идват от ефективните theme tokens.
Вложен `UiSurface` използва собствените си component variants, без стил от външен
preview да променя solid/outline или bordered/raised. Таблицата има собствена
scroll област и общи header/cell стилове. `UiField` подава `placeholder` и
`autofocus` на native контрола. Промяна на тема/палитра/варианти не remount-ва
формата и не прави submit/fetch/retry от името на приложението.

Hover цветовете на primary/secondary/danger се извеждат от съответната двойка
фон/текст, без да намаляват нейния контраст. Вторичният бутон не преминава към
фон на панел със запазен бял текст. Outline запазва accent/danger текста, когато
е четим върху surface/surface-alt; иначе използва четим неутрален текст.
Останалите Core бутони със старите aliases използват същите двойки и hover
изчисление. Disabled/loading бутоните не приемат hover цветовете; keyboard focus
остава отделен видим контур. Това е обща frontend поправка от 2026-10-28, без
промяна в Theme Design schema или public UI contract version.

Текущите UI пакети, които използват публичните компоненти, получават общата
поправка с Core frontend обновяването; не е необходимо да се променят техните
immutable ZIP файлове. Собствен layout/CSS на приложение остава негова отговорност.

### Текущ actor и делегирана операция (CAP02)

`await useApplicationHost().access.getInfo()` връща текущата самоличност за
конкретния route: user със стабилен `subject_id`, kiosk terminal или anonymous.
`permission_ids` са human application permissions, отделни от platform admin
и service resource consent. Това е наблюдение, не право за бъдещо изпълнение.
За business ownership използвайте `actor.subject_id`, а не роля или числов ID.

Route може изрично да декларира `delegated_operations`. Публичният browser API е
`host.delegations.create(operationId, payload, requestId, ttlSeconds?)`,
`.lookup(id)` и `.cancel(id)`. Browser не задава инициатор/изпълнител или audience;
Core издава една конкретна операция с кратък срок за worker на същото приложение.
Приложението предава получения ID на собствената си опашка през декларирана
операция. Worker изпълнява след връщането на handler-а; при изгубен отговор чете
резултата, без автоматично повторение. Няма generic HTTP client, bearer grant,
автоматично polling/refresh или превръщане на service account в business admin.

Точните payload/lifetime budgets, native SDK методи, откази и граници са в
[CAP02 договора](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#stable-actor-browser-access-and-finite-operation-delegation).
Това е локално разработеният API; внедряване и ръчна проба на Raspberry следват
само при отделно възложено обновяване.

### Начален и жив език на application route (2026-10-27)

Core подава ефективния си език преди mount като стандартен reactive root prop
`locale: string`. Приложение, което вече приема този prop, не изисква собствен
Core store или езиков selector. Промените patch-ват същия component instance;
не го remount-ват и не изтриват въведена форма, грешка или pending request.
Източникът е същият като на Core header-а, включително preview/fallback режима.

За вложени компоненти или приложения без root prop публичният вход е:

```typescript
import { onBeforeUnmount, ref } from 'vue'
import { useApplicationHost } from '@3mm/application-ui/v1'

const { presentation } = useApplicationHost()
const locale = ref(presentation.getInfo().locale) // синхронно, без HTTP
const unsubscribe = presentation.subscribe(info => { locale.value = info.locale })
onBeforeUnmount(unsubscribe)
```

`presentation.version === 1`; `getInfo()` връща frozen `{ locale: string }`.
`subscribe` известява за бъдещи промени, а initial value се чете с `getInfo()`.
Unsubscribe е идемпотентен; Core прекратява останалите subscriptions при unmount
и задържан host отказва четене/нов subscription с `disposed`. Няма setter,
localStorage, HTTP client, token, Core store или отделен theme source в този API.
`host.getInfo().features.presentation_version` също е `1`. Manifest v2, host v1,
UI contract v1 и native SDK 1.3 запазват независимите си version axes.

Темата продължава да идва от `UiSurface`, публичните `--ui-*` tokens и Core-owned
component variants. Приложението не избира втори theme и не следи OS dark mode.
Текущата инициализация на Core изчаква потребителските настройки преди route mount;
при недостъпни настройки остава използваемият вече инициализиран fallback.

Application текстовете остават собственост на приложението: задължителен пълен
`locales/en.json`, допълнителни каталози по избор. Нормализирайте `_` до `-` и
регистъра, после търсете точния locale, базовия език и EN **за всеки ключ**.
Липсващ EN ключ е authoring error. Каталогът не инсталира глобален Core language
package; сменяйте само видимите текстове, без автоматични fetch/submit операции.
Това е правило за авторите на приложения, не нова проверка на ZIP каталозите.

Този договор е реализиран локално; Raspberry deployment и потребителска проба
на приложенията след обновяване остават отделни действия.

### Connector настройване от Extensions (2026-10-27)

В `/extensions` има settings колелце за версии с декларирани connector-и. Core
показва собствен диалог за адрес, създаване/избор на данни за вход и потвърдената
им смяна/отмяна. Достъпът е за текущ Core администратор; приложението не трябва
да импортира private HTTP/token функции или да прави свой credential editor.

Записът е атомарен за configuration, нов credential и binding. Има snapshot/CAS
и запечатан резултат по request ID; при непотвърден отговор диалогът проверява
първоначалната заявка, без повторен Save. Нов валидиран пакет може да получи
настройки преди native consent: остава спрян и без права. Записът не стартира
код, SQL migration или външна HTTP заявка. След промяна е нужен нов преглед на
достъпа и активиране през съществуващия lifecycle.

Това е **Core-owned вход от Extensions**, реализиран локално без deployment.
Предложеният in-application `administration.connectors` facade и неговите route
allowlist declarations още не са публичен API и не се рекламират като feature.
Те не са нужни за този Core вход. Native SDK connector broker остава начинът за
изрична проба на връзката и business операции след настройването и одобрението.
Виж [пълния договор за настройване](EXTENSION_PLATFORM_V2_PUBLIC_CONTRACTS.md#core-owned-connector-settings-2026-10-27).

### Публични UI компоненти

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
`UiDialog`, `UiField`, `UiForm`, `UiTable`, `UiState`, `UiEditorForm`,
`UiRecordPicker`, `UiCollectionEditor`.
Новите exports са additive в текущия прототип; изискват Core build, който ги
публикува. Не са обещание, че стар UI-v1 host съдържа новите компоненти.
Вътрешни source paths, stores, router, theme loader, injection key,
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
| `UiField` | Задължителни `id`, `label`; `v-model` за draft; `type`: text/email/number/date/datetime-local/checkbox/textarea/select; `description`, `error`, `required`, `disabled`, `readonly`, `maxlength` (1024 default), `step`, `min`, `max`, select `options: {value,label,disabled?}[]`. |
| `UiForm` | `busy` изключва fieldset; default slot; `submit` event само при валидна native форма и без busy. Не извършва заявка. |
| `UiTable` | Задължителни `rows`, `columns: {key,label}[]`, `rowKey(row)`, `caption`, `emptyLabel`; `#cell="{row,column,value}"`; controlled `hasPrevious`/`hasNext`, `previous`/`next` events, `busy` и преводими `previousLabel`/`nextLabel`/`paginationLabel`. |
| `UiState` | Задължителни `kind`: loading/error/empty и `message`; default slot за изрично действие на приложението; role status/alert и loading `aria-busy`. |
| `UiEditorForm` | `title`, `description?`, `dirty`, `busy`, `disabled`, `valid`; `state`: idle/unconfirmed/conflict; `error?`. `save` само от валидна, променена и отключена форма; `cancel` е намерение за отхвърляне на draft. Default slot `{disabled}` и `#recovery` извън заключения fieldset. Преводими `saveLabel`, `cancelLabel`, `dirtyLabel`, `savedLabel`, `unconfirmedLabel`, `conflictLabel`. |
| `UiRecordPicker` | `id`, `label`, `options: {id,label,description?,disabled?}[]`, `v-model`: string/null или string[] с `multiple`; `v-model:search`. `filterMode`: local (default) или external; `selectedOptions` са labels за избрани записи извън текущата страница. `disabled`, `busy`, `description`, `error`, `placeholder`; преводими empty/loading/selected/remove/toggle/unavailable labels. |
| `UiCollectionEditor` | `v-model`: масив от draft записи, `title`, `itemKey(item): string`, `itemLabel(item): string`; default slot `{item,index,disabled}`; `add` и `update:modelValue` намерения. `disabled`, `minItems`, `maxItems`, преводими add/remove/moveUp/moveDown/empty/invalidKeys labels. |

`UiSurface` се поставя около route/widget/editor UI; не сменя shell, menu или
route authorization. Наследява live theme/preview варианти без повторно монтиране
на страницата. Без shell provider използва solid/bordered; цветовете и размерите
продължават да идват от host CSS variables. Не е самостоятелна външна библиотека
без Core styles. Legacy/built-in темите работят чрез съществуващия adapter.

`UiButton` при loading е disabled и има `aria-busy`. UI компонентът не изпраща
API заявки, не решава права и не заменя идемпотентност или backend validation.

`UiField` свързва label/help/error с контрола чрез точния ID, `aria-describedby`
и `aria-invalid`. Използвайте уникален ID при повече от един екземпляр.
Text/number/date/select/textarea връщат string draft, включително празен string;
checkbox връща boolean. Приложението извършва conversion и domain validation
преди invoke. Компонентът не превръща празно числово поле в нула.
`UiForm` използва native HTML validity; това е удобство за човека, не сървърна
проверка или предоставяне на права. Приложението притежава submit/pending ID,
непотвърдения резултат и решението кога може да се изпрати нова mutation.

`UiTable` не избира endpoint, cursor, page size или видими business полета.
Родителят подава разрешените редове, стабилни уникални ключове и следващата
страница. Render, смяна на език/тема и busy не предизвикват fetch или mutation.
Широка таблица има локална, именувана и focusable scroll област; не разширява
родителския layout. Приложението подава преводите и управлява loading/error
чрез `UiState`; текстът се escape-ва, без `v-html`.

CSS closure на публичните import-map ESM entries се включва в prebuilt host
HTML. Директният ESM import не минава през Vite dynamic-import CSS loader;
затова само наличен CSS файл в архива не доказва, че компонентите са стилизирани.
Четирите нови компонента са presentation код с текущите публични CSS tokens,
без нова библиотека, Core store, credentials или скрита HTTP операция.

Първи текущ потребител е optional `libraries/three_mm_crud/frontend/CrudPage.vue`.
Той запазва собствения SDK invoke, permission/result/pending правила и вече
работи без `crypto.randomUUID` на HTTP LAN. Това не променя готовите immutable
Contacts пакети и не публикува нова версия на приложение. Upload, task monitor,
filters и бизнес editors остават извън тази първа CAP09 част.

### Общ редакторски профил (локално подготвен, 2026-10-29)

Редакторът, избраните записи и подреждането променят само draft на приложението.
Няма Core бизнес CRUD engine, schema migration, endpoint, token, автоматично
записване, retry или генериране на mutation ID. Приложението запазва server
validation, проверката на права/ревизия, single-flight busy, request ID и
разрешаването на непотвърден резултат. След `save` задайте busy синхронно преди
асинхронната операция. `cancel` не е отмяна/rollback на вече изпратена операция.
`unconfirmed` и `conflict` заключват формата и двата бутона, без да чистят draft;
само собственикът може да ги разреши чрез изрично read/reconcile в `#recovery`.
Промяна на props, locale или theme не извършва действие.

`UiRecordPicker` използва реален Reka combobox с единичен/множествен избор и
клавиатурна навигация. `search` е отделно от избраните IDs: въвеждането на текст
не избира/изчиства запис, а Enter в полето не записва обкръжаващата форма.
Идентификаторите на options трябва да са уникални непразни string стойности.
При external mode приложението зарежда разрешената страница и управлява busy,
cursor, debounce и отхвърляне на остарели отговори; компонентът няма loader.
`selectedOptions` пази само видими labels за вече избраните IDs, не дава право
да се избере нов запис извън текущите options. Изчезнал от страницата избор не
се изтрива автоматично. При отнет достъп приложението чисти недостъпните данни
и подава disabled; тези визуални контроли не са authority.

`UiCollectionEditor` изисква стабилни string ключове, не array index. Duplicate/
празни ключове блокират редакциите с видима грешка, без да поправят данните.
Move/remove емитват нов масив, без да мутират подадения; `add` и създаването на
нов стабилен ID са отговорност на приложението. Тези събития са за draft, не за
директна физическа/бизнес операция. Подайте slot disabled на вложени контроли.
Няма drag-and-drop-only действие: подреждането има именувани native бутони,
достъпни с клавиатура, и запазва фокуса/идентичността на редактирания елемент.

Reka UI 2.11.0 е вътрешна build зависимост на Core, не нов extension import.
Публичният compiler продължава да отказва `reka-ui`, private subpaths и Core
stores. Компонентите ползват общия host Vue runtime и public theme tokens;
popup-ът остава inline в същия UiSurface/диалог, без teleport в body или CDN.
Няма промяна в manifest/SDK/Core/езиковите версии. Source примерът в
`modules/ui-reference` показва избор на записи и подредени панели с общите
компоненти; съществуващи immutable ZIP файлове не се променят.

`UiDialog` трябва да остане **вътре в UiSurface**, без teleport извън него.
Има inert background, Tab/Shift+Tab containment, Escape/close request и връщане
на focus към launcher. Не извършва потвърждение/изтриване вместо extension-а.
Поставете `autofocus` върху безопасния Cancel control при опасни операции;
extension-ът остава собственик на pending/cancel policy и защитната фраза.

## CAP01 resource observations in an administrator route

Локално допълнение от 2026-10-27, без deployment. Administrator route може
изрично да декларира `administration_reads: ["resources.inspect"]` и да използва:

```ts
const view = await useApplicationHost().administration.resources.inspect([
  'storage:private_files_read', 'storage:private_files_transform',
])
```

Това е общият [resource report](APPLICATION_COMMANDS.md#installation-resource-observations-cap01-third-slice)
само за собствената активна инсталация, с максимум 16 различни scopes.
Host изпраща текущите source/build hashes; няма URL, чужда инсталация, secret
или instance ID, избирани от приложението. Core проверява текущия administrator,
login, точния reviewed UI artifact и изрично декларирания read преди наблюдението
и отново след него. Отнемане на човешки или service достъп не връща старите
provider данни. Browser host проверява формата, съответствието на scopes/artifact
и отхвърля неочаквани полета; няма автоматично повторение.

Service grant и човешкият UI достъп са отделни. Read-ът не предоставя grant,
не изпълнява операция и не потвърждава човешко право за бъдеща mutation.
`unknown`, `unavailable`, `required` и `not_evaluated` трябва да се показват
отделно. Operator/kiosk resource discovery не е част от този admin профил.
Няма нов екран или запис в менюто; extension-ът избира presentation-а.

В resource rows `required` е boolean: `false` означава авторски декларирана
optional external зависимост. Това не означава предоставен достъп или работещ
provider. Празен optional device selector не се изпраща като невалиден празен
device ID; required selectors и авторската schema остават задължителни.

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

CAP11 добавя `useApplicationHost().files` в `@3mm/application-ui/v1`: bounded
raw upload chunks, resume/status/finalize, metadata, проверено streaming download,
временни връзки и optional image jobs. Browser route трябва изрично да декларира
човешките файлови права; това не предоставя service authority. UI/presentation
major не се променя. [Договор и reference consumer](APPLICATION_FILES.md).

V7 reference ZIP минава през истинския validator/compiler и се зарежда с
действителния hashed public module през съществуващия frontend compiled loader.
Двете themes и legacy adapter използват един и същ compiled artifact.
[Отчет](THEME_PLATFORM_V2_V7_REPORT.md). Live installed-package/upgrade/recovery
приемането е V8; не се подразбира от локални unit/browser проверки.
