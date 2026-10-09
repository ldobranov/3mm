# Milestone 20 — ограничен WP0

Дата: 2026-10-08. Статус: ограничен преглед и целеви baseline проверки са
изпълнени. След този audit собственикът одобри първата read-only реализация;
тя е описана отделно в [Package Inspection](EXTENSION_PLATFORM_V2_PACKAGE_INSPECTION.md).
Този документ запазва audit baseline-а. Не е пълно WP0 security/live приемане
и не разрешава целия WP1 автоматично.

## Обхват и отправна точка

- Core `v0.3.0-beta.43`, commit `4415cee2c108f66838bde9cae9dcf94cfa5642a8`.
  Успешните release/CI проверки са baseline, не доказателство за untrusted isolation.
- Общ слой за Standalone, local Agent, Hub/Fleet и application extensions.
  Fleet и облакът не са предпоставка.
- Само source audit, съществуващи изолирани тестове и документация. Без runtime,
  API, schema, dependency, package, live данни, deploy, commit/push или release промени.
- Запазваме manifest v2; application/runtime/compiled UI descriptors v1;
  theme/design API v1/v2; Application SDK 1.3 с поддръжка на 1.0–1.3;
  публичен browser UI `@3mm/ui/v1`. Това са независими версии.
- Чуждите незаписани планове и приключването на M17 се запазват. AI Generator
  планът не е преглеждан/реализиран като част от този ограничен WP0.

## Карта: използваме / допълваме / липсва / отлагаме

| Област | Извод и source/test доказателство | Собственик / действие |
| --- | --- | --- |
| ZIP, identity, versions | **Използваме** [validator](../backend/services/module_packages.py), [manifest v2](../three_mm_protocol/module_manifest.py), [catalog API](../backend/routes/modules.py) и `ModulePackage` unique ID/version/hash. `test_module_packages.py` покрива compatibility, traversal, duplicate paths, type identity и permissions. | Core / WP1: adapter, не нов registry/validator. |
| Преглед преди upload | **Липсва в проверения module-v2 API** немутативен inspect response. `POST /packages` записва ZIP, компилира compiled UI и записва каталог; `GET /packages` връща вече качени пакети. Activation е отделна, но upload не е inspection. | Core / WP1: първата предложена малка стъпка по-долу. |
| Application lifecycle | **Използваме** [activation](../three_mm_runtime/application_activation.py): exact digest, configuration, SQLite snapshot, health и rollback; uninstall пази data, erase е отделно. Шест activation теста минаха. | Core/runtime / WP3: разширяваме само доказани липси. SQLite rollback не доказва rollback на всички файлове/външни ефекти. |
| Agent lifecycle | **Използваме отделния adapter** [module runtime](../agent/module_runtime.py): digest/runtime/architecture/permission checks, staging и persistent state. Три целеви install/failure/integrity теста минаха. | Agent / WP3: не уеднаквяваме runtime implementations и не твърдим arbitrary-code sandbox. |
| SDK и Device Platform | **Използваме** [SDK](../three_mm_application_sdk/__init__.py) и [единния capability query](../backend/services/device_capability_registry.py). Тестовете за provider без ModulePackage/Fleet и application binding към module/native/firmware минаха. | Core/SDK / WP4: без втори GPIO/Fleet API, re-pair или SDK 2. |
| UI, themes, languages | **Използваме**, не изграждаме повторно: [public UI](EXTENSION_UI_V1.md), compiled/runtime validators и декларативни theme v1/v2. Езиците все още имат legacy contract/path, а не ModuleManifestV2 adapter. | Core / WP1/WP4: normalize projections, запазваме payloads. Language lifecycle/adapter изисква отделна проверка. |
| Права и upgrade review | **Допълваме**: manifest permissions са allowlisted и съгласувани с descriptor; application activation е admin-only. Това не е общ approval план с exact artifact + промяна на target/connector/runtime права. | Core / WP4/WP5: scoped grant diff и drift/revocation gates преди изпълнимо distribution. |
| Publisher trust / dependencies | **Липсва в module-v2 потока** publisher namespace/key/signature договор и общ pinned dependency graph/plan. Manifest има `dependencies/conflicts`; проверените module install paths не ги решават като граф. Legacy има собствени dependency helpers — не е общият v2 resolver. | Core / WP1/WP2/WP3: отделни договори. SHA-256/HMAC RPC/Node OTA подписи не доказват package publisher trust. |
| Untrusted isolation | **Допълваме преди untrusted delivery**: supervised runtime има systemd hardening, но всички instances са `3mm-app`; compiled UI споделя Core origin/runtime; legacy backend може да бъде import-нат в Core. | Core / WP5: доказана cross-instance/backend/browser граница; не приемаме sandbox от име или процес. |
| Registry, лицензиране, ESP | **Отлагаме**: remote package sources след isolation/recovery; entitlements след безплатния локален flow; storefront/AI UI/firmware са отделни consumers. | Core / WP2/WP6; конкретните extension проекти отделно. |

## Кратък threat model и граници

1. **Inspection/build:** архивът е недоверен input. Съществуващият validator
   има bounded package/member/expanded sizes и path/type checks. Бъдещото inspect
   не компилира, не извлича в persistent storage, не import-ва и не изпълнява migrations.
2. **Backend между extensions:** [systemd template](../deployment/systemd/3mm-application-extension@.service)
   използва общ UID/GID. Activation създава group-readable keys `0640` и directories
   `0750`; host sockets са group-accessible `0660`. Това е конкретен риск за чужди
   files/credentials/sockets, не доказана взаимна изолация. `ProtectSystem=strict`
   и per-instance writable paths не скриват чуждите четими ресурси. Не е правена
   злонамерена/live проба; WP5 трябва да докаже два изолирани instances и граница
   към Core, включително impersonation/revocation, преди недоверени услуги.
3. **Browser:** `@3mm/ui/v1` излага presentation primitives, не Core stores;
   това не ограничава произволния JS. Compiled Vue е reviewed native integration,
   не third-party sandbox. Изолиран origin/bridge и негативни тестове са отделен gate.
4. **Legacy path:** [upload](../backend/routes/extension_routes.py) използва
   `require_user`, не module-v2 `require_admin`; при `backend_entry` извиква
   [manager](../backend/utils/extension_manager.py), който използва `exec_module`
   в Core процеса. Security hooks/dummy fallbacks не доказват външна изолация.
   Новият inspector/registry не трябва да fallback-ва към този път. Преди ново
   изпълнимо distribution е нужна отделна authorization/execution проверка и
   opt-in compatibility policy за legacy code; запазването на езиковите пакети
   не означава разрешение за произволен legacy backend. Тук няма auth промяна.
5. **Recovery/supply chain:** checksum не е авторство; service health не доказва
   липса на side effects. Нови artifact/grant plans изискват одобрение и revalidation.
   Rollback не повтаря неясно плащане или физическо действие. Реалните
   backup/restore/restart и междинно прекъсване остават отделни live gates.

## Първа предложена реализация — read-only Package Inspection

Само adapter/projection върху `validate_module_package`, **не** нов installer.
Първи обхват: съществуващите manifest-v2 Agent/runtime/compiled UI/application/theme
пакети; legacy language/backend форматът се отчита като unsupported by this inspector,
без автоматична конверсия, изпълнение или пренасочване към legacy upload.

- Admin-only bounded inspect операция; точният endpoint/schema се приема преди код.
- Показва exact ID/version/SHA-256, type/runtime, декларирана compatibility,
  permissions, consumed/provided capabilities и конфигурационни изисквания.
- Съпоставя с каталога: нов пакет, вече наличен exact artifact или immutable-version
  conflict. Compatibility се отчита само за проверения Core/изрично избран target;
  неизвестното остава **непроверено**, не „готово за инсталиране“.
- Dependencies/conflicts са **declared / unresolved**, не resolved plan. Publisher/
  signature/trust е **unverified**, не trusted заради filename, ID или hash.
- Без DB/catalog записи, persistent package/artifact files, compiler/subprocess,
  activation, downloads, migrations, права или mutation API промени. Inspection
  не е approval и не гарантира, че по-късната инсталация ще успее.
- Целеви проверки: malformed/oversized/unsafe ZIP; supported descriptors;
  invalid identity/permissions; admin vs user/guest/revoked; повторен inspect;
  immutable conflict; compiler/helper/DB/filesystem write sentinel tests.
- Старите upload/activation endpoints и SDK 1.3 се запазват. Това не разрешава
  remote или untrusted изпълнение и не отлага WP5 зад тях.

## Проверки и останало

На този baseline **35 tests passed, 12 warnings**, 9.85 s, в изолиран WSL/Linux:

```text
backend/tests/test_module_packages.py
three_mm_runtime/tests/test_application_activation.py
agent/tests/test_module_runtime.py — първите три lifecycle/integrity tests
backend/tests/test_device_capability_providers.py — provider без packages/Fleet
backend/tests/test_application_command_providers.py
three_mm_application_sdk/tests/test_identity_and_compatibility.py
```

Не са повторени full suite, browser review или live update/reset. Не са
изпълнени malicious packages срещу работещ Core. Theme/language lifecycle,
all-type restore и пълният cross-instance threat model не са повторно доказани
с тези 35 теста. Съществуващи fixtures за следващите малки задачи:
`modules/application-reference`, `modules/mock-gpio`, `modules/runtime-contacts`,
`modules/compiled-clock`, `modules/ui-reference`; themes — тестовите builders в
`test_theme_extension_packages.py`/`test_theme_extension_v2.py`; languages —
съществуващият legacy language manifest, не нов универсален v2 fixture.

Последващо решение: одобрена е отделната scoped реализация на read-only inspector.
След нея остават owner review и решение за следващия договор. Пълно WP0/WP5
приемане не се маркира автоматично; горните 35 теста са само audit baseline.
