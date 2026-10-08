# 3mm Theme Platform v2 — цялостни визуални теми

Обновен: 2026-10-08. Статус: V0–V4 са публикувани; работещата основа,
включително персоналните цветове на темите, е в beta.40. V5 е изпълнен и проверен
локално с два действителни ZIP пакета и лицензиран шрифт с кирилица и е одобрен
от собственика. Допълненията за idle tab и общ редактор са проверени локално;
подготвени за beta.41, при успешен release workflow. Deploy остава отделен.
V6 / DashboardList е одобрен от собственика на 2026-10-07.
V6 / Extensions е одобрен от собственика на 2026-10-07.
V6 / Settings: navigation, общи cards и Application/Header формите са одобрени.
Останалите вътрешни форми са одобрени с продължението на собственика на 2026-10-08.
V6 / Display Editor е одобрен от собственика на 2026-10-08; V6 е приет локално.
V7 е изпълнен локално и одобрен за доставка на 2026-10-08. V6/V7 се подготвят
за beta.43; публикацията се допуска само след успешен release workflow. V8 остава отворен; пълно
live/recovery приемане не се подразбира от успешен release.
Обхват: продължение на Milestone 17, не нов device/extension subsystem.
Свързани: [продуктов план](MASTER_PLAN.md), [доставка T0–T6](THEME_EXTENSION_PLAN.md),
[действащ договор v1](THEME_EXTENSION_V1.md).

## 1. Цел и отправна точка

Да инсталираме визуално различни теми през **Extensions**, без нов build на Core
за всяка съвместима тема. Разликите да включват не само цветове, а типография,
компоненти, плътност, навигационен layout и локални визуални ресурси.

В `v0.3.0-beta.36` вече са публикувани T0–T3: декларативен theme v1 пакет,
общ upload/catalog, lifecycle, избор в Settings и безопасно прилагане на tokens.
V1 има 11 цвята и 3 радиуса; не предоставя CSS, assets или layout.
Локалният Graphite Mint v1 е reference палитра, не цялостен нов интерфейс.
Тази основа се надгражда, а не се заменя с втори installer или registry.

Голямата промяна е в **Core frontend / общия UI слой**. Backend се променя само
за доказано необходимите v2 validation, assets и recovery договори. Device
protocol, Agent, бизнес логика и Application SDK 1.3 не се променят по подразбиране.

Работи локално, без облак, в Standalone, Hub и централна инсталация.
Fleet и CME са consumers, не специални случаи в Theme API.

## 2. Граница: поведение срещу оформление

| Слой | Притежава | Не може да променя |
| --- | --- | --- |
| Core/domain | Права, маршрути, меню данни, действия, lifecycle и настройки | Конкретна тема по име |
| Core UI Platform | Проверени Vue компоненти, shell layouts, tokens и достъпност | Бизнес правила на extensions |
| Theme extension | Декларативни tokens, варианти, layout избор и разрешени assets | Auth, router, handlers, API, capabilities или потвърждения |
| Application extension | Собствените страници и поведение, чрез общия UI договор | Вътрешни Core компоненти и чужди права |

Тема избира и настройва **предварително реализирани от Core** layout primitives.
Не предоставя произволен HTML/Vue template, JavaScript или CSS stylesheet.
Това е цялостна визуална тема в рамките на версията на UI договора, не свободна
подмяна на цялото приложение. Нов съвместим дизайн не изисква Core промяна;
нова универсална layout възможност може да изисква следваща версия на договора.

Core продължава да решава кои менюта и действия са достъпни. Темата не задава
маршрути, не премахва защитни потвърждения и не превръща забранено действие в
разрешено. Command Palette, i18n и dynamic registrations остават функционални.

## 3. Какво ще описва v2

### Design tokens и компоненти

- semantic surfaces, текст, accent, border, focus, disabled и status states;
- typography: локален font избор, скала за размер/тежест/line-height и fallbacks;
- spacing, compact/comfortable density, контролирани размери на controls;
- радиуси, сенки, разделители и варианти на карти, бутони, форми и таблици;
- отделни light/dark стойности и безопасни default стойности за липсващи tokens.

Shared компоненти: button, input, select, textarea, card/section, dialog,
status badge и table wrapper. Запазват текущите събития, validation и loading/
disabled състояния; формите не се пренаписват като част от стилизирането.
Критичните състояния не се разчитат само по цвят. Focus, четимост, touch targets
и `prefers-reduced-motion` са част от Core UI договора.

### Application Shell

- основен desktop вариант: sidebar + content + компактни top controls;
- поддържан алтернативен вариант: top navigation;
- mobile: Core-owned drawer, четими controls и responsive content;
- slots за branding, разрешена navigation, page title/actions и content;
- контролирани content width, density и contextual panel настройки.

Slot означава позиция за **Core-owned съдържание**, не код от пакета.
Login, public, kiosk и fullscreen display имат изрични shell режими; sidebar
не се налага върху тях. Отделният Setup portal и минималният Node UI не се
преработват автоматично с този milestone.

### Assets

Първа версия: локални WOFF2 fonts и PNG/WebP изображения за декларирани роли,
например theme branding defaults. Няма remote fonts/CDN, HTML, raw SVG, scripts
или произволни CSS `url()` стойности. Съществуващият Bootstrap Icons остава;
нова изпълнима icon система не е необходима.

Пакетът декларира assets и hashes. Validation проверява canonical paths,
allowlisted типове, структура, размери и общ decompression budget; отказва
traversal, symlinks, дублирани members и недекларирани файлове. Публикуваните
ресурси идват само от управлявания immutable artifact store, не от произволни
файлове на устройството. Fonts имат license metadata и кирилица или четим fallback.
Точните числови лимити се фиксират във V1 преди реализацията на asset loader.

## 4. Съвместимост и собственици на настройките

- Theme/design API има собствена версия; не се смесва с device protocol или SDK.
- V1 пакети и старите персонализирани цветове продължават да работят.
- V2 е отделно валидиран contract variant; неподдържани версии/fields се отказват.
- Избраният пакет е точна version/hash, installation-wide; locale и browser
  light/dark preference остават независими. Няма logout при смяна на тема.
- Темата не заменя текстове/преводи, menu items, menu visibility или branding
  съдържание от Header/Menu Customization.
- Запазените header/menu цветове не се изтриват. За v2 администраторът изрично
  избира theme styling или съществуващите overrides; липсващ избор не променя
  наследеното поведение. Precedence се специфицира и тества във V1.
- Font/asset failure използва безопасен fallback; не оставя невидим интерфейс.

Bootstrap остава временно за legacy екрани. Новият UI слой е native Vue + CSS:
общи tokens и reusable classes; scoped CSS само за специфичен layout.
Няма Tailwind, нов component framework или пълно CSS пренаписване наведнъж.

V1 theme избиране запазва legacy layout при първото внедряване на v2. Новият shell
се включва изрично за v2/built-in v2 preview, докато бъде приет. Не сменяме всички
инсталации визуално само защото са получили Core update.

## 5. Install, preview, apply и recovery

Един поток: **Extensions → Upload ZIP → validate/enable → Settings → preview/select**.
Няма нов upload екран, theme compiler, Agent installation или backend service.
Enable на нова версия не сменя автоматично активната тема.

Preview е временен browser context с cancel/cleanup; не записва глобалния избор.
Първата preview среда използва ясно обозначени fixtures за реалните UI компоненти,
без истински device/payment операции. Тя не се представя за live acceptance.
Apply минава през съществуващата admin authorization граница и избира точния пакет.
Останалите браузъри обновяват appearance по общия loader, без auth refresh/logout.

Core гарантира независим built-in recovery вид на theme picker/recovery entry:
несъвместима, премахната или повредена тема не може да блокира връщането към него.
Точният recovery entry и диагностиката се проектират във V3/V4; това не е обход на
правата. Public appearance разкрива само безопасен дизайн и asset references,
не catalog errors, storage paths, настройки или credentials.

При смяна/cancel се изчистват theme classes, variables и font registrations,
без натрупване на стар CSS или превръщане на preview в постоянна настройка.
Backup/portable restore включва избрания immutable пакет и assets. Липсваща или
неподдържана версия след restore води до built-in fallback и видима диагностика,
без промяна на users, devices, credentials или extension данни.

## 6. Етапи и конкретно приемане

V0–V4 са **публикувани**; собственикът потвърди работещите теми и корекции на
логото до beta.40. V5 и V6 са изпълнени локално и одобрени; чакат доставка.
V7 е одобрен за доставка с beta.43; V8 остава отворен. Локален visual review и успешно публикуване не заменят пълното
live/recovery приемане. T0–T3 остават
историческата v1 доставка. [Baseline и карта на зависимостите](THEME_PLATFORM_V2_BASELINE.md).
[Договор V1–V3](THEME_DESIGN_API_V2.md), [отчет](THEME_PLATFORM_V2_V1_V3_REPORT.md).

### V0 — Baseline и карта на зависимостите

Преглед на App, Menu, theme/settings stores, global CSS, router и SDK UI boundary.
Описваме hardcoded styles, Bootstrap зависимости и собствениците на overrides.
Записваме текущи screenshots и размер/build/asset baseline; съставяме кратки
regression сценарии за navigation, роли, locale, palette и extensions.

Резултат: карта на засегнатите файлове, baseline и одобрена граница. Без redesign.

Изпълнено на 2026-10-05: source audit, desktop/mobile screenshots в изолиран
fixture, успешен frontend build и 37 целеви теста. Няма промяна на production код
или live данни. Fixture review не заменя реалните auth/extension/recovery проверки.

### V1 — Версиониран UI/Theme договор

Фиксираме schema, token names/ranges, component variants, shell modes, precedence,
asset limits, compatibility и migration policy. Създаваме v1 adapter към новите
tokens без загуба на старите стойности. Запазваме една система, не два theme stores.

Приемане: v1 fixture дава същите ефективни стойности; неизвестни/опасни стойности
се отказват. Spec не обещава layout или asset, който renderer-ът няма да поддържа.

Локално изпълнено: Design API 2 parser/closed tokens, наследяване и v1 adapter,
контраст/ranges, header precedence и резервиран asset budget. ZIP envelope,
fonts/images и persisted v2 selection не се приемат до V4.

### V2 — Shared UI primitives

Добавяме общите classes/компоненти на малки групи и един демонстрационен екран.
Проверяваме форми, keyboard/focus, loading/error/disabled, дълги етикети и modals
в двата режима. Не мигрираме всички страници в този етап.

Приемане: компонентите се стилизират чрез договора, без inline overrides и без
промяна на действията/validation. Frontend build и целевите проверки минават.

Локално изпълнено: native Button/Dialog, scoped forms/cards/status/table classes
и admin-only `/settings/ui-preview`. Проверени validation, loading/disabled,
light/dark, BG/EN и keyboard focus; не са мигрирани всички екрани.

### V3 — Application Shell

App.vue, Menu.vue и необходимите общи styles/composables. Въвеждаме sidebar/
top-navigation renderer с mobile drawer и protected recovery entry. Използваме
същите menu registrations, permissions, localization и router destinations.

Приемане: admin, ограничен user и guest виждат правилната navigation; extension
routes, login/logout, Command Palette и display/public режими работят. Desktop
и mobile visual review преди следващ голям екран.

Локално изпълнено: sidebar/top/mobile drawer, един Menu registry, stable content
mount, generic shell modes и protected preview recovery. 65 целеви проверки и
изолиран browser review минават. Preview не променя installed theme; legacy shell
остава default. Реален logout/login и installed-extension acceptance са още live gates.

### V4 — V2 пакети, assets и lifecycle

Разширяваме общия validator, catalog projection и browser loader. Ако persistence
изисква промяна — additive Alembic migration и migration/restore тестове.
Не добавяме schema само за удобство и не въвеждаме конкретни theme имена в Core.

Приемане: v1/v2 coexistence; bounded safe assets; immutable versions; select,
disable/delete, rollback и corruption fallback. Admin/non-admin/public boundary
остава проверена. Deployment architecture не се преработва.

Локално изпълнено: общ Extensions installer/lifecycle за v1/v2, strict v2 договор,
shared defaults, assets с hashes/limits/container checks, selected-only serving,
frontend loader/fallback/cleanup и permanent built-in recovery. Без DB migration
или нови native dependencies. Font/WebP container validation не е пълен codec
sanitizer; последното decode е в browser.
[Package договор](THEME_EXTENSION_V2.md), [отчет V4](THEME_PLATFORM_V2_V4_REPORT.md).
Portable export/import/restore е проверен локално; live Raspberry acceptance е V8.

### V5 — Цялостна reference theme и preview

Graphite Mint v2 може да е първият отделен пакет; v1 остава наличен и непроменен.
Втори малък reference пакет доказва различен shell/component вариант и density,
не само друга палитра. И двата се инсталират върху един и същ Core build.

Приемане: upload през Extensions → preview → cancel/apply → reload → light/dark
→ BG/EN. Новата theme версия не редактира Core, не изисква compiler и не сменя
sessions. Изолираното preview и реалната app проверка са отделни доказателства.

Първа част изпълнена локално на 2026-10-05:
Graphite Mint 2.0 — отделен локален v2 ZIP, извън Core commit/release по
решение на собственика; качва се отделно през Extensions. Има
sidebar/compact/raised варианти и две локални PNG марки, без промени по Core.
Четири package проверки и fixture browser review в light/dark/BG/mobile минават;
v1 остава непроменен.

Втора част изпълнена локално на 2026-10-07: Settings → Theme Customization има
**Преглед на тема**, **Отказ** и съществуващото **Приложи тема**. Прегледът зарежда
точния enabled пакет, неговите настройки, шрифт и изображения в временен browser
context. Няма промяна на глобалния избор, ZIP или одита до Apply. Cancel, напускане
на секцията и неуспешно зареждане освобождават временните assets и връщат текущия
изглед/предишния светъл или тъмен режим; закъснели отговори не възстановяват preview.
Palette редакторът е скрит през този preview, за да не записва чуждия пакет.

Неактивните assets са достъпни само през новите admin-only preview GET endpoints;
публичното обслужване остава selected-only. Прилагат се същите ZIP/path/hash/type/
size проверки. Няма DB migration, SDK промяна или промяна на public-web runtime.
45 целеви backend проверки и 42 frontend проверки минаха, включително shell и
initial appearance regressions; има managed-path отказ, type-check/build и
изолиран desktop/390px light/dark BG/EN
browser review. Preview/Cancel не записват; Apply прави един изричен selection запис.
Тази реализация не е deployed и няма commit/release в тази задача.

Останалото V5 е изпълнено локално на 2026-10-07: **Slate Copper 2.0.0** е втори
отделен ZIP — top navigation, comfortable density, outline buttons, bordered
cards и локален variable WOFF2 шрифт. Slate Reference Sans е производен на
лицензирания Inter: преименуван съгласно OFL, с пълния лиценз в ZIP и font metadata,
проверени 66 български кирилски символа и реално browser decoding. Няма нова
runtime dependency. Поправен е само общият WOFF2 container validator за до три
нулеви байта за 4-byte alignment; произволни допълнителни данни се отказват.

Graphite Mint и Slate Copper са едновременно enabled върху един локален Core.
Действителният Slate ZIP е качен и включен през общия Extensions UI, после
проверен с Preview → Cancel → Apply → reload, BG/EN, desktop и mobile light/dark.
Preview/Cancel оставят избора и theme одита непроменени и освобождават шрифта.
Apply изпраща един selection POST/transaction; съществуващият одит записва
двете променени installations (стар избор false, нов избор true), не една audit
entry. Reload запазва избора и зарежда локалния шрифт.

56 целеви backend проверки минаха (включително 11 нови WOFF2 проверки);
предходните 42 frontend проверки и type-check остават доказателството за preview,
а frontend build е повторен успешно. [Отчет V5](THEME_PLATFORM_V2_V5_REPORT.md)
описва пакетите, font provenance, снимките и границите на изолирания сценарий.
Това е **локално V5 приемане**, не live Raspberry или цялото V8. Конкретните ZIP
пакети остават извън Core; preview и font поправката не са в beta.40.
Собственикът одобри V5 на 2026-10-07. Следват две scoped корекции: при временна
мрежова грешка табът запазва последната валидна тема; Theme Customization обединява
декларативни package options, цветове и живи компонентни примери. Старият preview
bookmark води към общия редактор, а защитеният recovery остава независим.
Подробности: [пакетен договор](THEME_EXTENSION_V2.md).
Тези промени се преглеждат отделно; не започват автоматично DashboardList/V6.
Доставка остава отделно поискана.

### V6 — Екрани, един по един

1. DashboardList: project/dashboard cards и ясна информационна йерархия.
2. Extensions: общ catalog и lifecycle controls за всички package kinds.
3. Settings: navigation, forms и ясни граници на Header/Menu/theme overrides.
4. Display Editor: palette вляво, canvas в средата, properties вдясно;
   mobile режим без загуба на editor функции.

Всеки екран е отделна задача, build и визуално приемане от потребителя. Router,
API и бизнес поведение не се променят без доказана необходимост. Екраните извън
този обхват остават legacy-compatible и се вписват като следващи малки задачи.

На 2026-10-07 **DashboardList е изпълнен локално и одобрен от собственика**.
Картите, статусите и действията използват общите theme
tokens/варианти; Create/Delete използват споделения native dialog. Запазени са
API заявките, ownership проверката и preview/editor destinations. Няма backend,
SDK или router промяна. 8 component теста и 2 UI primitive теста, type-check и
frontend build минаха. Изолиран browser review включва desktop/mobile, light/dark,
BG/EN, дълги текстове, Escape/focus и безопасен начален фокус върху Delete → Cancel.
Проверен е и built-in/legacy adapter. Това не е live auth или recovery приемане.
[Отчет за DashboardList](THEME_PLATFORM_V2_V6_DASHBOARD_REPORT.md).
**Extensions е изпълнен локално и одобрен от собственика на 2026-10-07.** Единният upload,
каталогът, статусите, switches и lifecycle controls използват общи tokens и
component варианти. Конфигурацията и потвържденията използват споделения native
dialog с безопасен Cancel фокус, Escape/focus return и защита на текущата заявка.
Запазени са API payloads, разграничението uninstall/delete/erase, permissions и
read-only compiled UI controls. 17 Extensions теста, 8 DashboardList теста и
2 UI primitive теста, type-check и frontend build минаха. Изолираният browser
review включва desktop/mobile, light/dark, BG/EN и две палитри; не е live lifecycle
или recovery приемане. [Отчет за Extensions](THEME_PLATFORM_V2_V6_EXTENSIONS_REPORT.md).
**Settings — първа част е изпълнена локално и одобрена от собственика.**
Навигацията е компактна desktop секция и именуван native select на mobile;
общите panels, Application и Header формите използват UI tokens/варианти.
Запазени са mounted sections и незаписаните drafts, language bindings,
споделеното лого, API payloads и съществуващите permission условия. Поправен е
white hover фонът на upload зоната на image editor в dark mode. Няма backend,
SDK, router или deployment промяна. 41 целеви frontend теста, type-check и build
минаха; browser review включва desktop/mobile, BG/EN и light/dark, две theme
палитри и built-in adapter. Използван е изолиран fixture, без live writes.
[Отчет за Settings](THEME_PLATFORM_V2_V6_SETTINGS_REPORT.md).
**Settings — останалите форми са изпълнени локално и одобрени на 2026-10-08.**
Menu/Network/Backup/Diagnostics/Device control и built-in color/radius controls
използват semantic tokens, общи controls/actions и responsive подредба. Запазени
са API handlers, native confirm/prompt, menu audience/localization/reorder и
точната reset фраза. Diagnostics има текстови status badges; поправен е оставащ
Bootstrap muted цвят в dark network forms и legacy hex input width.
51 целеви теста в 10 файла, type-check и frontend build минаха. Browser review:
Graphite/light/desktop, Copper/dark/390px/BG, built-in/light/desktop и mobile/EN;
дълги backup IDs се пренасят без хоризонтално преливане. Това е изолиран fixture,
не live backup/recovery проверка. Собственикът продължи към Display Editor след
приемането на тази втора част.

**Display Editor е изпълнен локално и одобрен от собственика на 2026-10-08.** Workspace:
palette / canvas / properties; на тесен екран секциите са последователни,
а платното има собствено хоризонтално превъртане без промяна на grid координатите.
Изборът на widget работи и през native select, без drag-and-drop. Dynamic legacy
и compiled editors продължават да се зареждат през съществуващите resolver-и.
Preview → Cancel и смяна на widget връщат оригиналния config; закъснели editor
responses и preview timers не сменят новия избор. Save затваря панела само след
успех; грешка запазва draft. Settings използва shared native dialog и същия API.
28 целеви теста, type-check и frontend build минаха. Browser review: две theme
палитри, light/dark, BG/EN, desktop/390px, long labels, локален preview/cancel,
failed save и Escape/focus. Няма backend, SDK, router или deployment промяна;
public DisplayCanvas и GridStack алгоритъмът не са променяни. Това не е live
save/layout/drag-and-drop приемане. [Отчет](THEME_PLATFORM_V2_V6_DISPLAY_EDITOR_REPORT.md).

### V7 — UI договор за extensions

Документираме tokens/classes и поддържания начин за reusable UI през публичния
extension boundary. Няма imports от вътрешни Core файлове или глобално CSS
завладяване. SDK export се добавя само ако е необходим и отделно версиониран.

Приемане: неутрален reference application използва същите primitives при двете
теми. Legacy extension с hardcoded CSS продължава да работи, но не се обещава,
че автоматично ще изглежда като новата тема. Миграцията му е задача за неговия чат.

Изпълнено локално на 2026-10-08: публичен browser module `@3mm/ui/v1`
(Surface/Button/Dialog/version), hashed host import map и същият Vue runtime.
Shell предоставя само read-only component variants, не Core stores. Съществуващият
install-time compiler допуска точно този import; няма промяна на catalog,
route/auth/API, database, Device Protocol или Application SDK 1.3.
Неутрален UI-only reference ZIP минава през действителния validator/compiler и
frontend loader. 17 frontend и 9 backend проверки, type-check/build и browser
review с две themes, legacy adapter, mobile, BG/EN и native dialog минават.
Няма автоматична миграция на бизнес extensions или обещание за theme-aware
hardcoded CSS. [Публичен договор](EXTENSION_UI_V1.md),
[отчет V7](THEME_PLATFORM_V2_V7_REPORT.md). Собственикът одобри доставка на 2026-10-08;
live installed-package и upgrade/recovery приемането остават V8.

### V8 — Реално upgrade/recovery приемане и доставка

Една поддържана Raspberry/VM инсталация: beta.36 → нов release → v1/v2 theme
selection → restart → rollback → portable backup/restore. Destructive reset
проба се прави само след отделно одобрение и проверен backup.

Приемане: packages/assets/selection се възстановяват; повредена тема не блокира
Settings; unrelated данни и device trust са запазени. README, package/UI contract,
CHANGELOG и milestone report описват провереното, не предполагаемото.

## 7. Работен ред и бюджет

Ред: **V0 → V1 → V2 → V3 → V4 → V5 → V6/V7 → V8**.
V6 има отделна visual gate за всеки екран; не означава обща задача за четири redesign-а.
По решение на собственика от 2026-10-07 завършваме този theme milestone преди
реализацията на следващия Extension Platform v2 milestone; неговият план остава
подготвен, но не започнат в тази задача.

- Малки diff-ове; без несвързан cleanup или редакция на бизнес extensions.
- При frontend промени: `npm run build-only` и релевантни целеви проверки;
  type-check при промяна на TypeScript договори.
- Authorization и DB промени задължително имат security/migration проверки.
- Visual review: desktop, 390px mobile, light/dark, BG/EN, long labels, forms,
  modal/focus и основните роли; не оценяваме само кода или palette mockup.
- Full suite е release gate, не се повтаря за всяка малка CSS/документационна задача.
- V0 фиксира performance baseline; V1 задава bounded asset/font budgets.
  По-късните етапи сравняват load/layout cost с него, без скрити CDN зависимости.
- Deploy, commit, push, release и destructive live тестове са отделно поискани
  действия. Този план сам по себе си не ги разрешава.

## 8. Финално приемане и извън обхвата

Готово означава: два действително различни визуални пакета върху един Core build;
v1 съвместимост; работещи auth/roles/i18n/dynamic extensions; mobile/light/dark;
безопасен избор, fallback и portable recovery. Нов **съвместим** дизайн изисква
нов theme пакет, не нова Core промяна.

Не започваме arbitrary Vue/CSS/JS themes, drag-and-drop theme builder, marketplace,
marketing pages, нови business/device APIs или цялостна автоматична преработка на
чужди extensions. Ако по-късно се поиска изпълним theme plugin, той изисква
отделен trust/security milestone, не разширяване на декларативния v2 по подразбиране.

V6/V7 са одобрени локално; не започваме автоматично redesign на други екрани.
По заявка на собственика се подготвя beta.43. След successful workflow собственикът
ще обнови устройствата; live upgrade/recovery проверките остават V8.
M17 не се затваря преди V8.
