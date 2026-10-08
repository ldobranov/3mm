# Theme Platform v2 — V6 / Extensions

Дата: 2026-10-07. Source baseline: `427f32e` плюс локалните промени.
Статус: **готов локално; одобрен от собственика на 2026-10-07**.
DashboardList вече е одобрен. Това не приключва V6 или Milestone 17.

## Обхват

- Единният upload и каталогът запазват всички досегашни package kinds.
- Cards, badges, version controls и бутони използват общите tokens/варианти,
  без собствена фиксирана цветова палитра. Дълги имена се пренасят; mobile е
  едноколонен, с ясно отделени действия.
- Switch controls имат именуване, keyboard focus и 44×44 px зона за натискане.
- Конфигурацията и uninstall/delete/erase използват споделения native dialog:
  Escape, focus return, Cancel начален фокус при премахване и ясни предупреждения.
- Докато заявка се изпълнява, затварянето не губи текущия target. Грешка при
  премахване се показва и вътре в диалога, не само в неактивния фон.
- Запазени са API endpoints/payloads, dynamic refresh, admin/manage условията,
  изборът за запазване на данни и read-only compiled UI controls. Не е променяна
  backend authorization. Няма backend, SDK или router промяна.

Production промяната е в `frontend/src/views/Extensions.vue` и неговите
component тестове. Няма нов upload, package format или конкретен extension в Core.

## Проверки

- Преди промяната: 12 Extensions теста минаха.
- След промяната: 17 Extensions + 8 DashboardList + 2 UI primitive теста минаха.
- Type-check и `npm run build-only`: успешни, 326 modules.
- Проверени са съществуващите lifecycle payloads, configuration required fields,
  Escape/cancel без mutation, disabled/permission UI, busy dialog guard и
  видимата грешка при неуспешно премахване.
- Изолиран browser review с реалния компонент: Graphite Mint / light / desktop,
  Slate Copper / dark / mobile, BG/EN, дълги текстове, конфигурация и премахване.
  При 390 px няма хоризонтално преливане. Escape връща фокуса на opener бутона;
  първоначалният фокус за премахване е Cancel, за конфигурация — device select.

Browser fixture използва синтетичен каталог; всички mutations са блокирани.
Това не доказва live install/uninstall, ZIP/font delivery, auth или recovery.
Някои съществуващи lifecycle преводи все още използват EN fallback; не са
добавяни hardcoded преводи или именуване на бизнес extensions.

## Локални визуални доказателства

Ignored review artifacts; не се включват в Core release:

- [Desktop / Graphite Mint / light / BG](../.runtime/theme-v6-dashboard/extensions-desktop-graphite-light-bg.png)
- [Mobile / Slate Copper / dark / BG](../.runtime/theme-v6-dashboard/extensions-mobile-copper-dark-bg.png)
- [Uninstall dialog / desktop / BG](../.runtime/theme-v6-dashboard/extensions-delete-desktop-bg.png)
- [Configuration dialog / mobile / dark / BG](../.runtime/theme-v6-dashboard/extensions-config-mobile-dark-bg.png)

## Следващ gate

Extensions е одобрен. V6 / Settings е започнат с navigation и Application/Header
формите, които чакат отделен визуален преглед. Следват останалите Settings controls, Display Editor,
V7 extension UI contract и V8 реално upgrade/recovery приемане. M17 остава отворен.
Няма deploy, commit, push, release или live reset в тази задача.
