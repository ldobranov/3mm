# Theme Platform v2 — V6 / Display Editor

Дата: 2026-10-08. Source baseline: `427f32e` плюс локалните промени.
Статус: **готов локално; одобрен от собственика на 2026-10-08**.
DashboardList, Extensions и двете части на Settings са одобрени.

## Обхват

- Desktop workspace: palette вляво, canvas в средата, properties вдясно.
  При междинна ширина palette е общ горен ред; на mobile секциите са вертикални.
- Общи UI tokens и card/button варианти, без inline theme colors. Наследеното
  глобално центриране на header се отменя само в този екран.
- Native widget selector позволява keyboard/touch избор без drag-and-drop.
  На mobile платното се превърта локално, без да променя grid координатите;
  toolbar бутоните остават видими и с увеличени touch targets.
- Properties вече е dock, не modal. Legacy и compiled editors се зареждат чрез
  същите динамични registrations/resolvers. Не са добавени concrete extensions
  или theme names в Core; съществуващият legacy built-in resolver е запазен.
- Cancel и смяна на widget възстановяват snapshot на оригиналния config.
  Повторен избор на същия widget не заменя този snapshot с незаписания preview.
- Preview timer се изчиства при Cancel/Save/close/switch/unmount; закъснял
  editor response не може да замени редактора на новия избор.
- Save запазва draft при грешка и затваря dock само след успешен PATCH.
  In-flight save блокира cancel/selection и повторно submit. Delete на текущия
  widget затваря dock след успешен DELETE. Mutation errors остават видими.
- Dashboard settings използва shared native dialog, асоциирани labels и form
  submit. Escape/backdrop/cancel и връщането на focus са запазени; текущ save
  не се затваря по невнимание. Enter не записва widget от чужд toolbar/страница.

Production файлове: `DisplayEditor.vue`, `WidgetPalette.vue`, `EditorPanel.vue`.
API endpoints/payloads, router/auth guards и stores са непроменени. GridStack
runtime и public/read-only DisplayCanvas не са редактирани; editor toolbar CSS
е scoped през DisplayEditor. Няма backend, SDK, database или deployment промяна.
Външните widget editors запазват собственото си оформление; не се обещава
автоматична тематизация на hardcoded extension CSS. Новите UI текстове използват
i18n keys с EN fallback, когато езиковият пакет още няма тези преводи.

## Проверки

- 28 целеви frontend теста в 5 файла: DisplayEditor (8), EditorPanel (8),
  WidgetPalette (2), DashboardList (8), shared UI primitives (2).
- Покрити са display/widgets GET, owner-aware preview destination, непроменени
  add/drop/layout/delete/settings payloads, theme variants, empty/load failure,
  local preview/cancel/switch, successful/failed save, pending settings guard,
  late editor response, compiled resolution, scoped keyboard и timer cleanup.
- Type-check и `npm run build-only`: успешни; 325 modules. Full suite остава
  release gate и не е изпълняван за този scoped frontend екран.
- Browser: Graphite/light/1600px/BG, Copper/dark/390px/BG и built-in/light/EN
  с празен каталог. Long title/slug/widget labels, properties selector,
  Preview → Cancel, failed Save, Settings dialog/Escape/focus са проверени.
- На 390px няма хоризонтално преливане на страницата; само canvas е scrollable.
  Mobile заглавието и actions са отделни редове. Focus стига до editor input,
  а Cancel се връща към widget selector; native dialog се връща към Settings.

Изолираният ignored browser fixture използва реалния shell, DisplayEditor,
palette, EditorPanel и GridStack със синтетични API данни и неутрални sample
renderer/editor компоненти. Всички HTTP mutations са блокирани. Failed Save е
предизвикан именно от този отказ; няма запис на live данни. Unit тестовете
проверяват успешните API handlers с mocks. Реално backend persistence,
drag-and-drop/resize на live dashboard, инсталирани бизнес editors, auth и
recovery остават live acceptance; не се подразбират от този review.

## Визуални доказателства

Ignored screenshots; не се включват в Core release:

- [Workspace / Graphite / light / desktop](../.runtime/theme-v6-dashboard/editor-graphite-light-desktop.png)
- [Properties / Copper / dark / mobile](../.runtime/theme-v6-dashboard/editor-copper-dark-mobile.png)
- [Settings dialog / Copper / dark / mobile](../.runtime/theme-v6-dashboard/editor-settings-copper-dark-mobile.png)
- [Failed Save / desktop](../.runtime/theme-v6-dashboard/editor-save-failure-desktop.png)
- [Built-in adapter / empty catalog / desktop](../.runtime/theme-v6-dashboard/editor-builtin-empty-desktop.png)

## Следващ gate

Собственикът одобри Display Editor на 2026-10-08. Следва V7 — публичният
extension UI contract, после V8 upgrade/recovery приемане.
Няма commit, push, release или deploy в тази задача. M17 остава отворен.
