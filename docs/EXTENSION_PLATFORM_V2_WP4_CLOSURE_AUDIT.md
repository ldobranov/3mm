# M20 — проверка на остатъка за приключване на WP4

Първоначален audit: 2026-10-09; последно обновяване: 2026-10-10. Проверен checkout:
`main`, HEAD `3ce8607`, с наличните локални непубликувани промени. SDK остава
**1.3**. Първоначалната проверка е source-only; последващите targeted тестове
са записани по-долу. Това не е live приемане или приключване на WP4.

## Какво действително е налично

| Област | Налично | Какво още не е доказано/реализирано |
| --- | --- | --- |
| Собствена база | Legacy `ApplicationStorage`; relational декларация/exact grants, bounded engine, signed Core admission/atomic receipts, verified preparation/migrations/recovery и normal host/SDK transport за вече protected prepared DB. | Остават full fresh-install namespace/key setup, prepared-DB upgrade, general backup/rollback/key и partial interrupted-recovery resolution. Generic activation/native/source gates са запазени; normal-host тестът не е public install/upgrade acceptance. Legacy SQLite не е scoped. |
| Собствени файлове | Декларация, точни read/write grants, подписан SDK transport, target-owned executor, лимити, receipts и отказ при revoke/drift. Административният диалог показва точните ресурси. | Визуално приемане на новите карти от собственика и общото live SDK приемане. Файловите лимити не покриват SQLite. |
| Команди и connectors | Installed-only exact-resource review → approve → apply → revoke и проверки при admission. | Не означава разрешение за произволни устройства/мрежови заявки или всички типове приложения. |
| Събития | Scoped device consumption и application publication с journal/receipts. | Publication не предоставя автоматичен cross-application subscription. |
| UI представяне | `@3mm/ui/v1`, публични компоненти/CSS tokens, light/dark и host appearance. | Това не е публичен UI operation/host bridge и не предоставя права. |
| Platform операции | Съществуващият подписан SDK поддържа identity, peers и checkpoints в compatibility mode. | В opted-in режима неподдържаните операции са отказани. Няма scoped review/admission adapter за тях. |
| Providers | Тестове за еднакъв application command binding към Agent module/native/firmware capability. | Не е общият installed-extension acceptance в Standalone и Hub с реалния host/transport/recovery. |
| Потребители и възстановяване | Съществуващи route/audience/permission и recovery проверки. | Не са проведени заедно с неутрален WP4 SDK reference в двата layout-а. |

„Налично“ тук е конкретна реализация или съществуващ тест, а не гаранция за
hostile-code isolation. Reviewed-native приложенията могат да заобикалят Python
helpers; OS/browser isolation и ресурсната защита срещу злонамерен код са **WP5**.

## 1. Relational storage: не изграждаме нова база или ORM

`ApplicationStorage.transaction()` връща връзка само към собствената SQLite база
на host-created context. Това е публичен SDK, не Core SQLAlchemy session.
Съществуващите migrations/outbox и SDK 1.0–1.3 приложения трябва да се запазят.

Реалната липса е одобреният relational storage profile и прилагането му. Преди
runtime промяна трябва да се фиксират:

- Собственик: Core/application installation/incarnation + точен artifact.
- Отделни DB read/write права и точни граници; без наследяване от file grant.
- Как се проверяват current grant, revoke, configuration/key/recovery drift при
  транзакция; не е достатъчна проверка само при стартиране на service.
- Отделен lifecycle режим за migration/health/export/recovery. Първото adoption
  не трябва да изисква предварително live право, за да стартира health check.
- Как се броят/ограничават SQLite, WAL/SHM, transaction/staging bytes и lock waits.
  Cooperative SDK bounds не се обявяват за OS quota или чужд-файл изолация.
- Няма произволен Core/foreign DB path, нов общ DB broker, автоматично adoption,
  промяна на старите constructor позиции или подмяна на SDK 1.3.

Условие за приемане: собствена транзакция/outbox работят с точния профил; липсващо,
отнето или остаряло право не допуска нова работа. Legacy поведение и поддържаното
възстановяване са запазени. Source review не изпълнява това условие.

## 2. Platform и frontend: наличните API не означават scoped support

Провереният source resolver отказва приложения с `platform_permissions`, jobs,
public HTTP routes и неподдържани provides, а compiled UI се маркира отделно като
`frontend_authority_unresolved`. Peer declarations имат и
`peer_authority_unresolved`. Тези откази не трябва да се премахват само защото
manifest-ът е валиден или има UI компоненти.

Остава да се фиксират и реализират точните adapters за приетите платформи:

- Checkpoints: own installation, revision/CAS, read/write, bounded payload и
  текущо одобрено право. Сега compatibility проверки има, scoped adapter няма.
- Identity/peers/status: точна операция и Core-resolved installation/peer binding,
  текуща местна воля и generation. Service право не става human admin или cloud
  ownership. Запазват се работещите отделни peer consent/security договори.
- Jobs/public routes/provides: описват се точните разрешени операции и actor/
  service контекст преди добавяне на support. Scheduler leases и quarantine не
  се заобикалят. Staged lifecycle и dependency resolution остават WP3, не WP4.
- Frontend host: module-bound operation invocation и информация за поддържани
  features/права без Core token, private stores или общ HTTP/path bypass.
  Backend отново проверява audience/actor/operation и resource grants.

Публичните `UiSurface`, `UiButton`, `UiDialog` и CSS tokens се **използват**.
Не се създават втори Vue runtime, UI framework или theme API. Нов operation
contract не се публикува като вече поддържан преди отрицателните му тестове.
Third-party browser sandbox се доказва в WP5; reviewed-native UI не го заменя.

Условие за приемане: поддържаните операции минават през един и същ grant lifecycle;
неподдържаните са ясно означени и не падат към compatibility execution след opt-in.

## 3. Един общ acceptance сценарий, а не нова система от fixtures

Използва се неутрален SDK reference с disposable data/mock connector и без реални
GPIO, плащания или фискални операции. Това не изисква промяна на бизнес extension.

1. Standalone + local Agent + mock embedded provider и Hub + Linux/embedded nodes
   използват еднакви SDK заявки и общия capability registry; extension-ът не
   разклонява по конкретен хардуер или Fleet наличност.
2. Реален installed package/host и подписан transport доказват review, approval
   без apply, exact apply, разрешено изпълнение и отказ при undeclared/foreign
   ресурси. Одобрение не се фабрикува с SQL или fixture-only evidence.
3. Public/kiosk/operator/admin и фалшив/изтекъл контекст се проверяват през Core
   route/operation границата, отделно от service resource grants.
4. Revoke, disable/re-enable, restart и загубен отговор не повтарят физическа или
   външна работа и не възстановяват автоматично старо право.
5. На disposable VM се проверяват backup/restore и supported failed-update
   recovery с предварително проверен backup/snapshot. Hub recovery се приема само
   за действително поддържания обхват; Standalone file recovery не е Hub доказателство.

Първо локален автоматизиран сценарий през нормалните validators/host/transport,
после отделно одобрен live VM/Standalone/Hub тест. Резултатите записват exact Core/
SDK/package versions и coverage; unit fixtures не заменят live доказателствата.

## Ограничена следваща стъпка

Първият остатък е **relational storage contract** върху съществуващия SDK:
фиксиране на requested/approved profile, transaction admission и migration/
recovery границата, след което съвместима реализация с положителни/отрицателни
тестове. Не се започват едновременно нов frontend runtime, peer rewrite или
Developer Kit packaging. Kit използва приетите договори накрая на milestone.

Обновяване 2026-10-10: [relational storage contract](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md)
вече конкретизира exact read/write profile, per-transaction admission, SQLite/
WAL limits, lifecycle/recovery и трите части на acceptance. Локално са добавени
декларацията/валидаторите, advisory ZIP review и exact installed v5 grant metadata
през съществуващия review/approve/apply/revoke coordinator. Activation/host и
generic effect/lifecycle guards отказват relational execution; runtime adapter,
UI integration и recovery интеграция остават за реализация. Това не премахва
DB остатъка и не затваря WP4; старият SQLite runtime не се обявява за scoped.

Следващата локална стъпка добавя вътрешния bounded SDK SQLite engine и отказ на
platform calls в scoped SQL context. Реални DB tests покриват read/write separation,
outbox atomicity, SQL authorizer/escapes, cursor lifetime, bounds, deadlines и
неясен commit без replay. Test admission callback не е подписан Core transport
или реален current grant. Durable admission/receipts и lifecycle/recovery wiring
остават задължителни; activation guards и SDK **1.3** са запазени.

Следващата вътрешна стъпка добавя actual current-grant Core journal и подписани
permits, bounded atomic own-SQLite commit receipts, metadata lookup без replay и
completion след SQL unlock. Core journal използва existing sealed Action model;
forward SDK metadata preparation е rollback-tested, но още не се извиква от
protected production lifecycle. Host context в tests е explicit fixture
dependency, не доказан host resolver или реален Unix transport. Activation и
нови platform relational actions остават отказани; recovery lineage/epoch и
transport-key rotation трябва да се координират преди runtime включване.

Следващата локална част добавя readonly prepared-host reader, root-protected
signed lifecycle metadata, fresh runtime nonce, bounded metadata-only Unix
worker и Core-derived enclosing-operation tickets/deadlines. Actual current
grant admission и receipt completion вече се проверяват с real Unix session
resolver; service request не задава host context, lineage или срок. Test fixture
подготвя lifecycle record/DB изрично: това **не** е production migration/restore
authority. Startup reader не изпълнява migration code и не поправя липсваща или
стара база. Activation/host/native/platform guards остават отказани до coherent
lifecycle publication/recovery и нормалната dispatch/SDK transport интеграция.

Следващата lifecycle част свързва проверен SQLite snapshot/absence manifest със
съществуващия activation checkpoint: bounded readonly backup, checksum/closed
evidence, staged restore и запазени candidate DB/sidecars при interruption.
Повреден DB preimage спира и file rollback преди namespace switch. Реални
частично committed forward SDK migrations се връщат заедно с schema history,
business data, outbox и sdk-files в disposable tests. Legacy candidate не може
да заобиколи наличен protected relational record. Това **не** е first-adoption
authority, protected migration/publication или restore с fresh lineage/epoch;
тези части и production dispatch остават необходими преди runtime включване.

Последната ограничена lifecycle част добавя explicit local-admin one-use
existing-schema preparation: current exact sealed grant/native/session/boot
проверки, root helper с existing mutation locks и DB/files preimage, само fixed
SDK receipt metadata и protected publication. Package Python/migration/factory
не се изпълняват като root. Липсваща/business schema mismatch или вече prepared
lineage отказва. Успехът остава disabled/prepared_not_started; lost finish ACK
пази candidate/snapshot/marker без rollback/replay. Fresh install/business
migrations чрез непривилегирован worker, fresh-lineage/key recovery и production
dispatch/SDK wiring остават; guards и SDK 1.3 са непроменени.

Последващата локална част добавя отделен one-use ticket/signing purpose/fixed
worker-policy digest за business migrations. Реален child с exact non-root
UID/GID, без ключове/tokens, импортира само pinned migration wheel; service
factory не се изпълнява. Проверени са initial DB absence и forward history в
вече създаден own namespace, bounded SQL/процес, общ preimage rollback, revoke
преди публикация и lost ACK без replay. При unconfirmed worker stop не се
възстановява база върху възможни живи writes. Това не е prepared-DB upgrade,
namespace/key provisioning, fresh-lineage/key recovery или production dispatch;
тези части и общото Standalone/Hub acceptance остават. Подробности/проверки са в
[relational contract](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md#initial-schema--forward-business-migrations--отделен-non-root-worker).

Последващата recovery част приема само exact published candidate след ново human
confirmation; не възпроизвежда package migration или uncertain operation. Core
сменя epoch, изисква fresh permission review и sealed-fence-ва старите relational
admissions, без да измисля outcome. Root helper проверява old lineage/key/schema,
пази DB/files/metadata preimage, сменя само fixed SDK lineage и архивира evidence
след confirmed finish. Normal readiness не получава bypass; partial publication,
unconfirmed worker, unknown marker и прекъснат recovery остават blocked.
General restore/rollback/rekey и production wiring **не** са приключени.
Добавена е отделна explicit readonly confirmation за вече напълно публикуван
recovery с lost finish request/response: fresh human/epoch/one-use authority,
exact current lineage + verified DB/files preimage, archive без SQL replay или
restart. Repeated lost confirmation ACK и partial archive изискват нов human
request; historical evidence не става нов grant. Partial publication/unconfirmed
worker, general restore/key coordination и production wiring остават blocked.
Подробности: [readonly confirmation](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md#interrupted-recovery--explicit-readonly-confirmation).
Нова targeted Linux regression: **191 passed**, включително **32 confirmation
cases** и предходната регресия; actual root disposable WSL Ubuntu fixtures,
Python **3.14.4**, SQLite **3.46.1**. Няма live действия, commit/push или release.
Предходната recovery regression: **159 passed**, включително **28 recovery cases**;
Black/isort и whitespace проверките минават. Това не е full release/live acceptance.
Подробности са в [relational contract](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md#explicit-recovery--приемане-на-проверен-published-candidate).

Адаптация на външния DeepSeek migration опит от `/opt/3mm-dev` (2026-10-10):
използван е полезният three-step forward/rollback сценарий, не целият по-стар
snapshot и не втори relational SDK/worker. Запазени са отделният human migration
ticket, bounded SQL facade, actual non-root process/group stop и съществуващите
recovery/confirmation добавки. Worker вече проверява ZIP origin на всеки parent
package/module преди import: loaded Core module или друг wheel не може да стане
migration entrypoint само чрез `sys.path` precedence. Namespace packages се
запазват само когато всички техни locations са в същия pinned wheel, без смесено
зареждане от други packages/Core directories.

Новият rollback regression изисква независимо SQLite наблюдение на **committed**
`0002` от реалния worker преди failure в `0003`, witness с actual UID/GID и
запазен candidate snapshot. После проверява възстановени business/schema/outbox/
SDK files и active metadata без restart. Import/permission failure не може да
мине вместо този сценарий. Допълнителен file-backed `ATTACH` regression отказва
създаване на неразрешена база. Използват се наличните disposable ownership/
traversal fixtures; не се разширяват production permissions. Bounds и uncertain
worker stop се проверяват през съществуващия единствен migration worker.
Това е ограничена интеграция, не WP4 closure или разрешение за production runtime.

Проверка на тази интеграция: **43 passed** — всички **39 migration cases** и
**4 recovery confirmation cases** за lineage/evidence и original pending
preparation checkpoint. Отделна съвместимост: **85 passed** за existing-schema
preparation, SDK relational wire и explicit recovery. Общо **128 distinct
targeted tests**, без skipped cases, върху actual disposable WSL Ubuntu paths
с root helper и exact non-root migration child; Python **3.14.4**, SQLite
**3.46.1**. Black/isort и whitespace проверките минават. SDK остава **1.3**,
Core версията остава **0.3.0-beta.44**. Това не е full release suite или live
acceptance; няма commit/push/release, deployment или редакции в `/opt/3mm-dev`.

Следващата normal-host стъпка вече свързва **verified prepared database** с
реалната non-root factory/handler и scoped SDK. Enclosing invocation ticket
идва от Core след outer gateway checks; transaction admission, completion и
historical lookup използват existing signed platform socket. Factory/health
нямат неявно SQL право, readiness не чете business/outbox, а undeclared files
не получават legacy fallback. Restart не импортира migration code. Exact
metadata-only requests отказват SQL/path/deadline context от package-а.

Новият real-host файл има **12 cases**; финалният targeted run е **191 passed**
с existing Core admission/host, SDK engine/receipts/wire, platform authority и
activation regression. Actual child е UID **1200** / GID **1201** след actual
protected preparation. Проверени са и atomic commit, read-only/revoke, lost
completion response без replay, restart, root factory и pending-checkpoint
refusal. Re-enable е explicit disposable fixture state, **не** завършен public
first-install/upgrade coordinator. Full lifecycle orchestration, generic
activation/native gates и каталогът още не са разрешени като production feature.
Подробности: [normal host/SDK transport](EXTENSION_PLATFORM_V2_RELATIONAL_STORAGE_CONTRACT.md#нормален-hostsdk-transport--само-verified-prepared-database).
Отделна final compatibility regression: **35 passed** за existing gateway/
platform/transport, file host и unprepared relational gate. Двата финални runs
имат **226 distinct tests**, без skips; предходният 45-case поднабор не се брои
повторно. Това не е full release suite или live VM приемане.

Следват remaining DB lifecycle, scoped platform/frontend договорите и общото acceptance. WP4 се затваря
само при записано покритие или изрично одобрена промяна на scope, не чрез
обявяване на оставащите отказани операции за реализирани.

## Проверени източници

### Release кандидат beta.45 — пълни проверки, 2026-10-10

Кандидатът запазва SDK **1.3** и описаните отказани generic relational gates.
Точният подготвен source, изнесен в disposable native Linux директория, минава
пълната Python suite: **2 970 passed**, **3 expected skips** (две non-POSIX-only
проверки и opt-in HTTPS acceptance), плюс **5 passing subtests**. Actual root и
non-root migration/host/recovery cases са изпълнени. Отделно целите deployment и
SDK suites минават **282 tests**. Предходните targeted runs не се добавят повторно.

Всички **299 frontend tests**, type-check и production build минават. Първият
parallel frontend run има import-time timeout; целият one-worker rerun минава
без промяна на assertions или deadlines. Първият full Python run намира stale
legacy storage fixtures и Unix socket върху Windows mount. Поправени са само
fixtures/test isolation, после целият run е повторен успешно; production guards
не са отслабени.

Това е автоматизирана release проверка, не live VM/Hub/Standalone приемане.
Публикацията остава gated от canonical GitHub проверки и reproducible packages.
Оставащите DB lifecycle/platform/frontend и общи acceptance задачи по-горе
**не** са затворени. Тестовият release не затваря WP4 или Milestone 20.

- [WP4 scope и closure checklist](../EXTENSION_PLATFORM_V2_CORE_PLAN.md#wp4--public-platform-api-sdk-and-authorization).
- [Public SDK / ApplicationStorage](../three_mm_application_sdk/__init__.py) и
  [storage tests](../three_mm_application_sdk/tests/test_storage.py).
- [Storage descriptor](../three_mm_protocol/application_extension.py) и
  [host context/migration](../three_mm_runtime/application_host.py).
- [Installed source blockers](../backend/services/application_authority_sources.py),
  [platform dispatcher](../backend/services/application_platform.py) и
  [no-fallback tests](../backend/tests/test_application_authority_management.py).
- [Public Extension UI v1](EXTENSION_UI_V1.md), [exports](../frontend/src/extension-ui/v1.ts)
  и [compiled loader](../frontend/src/utils/compiled-ui.ts).
- [Provider-neutral command tests](../backend/tests/test_application_command_providers.py).
- [Private files — current execution, review и evidence](EXTENSION_PLATFORM_V2_PRIVATE_FILES.md).
- [Live test checklist](EXTENSION_PLATFORM_V2_BETA_ACCEPTANCE.md).

Първоначалният audit е source-only и предшества release подготовката. Последващите declaration и exact metadata
стъпки имат protocol/ZIP/policy/admin review/host tests, описани в relational
contract. Grant records са проверени в disposable test fixtures; няма live
предоставени права, DB migration или deployment. Release проверките са описани
отделно по-горе и не заменят оставащото acceptance.
