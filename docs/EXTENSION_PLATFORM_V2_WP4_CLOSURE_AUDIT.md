# M20 — проверка на остатъка за приключване на WP4

Първоначален audit: 2026-10-09; последно обновяване: 2026-10-13. Първоначално проверен checkout:
`main`, HEAD `3ce8607`, с наличните локални непубликувани промени. SDK остава
**1.3**. Първоначалната проверка е source-only; последващите targeted тестове
са записани по-долу. Ограниченият private-file VM сценарий вече е приет по-долу;
това не е общото Standalone/Hub live приемане или приключване на WP4.

## Какво действително е налично

| Област | Налично | Какво още не е доказано/реализирано |
| --- | --- | --- |
| Собствена база | Legacy `ApplicationStorage`; relational декларация/exact grants, bounded engine, signed Core admission/atomic receipts, verified preparation/migrations/recovery, private two-consent first preparation с fresh key handoff/empty-bootstrap reconciliation, explicit inert first registration → normal review/approve/apply → local-admin/helper preparation и отделен one-shot activation CLI/helper, normal host/SDK transport за protected prepared DB; fresh-human stop-only interrupted-start reconciliation с local-admin/helper wiring и metadata-only status; confirmed reactivation и повторно stop-only recovery през local-admin/helper; explicit enable-only boot CLI/helper/Core-UID writer и current-trust pre-import gate за Root-managed boot с protected pending/confirmed publication. | Остават boot-enable live systemd/reboot acceptance, account provisioning, prepared-DB upgrade, general backup/rollback/key и nonempty partial interrupted-recovery resolution, включително запазване/fencing на boot metadata. Generic activation gates са запазени; local-admin registration/preparation/activation/reactivation/recovery/boot тестовете не са complete public first-install/upgrade acceptance. Legacy SQLite не е scoped. |
| Собствени файлове | Декларация, точни read/write grants, подписан SDK transport, target-owned executor, лимити, receipts и отказ при revoke/drift. Административният диалог показва точните ресурси; private-file VM сценарият на beta.47 е приет. | Общото SDK/Standalone/Hub приемане и live foreign-path/limit cases остават отделни. Файловите лимити не покриват SQLite. |
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

## Live beta.46 — отказ при private-file достъп, 2026-10-11

В WSL VM е възпроизведен `get: blocked` при active/enforced приложение с
`grant_effective: true` и работещ файлов worker. Причината е SDK directory walk:
`O_RDONLY` изисква read право и върху `/var/lib/3mm`, която правилно е `0710` —
само search/traversal за `3mm-app`. Това не е липсващ grant и не изисква `chmod`
на production state или immutable release.

Локалната поправка pin-ва Linux ancestors с `O_PATH`, `O_DIRECTORY`, `O_NOFOLLOW`
и `O_CLOEXEC`, после отваря pinned data directory с `O_RDONLY` за namespace I/O и
`fsync`. Symlinks, липсващ search достъп и unreadable data leaf остават отказани.
На POSIX без `O_PATH` се запазва предишният protected readable-directory walk;
няма path-based fallback. SDK **1.3**, grants, receipts, лимити и Core API не се
променят.

Проверка: **332 passed** върху Linux/Python **3.14.4** — целият SDK и targeted
Core file execution/authority, WP4 package, worker/host, snapshots и activation.
Новите permission tests използват actual non-root процес; root-run повторението
на SDK file suite също минава **42 tests**, със свалени UID/GID за permission
cases. Това е припокриващ се поднабор, не допълнителен unique-test total.
Двата нови положителни regression cases се провалят с directory walk-а от beta.46
и минават с поправката. Frontend production build също минава.

Отделна read-only проверка с реалния `3mm-app` UID и локалния поправен SDK отваря
data descriptor на тестовата инсталация, като запазва state mode `0710` и отказа
за прочит на родителската папка. Не изпълнява live file get/put, не редактира
release, не рестартира приложение и не създава или променя права. Инсталираната
beta.46 остава непоправена до нов release/update; пълният live scoped-file flow
след update и общото WP4 acceptance остават отворени.

## Приет live private-file VM сценарий — beta.47, 2026-10-12

Изпълнен от собственика на WSL Ubuntu/`LAZ-DELL`, след update. Източникът
на evidence е предоставеният терминален изход и изричното потвърждение за рестарт
на Core, не локален mock или ново действие на Codex върху инсталацията.
Проверка на backup възстановяемостта не е доказана чрез този изход.

- Core **0.3.0-beta.47**, Application SDK **1.3**; `org.3mm.wp4-test` **1.0.0**,
  installation **5**, Manifest v2, reviewed-native (не sandbox).
- Exact artifact: `6cd6368d8f6402bb486ebcb5288c7369c0d30884beedeed9ad6db782fe175ca5`.
  Effective read/write rights дават първоначално `missing`, после `stored`/`found`.
- Request `68614d551d824e549938a0c8ef426548` записва `WP4 beta47 test` (15 bytes),
  SHA-256 `ed9a422dc745fe559e43c621bfd7f2277eb6adc2e49cba66f1dc8fd669fa2665`;
  historical receipt има `outcome: completed` и същите ID/digest/size.
- Exact повторение връща същия резултат и непроменени данни/receipt. Променен
  payload под същия ID връща `unconfirmed`, без промяна на прочетения файл или
  първоначалния receipt. Това не е общ тест на lost-transport fault injection.
- При `grant_state: revoked`/`grant_effective: false`, активният extension
  връща `get: blocked`. Нов опит с правилния текущ CAS digest и ID
  `13b57b912e6a4a4680364b441927b1b7` връща `unconfirmed`. След изрично възстановяване
  този ID има receipt `not_found`, а оригиналният файл/receipt са запазени.
- След възстановяване и потвърден рестарт: mode `enforced`, effective grant
  revision **3**, непроменени файл/SHA-256 и original completed historical receipt.
  Не е повторен несигурният запис и не са предоставени права чрез SQL.

**Прието:** този конкретен private-file VM сценарий и production permission fix.
**Не е прието чрез него:** пълно relational lifecycle, Hub, чужди paths/граници,
read-only-only profile, lost-ACK injection, portable restore/failed-update,
event/device/connector/platform/frontend acceptance или WP4/M20 closure.

## Fresh relational namespace — ограничена вътрешна стъпка, 2026-10-12

Добавен е отделен explicit LOCAL-admin `create_owned_namespace` ticket в existing
sealed Action journal. Current exact grant/native/session/boot/epoch/generation
се проверяват на всяка фаза; отделните signing purposes и closed models не
превръщат namespace consent в SQL/migration/lifecycle permit. Ticket обвързва
non-root UID/GID, отделния trusted Core UID и digest на fresh per-instance key;
не съдържа secret bytes, package-selected paths или application-selected identity.

Root helper създава само липсващи own `releases`/`data`/`run` и transport key под
existing release/runtime locks, след confirmed stop. Съществуващи namespace/key,
symlink/unsafe ancestry/overlap или unresolved witness отказват без подмяна.
Protected roots могат да са под search-only Core-owned parent като installer
layout-а; application-owned parent се отказва. Production permissions не се разширяват.
Owner/mode/content се проверяват преди completion. Partial creation/revoke/lost
finish ACK пазят root witness и pending checkpoint, без изтриване на ключ/data,
автоматично replay, repair, enable или package import като root.

Успехът е **namespace_created_not_started**, без DB/active metadata. Схемата се
подготвя отделно чрез existing explicit migration ticket/non-root worker. Това
е вътрешна foundation, не public first-install/upgrade coordinator или manual
production recipe. На този foundation етап account provisioning, fresh-secret handoff/orchestration,
namespace interrupted-recovery resolution, prepared-DB upgrade/verified restore
и general key/lineage/epoch coordination са още отворени; последващият ограничен
handoff/reconciliation срез е описан по-долу. Generic guards, SDK
**1.3**, Core версията и външните endpoints не са променени.

Проверка на source на този foundation в disposable native Linux checkout, Python **3.14.4** /
SQLite **3.46.1**: **228 passed**,
без skips. Включва **49 нови namespace cases** и съществуващите preparation,
business migrations, recovery/readonly confirmation, real host, wire и gate
регресии. Actual non-root child отказва root helper; отделният integration
сценарий създава namespace/key от absence и използва existing migration worker
с actual UID/GID **1200/1201**, без service factory/import като root. Потвърдени
са и current-authority drift, protected/search-only Core ancestry, disjoint
paths, collisions, shared locks, revoke, partial writes и lost begin/finish ACK.
Core grant/native/actor records не са фабрикувани за успешния flow; използвани са
existing real ZIP/review/approve/apply fixtures. Negative drift injection е само
в disposable test state.

Frontend production build, Black/isort и whitespace проверките минават. Това
не е full release suite или нов live relational VM тест. SDK **1.3** и
Core **0.3.0-beta.47** са запазени; няма commit/push/release или live промяна.

## First preparation + empty-bootstrap reconciliation — 2026-10-12

Private root coordinator вече генерира fresh random 32-byte per-instance key и
го записва с exclusive create + fsync в root-only `0600` handoff под helper state,
преди namespace creation. Secret bytes не са в Core Action journal, results,
HTTP/CLI payload или package configuration. Бюджетът е **32 retained handoffs**
за instance; няма автоматично изтриване/rotation. Частичен actual transport-key
write не губи original secret и не се поправя чрез overwrite.

Изискват се две explicit consents: namespace/key и business migrations. След
confirmed namespace completion се издава отделният existing migration ticket;
owner/package/config/profile/grant/binding/epoch/generation трябва да са същите.
Code imports/migrations остават в existing actual non-root worker. Успехът е
`prepared_not_started`, без enable/restart, account creation или grant approval.
Lost namespace finish ACK никога не издава migration ticket и не повтаря setup.

Отделният fresh LOCAL-human recovery ticket предлага само:

- `confirm_owned_namespace`: проверява **complete empty** layout и exact key,
  без повторно creation/rekey/SQL. След durable Core ACK архивира само verified
  matching pending checkpoints; original witness и original outcome се запазват.
- `quarantine_owned_namespace`: премества само **known empty** partial bootstrap
  в recoverable evidence със същия filesystem; archive ancestry е root-only
  `0700`, key е root-only `0600`. Не overwrite-ва destination и не изтрива data/key.
  Main witness блокира fresh setup до confirmed Core finish и archive. След това
  новото setup е отделна explicit операция с **нов random key**, не SQL replay.

Latest sealed recovery pointer fence-ва original creation/older recovery helpers.
Всяка фаза отново проверява current native review/grants/local actor/session,
boot/deadline/epoch/generation; historical evidence не дава нови права. Lost finish
request/response и partial archive пазят uncertainty и изискват **нов** human
ticket. Recovery използва existing shared release/runtime locks, не second broker.

Any business DB/file, wheel/release, active/relational metadata, foreign/changed
key, symlink/hardlink, unsafe ancestry, unknown checkpoint или надвишен metadata
budget отказва този empty-bootstrap path. Той не е general restore или permission
to discard application data. No live roots/accounts/services/grants са променени.

Финалният lifecycle run в disposable native Linux checkout минава **287 tests**,
без skips: **47 empty-bootstrap recovery**, **12 first-preparation** cases и
existing namespace/preparation/migration/recovery/confirmation/host/wire/gates.
Отделният admission/runtime/review/context/session/SDK engine/receipts regression
минава **249 tests**, без skips — общо **536 distinct targeted cases**. Първият
284-case run е преди final ownership/budget tightening и не се прибавя повторно.
Проверени са actual root helper, actual non-root UID/GID **1200/1201**, partial
key handoff → explicit quarantine → нов random key → реални migrations; factory
не се импортира като root. Current grants/native/actor идват от existing real
ZIP/review/approve/apply fixtures; failure injection е само в disposable state.

Целият Application SDK пакет отделно минава **203 tests** с non-root Linux
потребител; това е припокриваща се проверка, не 203 допълнителни unique cases.
Един cache warning е за read-only root-owned source checkout, не failed assertion.
Python **3.14.4** / SQLite **3.46.1**; existing deprecation warnings са запазени,
не потиснати. Frontend production build, Black/isort и whitespace checks минават.
Това не е full release suite или live first-install/restore acceptance.

Остават public first-install/account provisioning + lifecycle dispatcher,
prepared-DB upgrade и general backup/rollback/rekey/nonempty interrupted recovery.
Scoped platform/frontend contracts и общото Standalone/Hub acceptance също остават.
Това довършва **вътрешния** bootstrap/handoff срез, не WP4 closure или production
installer endpoint. Generic denial gates, SDK **1.3** и Core **beta.47** са запазени.

## Local-admin/helper preparation — ограничено production wiring, 2026-10-12

Съществуващият Core local administration CLI вече има `prepare-relational` с
точен installation ID, expected grant-record revision и **две задължителни
потвърждения**: fresh owned namespace/key и owned business migrations. Current
LOCAL administrator token се въвежда скрито; не е argument, environment override,
файл или резултат. Командата не одобрява права и не активира приложението.
Това е непубликуван source; наличната beta.47 още няма тази команда.

Използва се existing privileged helper socket, не нов broker/HTTP endpoint.
Root приема този action само от actual OS peer UID на Core (`SO_PEERCRED`),
не от root/application UID, group membership или подадено JSON identity.
Closed request не приема paths, artifact/configuration overrides, UID/GID,
ключове или worker commands. Helper използва installer roots и existing
Core/`3mm-app` accounts; не създава нови системни accounts.

Core metadata phases се изпълняват от fixed **non-root Core-UID worker**,
с отделени private pipes и bounded systemd runtime. Worker проверява existing
configured Core DB преди engine import, current human/session, exact installed
artifact/configuration/native review/grant и всяка one-use фаза. Root не импортира
package code и не се представя като Core за създаване на authority. Core leases
приключват преди root filesystem effects; secret handoff и migration worker
остават съществуващите реализации. Lost reply не се повтаря автоматично.

Успехът връща само namespace/database preparation receipts и
**`prepared_not_started`**; installed application остава disabled. Generic
activation guards и review/apply границите не са отслабени. Separate enable,
upgrade, nonempty recovery и root coordination не се подразбират от този успех.

Входна граница на този wiring етап: тогава source resolver изисква стабилен installed
record с `active_version`, съвпадаща с избрания package. Затова този срез свързва
подготовката на **вече регистриран стабилен disabled record**, но не завършва
пътя от липсваща инсталация. Следващата стъпка е explicit inert registration
без package execution, следвана от normal review/approve/apply и отделна prepared
activation. Не се задава фиктивна `active_version`, не се фабрикуват grants и
не се предлагат ръчни SQL записи, за да бъде заобиколена тази граница.

Финалният targeted run върху disposable native WSL Ubuntu source минава
**153 tests**, без skips: **28 нови production-control cases** и **125 existing
helper/lifecycle/activation/relational-gate/systemd-template/Core-authority
regressions**. Всички са върху последния source. Actual non-root Core CLI →
реален Unix socket/peer credentials → root helper → actual Core-UID metadata
child → actual non-root migration child е проверен до disabled preparation.
Тестовете не създават OS accounts и не редактират live roots/grants/services.

Fixed systemd argv/hardening и отказите при malformed frames, wrong peer,
stale/revoked actor или grant, unknown/lost response и повторна подготовка са
проверени. В disposable harness transient systemd launch и stop/unit I/O са
заменени с test adapters; това **не** е live systemd/service acceptance. CLI
child е отделен от controlling terminal, за да използва private test stdin;
production hidden token prompt и timeouts не са променени.

Frontend production build, new-file Black/isort и whitespace checks минават.
Python **3.14.4** / SQLite **3.46.1**; existing warnings не са потиснати.
Това не е full release suite, първа live инсталация или WP4 closure. SDK остава
**1.3**, Core **0.3.0-beta.47**; няма commit/push/release или live промяна.
Remaining scoped platform/frontend и общото Standalone/Hub acceptance остават.

## Inert first registration — от липсваща инсталация до preparation, 2026-10-12

Local Core admin CLI добавя `register-relational`: exact uploaded catalog package
ID + SHA-256, stable request ID и explicit `--confirm-register-without-start`.
Optional configuration file е bounded JSON със strict duplicate-key rejection;
config/schema validation използва existing application configuration contract.
Current LOCAL human/session се проверяват преди ZIP I/O и отново под final
key → Core guard transaction. Няма startup hook, HTTP/SDK writer или automatic trust.

От absence се създава existing installation record: **`active_version: null`**,
`status: disabled`, `enabled: false`, `authority_mode: review_required`, без
activated/health timestamps и без runtime socket. Няма namespace/key provisioning,
package Python import, migrations, helper call, native review или grant. Existing
installation, включително staged/failed/recovery-required, не се преизползва.

Registration provenance и human request receipt са атомични **подписани Action
records в съществуващия journal**, заедно с audit и guard advance. Provenance ID
се извежда от Core identity + installation ID/incarnation; record обвързва exact
catalog package/version/SHA, instance и protected configuration fingerprint.
Няма нов persistence model, inferred backfill, destructive migration или нова SDK
версия. Plain record existence е само preliminary artifact pin, не authority.
Final keyed composition проверява seal/state/purpose/binding в същия snapshot.
Unkeyed source reader не издава частичен subject за never-active registration.

Normal exact native-review → review → approve → apply работи върху тази
**никога не стартирала** инсталация. Baseline artifact е authenticated selected
registered package, не твърдение за running/previous active version. Apply дава
само reviewed grant metadata; effective runtime rights остават false при disabled
приложение. След отделните namespace/migration consents existing helper може да
подготви own DB с actual non-root worker, без промяна на `active_version` или enable.

Повторение на exact registration request връща само authenticated **historical**
receipt — без нов installation/epoch/guard advance или повторно изпълнение. Друг
payload/actor под същия ID отказва. Corrupt/missing/foreign seal, incarnation,
instance/configuration drift или key rotation не стават permission fallback;
не се презаписва old proof като repair. Interrupted/old-key registration recovery
още изисква отделен explicit contract. Ordinary never-active records не стават
reviewable само чрез задаване на disabled/review-required status.

Новите **32 registration cases** включват exact CLI без helper, from-absence
registration → реален sealed native review/approve/apply → actual Core-UID metadata
worker → root namespace helper → actual UID/GID **1200/1201** migrations. Проверяват
се no automatic native/grant/start, current actor, closed/typed requests, ZIP
bytes/symlink/key откази, provenance drift, request conflict, atomic rollback,
unsupported platform declaration и keyed/unkeyed read-only граници. No live
accounts/roots/services/grants са променени. В harness systemd launch и unit I/O
остават adapters, не live service acceptance.

Финалното общо повторение върху exact source: **297 passed, 1 skipped**. Покрива
всички 32 registration cases и existing sources/subjects/native-management,
relational review API, production helper, namespace, empty-bootstrap recovery и
first-preparation suites. Skip-ът е само non-POSIX refusal върху Linux; actual
Core/application UID helper/worker сценарии са изпълнени. Отделните **56 passed,
1 skipped** за registration/subject compatibility са припокриващ се поднабор,
не допълнителен unique-test total. Frontend production build, new-file
Black/isort и whitespace checks минават. Python **3.14.4** / SQLite **3.46.1**;
existing warnings не са потиснати.

Първият общ run намери четири промени в legacy read-only diagnostics от ранното
key acquisition. Legacy resource-before-key редът е възстановен; само inert
registration придобива key преди snapshot за provenance authentication. В същия
run две helper подготовки останаха unconfirmed; isolated replay на теста в нови
disposable paths и final sequential suite минаха. Причина за тези два отказа не
е доказана; не са увеличавани timeouts, отслабвани assertions или replay-вани
несигурни production операции. Това не е full release/live acceptance.

Следва **отделна explicit prepared activation**: registration и preparation не
разрешават generic activate/re-enable. Prepared-DB upgrade, general recovery,
scoped platform/frontend и общото Standalone/Hub acceptance още не са затворени.
SDK **1.3** / Core **beta.47**, без commit/push/release или live инсталация.

## Private prepared activation — отделен start consent, 2026-10-12

Добавени са отделни closed activation ticket/result и signing purposes; те не
се приемат като preparation, migration или SQL permits. Current exact grant,
native review, local human/session, artifact/configuration/profile/owner,
Core generation и boot/deadline обвързват еднократния start. Ticket запазва
**съществуващите database lineage и digest на prepared lifecycle**, вместо да
издава нова подготовка. Нов permission review между preparation и start е
допустим, но трябва независимо да е current; старото epoch не се преправя.

Prepared source Action се резервира атомично за един activation ID в existing
sealed journal. Дори изгубен отговор при издаването не разрешава втори start
под нов ID. Няма нов persistence model, inferred grant или DB migration.
`begin` сменя epoch/mode към **review_required преди process startup** и
обезсилва pending commands. Old sealed grant остава historical start consent,
а не runtime permission. Next phases проверяват exact consent/native/resources
и новото activation epoch; fresh apply/revoke/config/key/generation/session
промяна спира completion, вместо да бъде презаписана.

Private root coordinator използва existing release/runtime locks. Проверява
protected roots/key/wheel/active metadata, own namespace/database ownership,
service traversal/read permissions и readonly prepared/schema/receipt readiness.
Не chmod-ва production paths, не сменя key/lineage, не копира или възстановява
база и не импортира package factory/migrations като root. Отделният supervisor
проверява fixed unit non-root User/Group и след старта kernel UID/GID credentials,
не identity от health payload. Health transport е ограничен от срока на ticket.

Service start е **точно един**, без helper restart/retry или generic activation
fallback. Factory и health нямат неявен SQL/file grant. След healthy finish Core
записва действителна active version/socket и active status, но mode остава
**review_required**; business SQL се допуска само след ново normal
review → approve → apply. Protected DB/lifecycle/active metadata/key bytes
остават непроменени от този cooperative start. Reviewed-native код не е sandbox
и директният злонамерен Python I/O не се обявява за изолиран.

Witness е root-only `0600` под helper state, без token/secret bytes, и се пази
при lost begin/finish ACK, failed health/revoke или unconfirmed Core abort/stop.
Known failure иска fail-closed metadata fence и verified stop, но не приема
загубен отговор за потвърждение. Няма SQL rollback/replay или автоматично
възстановяване на старите права. Source остава consumed; на този етап explicit fresh-human
interrupted-start reconciliation още е необходим. Confirmed witness се архивира
с fsync; budget е 32 retained activation witnesses за instance, без automatic prune.

**Граница на този вътрешен етап:** тогава activation още не е свързана с local
CLI/existing helper socket/fixed Core-UID worker. Следващият срез по-долу свързва
точно този private coordinator; това не е public install endpoint. Existing
generic activation/native/gateway denial gates и read-only status blockers са
запазени. Systemd adapter не enable-ва boot autostart; existing unit restart
policy не е сменена. Довършването на confirmation/boot-enable/uncertainty wiring
е отделно и не се подразбира от private healthy outcome. Live systemd, общото
Standalone/Hub acceptance, upgrade/restore/rekey и scoped platform/frontend
остават отворени; **WP4 не е затворен**.

Новите тестове покриват real ZIP/admin/native/exact grants и current-authority
drift, atomic begin rollback, closed wire и one-use source. Actual root disposable
helper стартира actual UID/GID **1200/1201** host, с kernel credential checks и
factory SQL/file denial; след fresh review реалният SDK изпълнява own read/write.
Допълнителният from-absence flow използва истински inert registration и fresh
namespace/key/business preparation, без SQL enable или fake active version.
Systemd командите/състоянията са adapter tests, **не live unit acceptance**.
Няма live account/root/service/grant промени или редакции в `/opt/3mm-dev`/M21.
SDK **1.3** и Core **0.3.0-beta.47** остават непроменени; няма commit/push/release.

Final targeted regression върху exact source в disposable native WSL Ubuntu:
**463 passed, без skips**, включително **64 нови activation cases**, и existing
preparation/migrations/namespace/empty-bootstrap recovery/registration/real host,
Core admission/review/authority и generic activation/lifecycle/systemd gates.
Python **3.14.4** / SQLite **3.46.1**; actual non-root cases са изпълнени, не
пропуснати. Frontend production build, new-file Black/isort и whitespace checks
минават. Предходните 58-case и subset повторения не се добавят към този total.
Existing deprecation warnings не са потиснати; това не е full release suite.

Първите runs откриха грешен test import/call и проверка на journal с вече
невалиден generation seal; тестовете са поправени да проверяват отказа и
непромененото stored state без да го представят за authority. From-absence test
добави липсващите traversal/group настройки само в disposable fixture, след
actual non-root permission failures; runtime проверката вече отказва такава
недостъпна ancestry преди startup. Production paths не са chmod-вани, assertions
и deadlines не са отслабени. Final общият run минава след тези поправки.

## Local-admin/helper activation — отделна команда, 2026-10-12

`activate-relational` е отделен explicit start на **вече подготвена** инсталация:
installation ID, точен database preparation ID, current grant-record revision,
stable request ID и задължителен `--confirm-start-prepared-service`. Login token
се въвежда скрито, не е argv/environment override или резултат. Namespace creation,
migrations, native trust и grant approval не се изпълняват от тази команда.
Това е още непубликуван source; инсталираната beta.47 няма новата команда.

Използва existing privileged helper socket с **actual Core OS peer UID** чрез
`SO_PEERCRED`, без Root/app UID или group-membership fallback. Closed request
не допуска paths, runtime root, configuration, keys, UID/GID, commands или
caller-authored receipts. Helper първо получава current disabled installed
snapshot от Core и чак после прочита съществуващия protected instance key.
Secret handoff е само чрез private pipes към fixed **Core-UID** metadata worker,
не CLI/stdout, environment или sealed Action data.

Worker има отделни closed `inspect_activation`/`issue_activation`/
`activation_checkpoint` операции, не generic RPC. Exact runtime root идва от
trusted worker argv и се сравнява с Core configuration преди engine import;
не се задава от request и не се записва чужд socket path при layout mismatch.
Current actor/native/grant/resource/boot/epoch/generation checks и one-use
source reservation остават в existing coordinator. Core leases не обхващат
helper filesystem, start, health или stop I/O. Ambiguous duplicate-key helper
frames и прекалено вложен JSON се отказват; valid legacy requests са запазени.

При успех командата връща **active_review_required**, точния activation receipt,
`permission_approval: not_evaluated` и **boot_autostart_enabled: false**.
Old grant не се възстановява, service factory/health нямат неявен SQL/file grant,
prepared DB/metadata/key не се мигрират или сменят. Lost metadata/helper response
и transport timeout изрично са **unconfirmed / do not retry**, без второ issue,
start или compatibility fallback. Source remains consumed; recovery/boot-enable
изискват следващ отделен explicit contract. Shared generic activation/native/
gateway gates и read-only status blockers не са премахнати; няма public/SDK
installation writer или UI convenience bypass.

Disposable acceptance проверява от липсващ installation record: inert registration
→ real native review/approve/apply → actual Core-UID preparation worker → actual
non-root migrations → actual Core admin CLI/Unix peer → Root helper → actual
**Core UID/GID 1202/1203** metadata writer → actual **application UID/GID
1200/1201** host. Kernel identity и factory denial се проверяват независимо от
health payload. Няма SQL enable/fake active version или fabrication на successful
native/grant evidence; Root и Core metadata правомощия не се сливат в един process.
Systemd launch/unit I/O остават test adapters — това **не** е live unit acceptance.

Целият нов activation-control файл минава **42 tests**, без skips, върху native
WSL Ubuntu/Python **3.14.4** / SQLite **3.46.1**. Всички actual Core/application
UID процеси и CLI/socket acceptance cases са изпълнени. Първият run намери
несъответствие в error class за malformed ticket; parser-ът вече отказва shape
преди manager access. Fixtures за преди-admission откази не създават namespace;
successful preparation/start cases продължават да използват действителните
workers, без по-дълги deadlines или отслабени assertions. Full release/live
acceptance не се подразбира от тези targeted проверки.

Final compatibility run върху exact source: **247 passed, без skips**, в девет
файла — всички **42 activation-control cases**, existing production preparation,
inert registration/private activation и shared helper/activation/lifecycle/
relational-gate/systemd suites. Предишният 42-case run е припокриващ се поднабор,
не допълнителен total; historical 463-case run е преди този wiring. Actual Core
CLI/UID worker и actual application process са изпълнени. Frontend production
build, new-file Black/isort и whitespace checks минават. Existing warnings не
са потиснати. Няма full release suite, live systemd/Standalone/Hub acceptance.

На този wiring етап следват interrupted-start reconciliation и отделно confirmed boot enable;
prepared-DB upgrade/restore/rekey, scoped platform/frontend и общото Standalone/
Hub acceptance остават. **WP4 не е затворен.** SDK **1.3**, Core **beta.47**,
без commit/push/release/live actions или промени в `/opt/3mm-dev`/M21.

## Interrupted prepared start — private stop-only reconciliation, 2026-10-12

Добавени са отделни closed recovery ticket/result и signing purposes в existing
sealed Action journal. Fresh LOCAL human confirmation изисква exact activation
ID и **текущия sealed source revision**, а не повторно използване на start ticket.
Core атомично сменя epoch към `review_required`, обезсилва pending commands,
оставя installation disabled и записва latest recovery pointer. Original start
state/ticket/receipt и consumed preparation reservation се запазват. Superseded
start/recovery helpers не могат да завършат със старото authority.

Това е **само stop/reconciliation**, не application execution admission. Current
administrator/session и exact owner/incarnation/package/config/profile/Core
generation/key/preparation chain се проверяват отново. Нито effective grant,
нито действащ native review се изискват за спиране: отнето доверие не трябва да
принуждава администратора да даде права отново. Sealed grants остават непроменени;
inherited grant/binding fields са historical evidence, **не** SQL/start permit.
Expired или old-boot start ticket не се подновява; издава се нов stop-only ticket.

Root coordinator използва existing release/runtime locks и проверява exact
root-only bounded `0600` original witness — pending или authenticated archived
completion при lost outer reply/directory ACK. Conflicting witnesses, foreign
identity, symlink/hardlink, unprotected/oversized/duplicate-key metadata се отказват.
Липсващ witness се допуска само при още `recorded` Core start, но **не** се
представя като доказателство „никога не е стартирал“: пак се изисква verified stop.
След stop се проверяват fixed non-root unit identity, own namespace/DB ownership,
protected key/wheel/active metadata и bounded read-only prepared/schema readiness.
Root не импортира application code, не стартира health/factory, не мигрира,
не restore-ва/rekey-ва и не променя lineage/configuration или production permissions.

Успехът е **`stopped_review_required`**, не restored/active/permitted. Original
witness не се изтрива или презаписва дори при успех. Отделен per-request root
record се fsync-ва преди possibly lost Core finish ACK; budget е **32 retained
recovery records** за instance. Lost begin/finish/stop или publication ACK остава
unconfirmed. Стар request не се replay-ва; нов explicit human stop може да
провери отново текущото състояние и да supersede-не неизвестния опит, без да
преправя неговия outcome, да restart-ва service или да възстановява grant.

Новият recovery файл минава **56 tests, без skips**, върху последния source в
disposable native WSL Ubuntu/Python **3.14.4** / SQLite **3.46.1**. Actual Root
coordinator и actual UID/GID **1200/1201** host проверяват прекъсване преди start,
след start, след Core finish и след archive rename; successful paths пазят
DB/key/lifecycle/active metadata bytes и original witness. Покрити са fresh
stop при revoked grant/native review и expired/old-boot source, lost recovery
begin/finish ACK, unknown stop, superseded requests, actor/configuration/key/
owner/artifact/evidence drift и atomic failed-write rollback. Final package pin
се проверява повторно под Core transaction, включително race след ZIP validation;
never-active provenance се удостоверява с existing sealed registration contract.
Предишните 42 cases са преди разширяването и не се добавят към този total.
Systemd stop/identity I/O са adapters, **не** live unit acceptance; Core callbacks
в тези нови tests са in-process, **не** новият Core-UID recovery worker pipeline.
Frontend production build, Black/isort и whitespace checks минават; existing
deprecation warnings не са потиснати.

Съвместимостта минава **271 existing tests, без skips** в десет файла: Core
registration/activation, actual CLI/Core-UID preparation/start control, shared
helper/lifecycle/systemd/generic denial gates и SDK wire. Общият run е **324
passed**, включително тогавашните **53 recovery cases**, преди final pin-race
проверка. След нея целият recovery файл е повторен отделно — горните **56 passed**.
Compatibility source не е променян между runs. Така покритието е **327 distinct
targeted cases в два runs** (271 + 56), а не 324 + 56; initial 42-case run и
припокриващите се 53 cases не се броят повторно. Това не е full release suite.

**Граница на този foundation етап:** тогава това е private Core/root механизъм с authenticated callbacks,
не нова production CLI/helper команда, HTTP/SDK writer или recovery UI. Следва
closed local-admin/helper wiring през actual Core OS peer и fixed Core-UID
metadata worker; отделно confirmed reactivation/boot enable остава необходимо.
Тези тестове не доказват live systemd, Standalone/Hub acceptance или general
DB restore/upgrade/rekey. Generic denial gates, SDK **1.3** и Core **beta.47**
са запазени; **WP4 не е затворен**. Няма commit/push/release/live действия или
промени в `/opt/3mm-dev`/M21.

## Local-admin/helper interrupted-start recovery — 2026-10-13

Добавени са две отделни LOCAL Core admin команди. `inspect-relational-start`
приема installation ID + original activation ID и връща authenticated Core
source revision/state/latest recovery ID, **`metadata_only: true`** и
`permission_approval: not_evaluated`. Не отваря instance transport key, не
проверява/спира процес и не променя epoch/grants/journal/guard revision. Не
показва configuration, ticket или private key и не представя historical state
като доказателство за текущ runtime outcome. Използва current administrator и
точния sealed source/owner/package/configuration/provenance snapshot.

`recover-relational-start` изисква installation ID, original activation ID,
**expected source revision**, caller-stable new request ID и задължително
`--confirm-stop-preserve-prepared-state`. Hidden login token не е argv,
environment override или резултат. Command pre-check потвърждава текущия
администратор преди helper call; root helper приема само actual **Core OS UID**
от `SO_PEERCRED`, не Root/app UID, membership в Core group или JSON identity.
Closed request не приема paths, configuration, UID/GID, secret, grants,
worker commands или caller-authored receipt.

Fixed Core-UID worker има separate closed `inspect_activation_recovery`,
`issue_activation_recovery`, `activation_recovery_checkpoint` dialect. Layout
идва от trusted worker argv и се сравнява с Core configuration преди engine
import. Private snapshot не изисква current runtime grant/native review и
предхожда четенето на existing protected instance key; actual issue/checkpoints
отново проверяват signed preparation/activation chain и current actor/bindings.
Ключът се предава само по private bounded stdin към fixed Core-UID writer,
без Core lease през Root/process/read-only DB I/O. Няма new broker/API/SDK writer.

Original caller CAS е за издаването. То резервира source и сменя sealed revision;
следващите callback frames използват **точно post-reservation revision от новия
ticket**, не мълчаливо обновена стара стойност. Стар request/revision не се
повтаря автоматично. След unknown issue/begin/finish/stop/outer response трябва
нов authenticated status read, нов human confirmation и new stable request ID.
Recovered witness/history и original prepared state не се изтриват/презаписват.

Успехът връща **`stopped_review_required`**, exact source/request-bound recovery
receipt, `permission_approval: not_evaluated` и `boot_autostart_enabled: false`.
Няма migration/rekey/rollback, restart, enable или automatic grant restoration.
Malformed/ambiguous/lost result е изрично **unconfirmed / do not retry**. Това е
непубликуван source; инсталираната beta.47 още няма тези команди.

Disposable tests вече минават през actual Core CLI/UID **1202/1203**, real Unix
peer → Root helper → actual Core-UID journal writer, след from-absence inert
registration/real review/approve/apply/non-root preparation и actual **1200/1201**
host start. Симулираният coordinator crash оставя реален жив application process,
който recovery спира. Проверени са unchanged DB/key/active/lifecycle/original
witness и historical grant; успешният flow не използва SQL enable/fake version
или fabricated grant. Отделен actual Core CLI revoke-native-review → stop
доказва, че отказаното доверие не се връща заради recovery. Systemd launch/unit
I/O са test adapters, **не live systemd acceptance**.

Проверки върху source на този wiring в disposable native WSL Ubuntu, Python
**3.14.4** / SQLite **3.46.1**: **41 recovery-control tests**, после **3 допълнителни
disjoint cases** — actual Root/application peer, дори с Core group, и отказ на
CLI без mandatory consent преди prompt/helper. Общо **44 нови cases, без skips**;
production source не е променян между тези runs. Actual Core CLI/UID writer и
actual application process са изпълнени, не replaced by claimed JSON identity.
Всички lost-ACK cases изискват нов human read/CAS/request; timeouts и assertions
не са отслабени и няма автоматично replay.

Отделният compatibility run е **231 passed, без skips**: целите 56 interrupted
activation recovery cases, existing activation-control/production preparation,
shared update-helper/application lifecycle/relational denial/systemd templates
и SDK wire. Покритието е **275 distinct targeted tests** в три runs (44 + 231),
без повторно добавяне на историческите foundation проверки. Frontend production
build, scoped Black/isort и whitespace checks минават. Existing warnings са
запазени. Това не е full release suite, live systemd/VM/Standalone/Hub acceptance
или WP4 closure.

Следват **отделно confirmed reactivation и boot enable**, prepared-DB upgrade,
general restore/rekey, scoped platform/frontend и общото Standalone/Hub
acceptance. **WP4 не е затворен.** SDK **1.3** и Core **beta.47** са запазени;
няма commit/push/release, live root/account/service/grant промени или редакции
в `/opt/3mm-dev`/M21.

## Confirmed prepared reactivation — private foundation, 2026-10-13

След exact **confirmed** interrupted-start recovery има отделен LOCAL human
`reactivate_prepared_service` ticket/signing purpose. Изисква current native
trust и **нов** normal permission review/approve/apply при disabled installation,
точен recovery ID/revision и ново explicit start confirmation. Stop ticket,
старият start grant или healthy outcome не се превръщат в право за повторен start.
Historical stop може да е от стар boot/deadline; само новият outer ticket има
fresh текущ epoch/boot/budget и актуален actor/resource/owner/package binding.

Confirmed recovery и неговият source start се резервират атомично за един
reactivation ID в existing sealed Action journal. Lost issuance response не
позволява повторно издаване или връщане към стария source. Late original recovery
callbacks са fence-нати; следващо recovery трябва да посочи **новия** start.
Original preparation reservation, tickets, states и receipts не се нулират или
преправят. Няма нов persistence model, SQL backfill или migration.

Root използва същия one-shot prepared activation coordinator, fixed non-root
supervisor и shared release/runtime locks. Новият closed ticket съдържа bounded
exact historical stop ticket/receipt, не secret или package-selected paths.
Root изисква matching protected `0600` stop record с confirmed publication и
unchanged original start witness; `stopped_unconfirmed`, missing/changed/foreign/
symlink/hardlink/ambiguous metadata отказват преди process effect. Prepared
key/wheel/active metadata/DB ownership и readonly lifecycle readiness също се
проверяват. Actual stop/unit identity се потвърждава отново преди новия start.

Повторният start има **собствен per-action witness**, вместо да трие/мести
original pending marker. Budget е 32 retained reactivation files за instance,
с bounded enumeration и без automatic prune. Core `begin` fence-ва epoch и
commands преди стартиране; успехът пак е **active_review_required**, без boot
enable или grant restoration. New human runtime review е необходим за business
SQL. Database lineage/preparation, migration history, данни и key се запазват;
няма preparation/migration/rollback/rekey replay.

Ако повторният start е interrupted/unknown, private stop-only recovery има
distinct `reconcile_reactivated_start` ticket/purpose и проверява неговия exact
pending/archived witness. Старото stop authority не се подновява. Fresh verified
stop → нов explicit review → нов one-use reactivation могат да продължат същата
prepared lineage, без нарастващ recursive ticket graph или смесване на свидетелства.
All original evidence остава recoverable. No current grant/native trust се
изискват за stop; изискват се независимо за последващия start.

Final targeted run върху exact source в disposable native WSL Ubuntu/Python
**3.14.4** / SQLite **3.46.1** минава **277 tests, без failures/errors/skips**:
**52 нови reactivation cases**, всички 64 initial activation и 56 start-recovery
cases, плюс 105 existing SDK wire/shared helper/activation/lifecycle/relational
denial/systemd-template cases. Actual Root coordinator и UID/GID **1200/1201**
host изпълняват start → crash → verified stop → review → restart, после second
crash → fresh stop → third start. Проверени са data/key/history preservation,
реални SDK read/write само след new runtime review, one-use/CAS, current rights/
actor/native/configuration/generation/key/package drift, lost begin/finish ACK,
unknown/changed stop witness и bounded retained evidence. Core-only cases не
се представят като доказателство за physical stop или нов Core-UID CLI pipeline.

Отделният compatibility run минава **6 tests, без skips** за съществуващите
first-start/recovery команди: actual Core CLI/UID **1202/1203**, real Unix peer,
Root helper, actual Core-UID metadata writer и actual **1200/1201** host;
actual Root/app peer, дори в Core group, отказва преди authority/key access.
Това е compatibility на стария closed dialect, **не new reactivation wiring**.
Общо **283 distinct targeted tests** в два final runs. Осемте Python source/test
файла са byte-identical по SHA-256 между working checkout и двата test clones.
Frontend production build, scoped Black/isort и whitespace checks минават.
Existing deprecation/test-key warnings не са потиснати; няма full release suite.

Първият проход намери два race-test отказа и 11 teardown errors: fixture helper
четеше current grant след injection вместо да запази prior CAS, а негативният
process-effect sentinel оставаше monkeypatched и за финалното test cleanup.
Поправени са само тези test boundaries; за reactivation е добавен и final pin
recheck на всяка Core фаза и bounded witness enumeration. Final общият run е
повторен върху този source; deadlines, assertions и production guards не са
отслабени. Preliminary/diagnostic/subset runs не се прибавят към final total.

**Граница на този foundation етап:** тогава това е private Core/Root механизъм
с authenticated in-process callbacks, без нова CLI/helper socket команда или
public/SDK writer. Следващият срез по-долу добавя отделния closed local-admin
wiring, без generic activation fallback. Boot enable остава отделна задача.
Reviewed-native код не е sandbox; няма live systemd/Standalone/Hub acceptance.
SDK **1.3**, Core **beta.47**, `/opt/3mm-dev` и M21 не са променени; няма commit,
push, release, live accounts/services/grants или production permission промени.
**WP4 не е затворен.**

## Local-admin/helper confirmed reactivation — 2026-10-13

`inspect-relational-recovery` приема installation ID и exact recovery ID.
Проверява current LOCAL administrator и Core-sealed latest source/owner/package/
configuration/generation, после връща **metadata_only** revision/state/recovered
activation ID/latest reactivation ID. Не изисква current grant или instance key,
не чете private runtime files, не проверява процес и не променя authority/journal.
Core `confirmed` тук **не** е твърдение за текущ Root/process outcome; transport
signature и protected Root publication се проверяват при отделния start.

`reactivate-relational` изисква installation ID, confirmed recovery ID + expected
recovery revision, current grant-record revision, нов caller-stable request ID и
задължителен **`--confirm-restart-stopped-prepared-service`**. Token се въвежда
скрито, не е argv/environment/резултат. Current administrator се проверява преди
helper call. Командата не approve-ва права, не rerun-ва preparation/migrations,
не сменя key/lineage и не enable-ва boot autostart. Изисква independently current
normal review/approve/apply; самият confirmed stop не ги създава.

Root приема new action само от **actual Core OS UID** чрез existing Unix socket/
`SO_PEERCRED`, не Root/app UID или член на Core group. Closed payload отказва
paths, configuration, UID/GID, secrets, receipts, commands и implicit consent.
Fixed Core-UID worker има отделен `inspect_reactivation`/`issue_reactivation`/
`reactivation_checkpoint` dialect. Original activation checkpoint приема само
original ticket type, не новия reactivation purpose. Trusted application root
идва от worker argv и се сравнява с installed Core configuration **преди engine
import**. Няма generic RPC, нов broker/HTTP/SDK writer или caller layout override.

Private helper snapshot изисква exact current grant/native/disabled state и
unconsumed confirmed recovery **преди** existing instance-key access. Issue и
всяка следваща фаза проверяват full signatures/exact history/current authority.
Key/token се предават само по bounded private pipes; Core metadata lease е
затворен преди Root filesystem/start/health/stop I/O. Caller CAS е само за issue;
checkpoints изискват **новия post-reservation recovery revision от ticket-а**,
не стария request CAS или silent read-and-refresh.

При успех result е **active_review_required**, exact reactivation receipt,
`permission_approval: not_evaluated`, `boot_autostart_enabled: false`. Factory/
health не получават implicit SQL/files; старото grant не се възстановява.
Ambiguous/malformed/duplicate/lost reply остава **unconfirmed / do not retry**.
Metadata status показва reserved new start ID дори при lost issue ACK. Следва
fresh `inspect-relational-start` за **новия** ID, explicit stop и нов review,
не replay/reset на old start или връщане към consumed original recovery.

Existing `recover-relational-start`/fixed worker вече приемат и отделния
**stop-only** repeated-start ticket. Core/Root проверяват точния new source и
неговия собствен witness; original state/ticket/receipt/key/DB са запазени.
Current native trust/grant не се изискват за stop и не се restored-ват от него.
Успехът остава stopped_review_required; още един start изисква нов confirmation.

Проверки върху точния production source в disposable native WSL Ubuntu/Python
**3.14.4** / SQLite **3.46.1**: новият reactivation-control файл има **37 cases**.
Шестте actual Core CLI/UID **1202/1203** → real Unix peer/Root helper → actual
Core-UID metadata writer → actual **1200/1201** host сценарии минаха в първия
проход. Те включват real from-absence preparation/first interrupted start/stop,
normal human review/approve/apply в actual Core UID (не SQL enable/fake grants),
повторен старт и lost issue/begin/finish ACK → fresh status/new-ID stop → new
review → още един start. Проверяват actual kernel identity, unchanged DB/key/
original witness и historical grant, factory denial и exact post-reservation
CAS; successful start не restore-ва old permission или boot enable.

Първият `-x` run спря при един **unit test expectation**: malformed source ID
правилно връща existing `AuthorityManagementError(invalid_request)`, не очаквания
`ValueError`. Точно този expected error class е поправен; production отказът,
assertions и deadlines не са отслабени. След това всичките **31 останали cases**
минаха, с шестте already-passed process cases deselected, не skipped. Включени
са две добавени duplicate-frame/response проверки, actual Root/app peer дори
с Core group, CLI mandatory consent преди prompt/helper и no-retry client.
Предишните припокриващи се 19 unit cases и отделното 2-case duplicate повторение
не се добавят към total. Шестте production Python файла са byte-identical по
SHA-256 между working checkout и трите използвани test clones; единствената
междинна промяна е negative-test expectation/добавяне на duplicate tests.

Final compatibility run минава **271 passed, без failures/errors/skips**:
всички 42 activation-control, 44 recovery-control, 52 private reactivation и
28 production-preparation cases, плюс 105 shared helper/activation/lifecycle/
relational denial/systemd-template/SDK wire tests. Така final coverage е
**308 distinct targeted cases** (6 + 31 + 271), без двойно броене. Frontend
production build, scoped Black/isort и whitespace checks минават. Existing
deprecation/test-key warnings не са потиснати. Това не е full release suite или
live systemd/service/Standalone/Hub acceptance; launch/unit I/O остават adapters.

Граници: source е непубликуван; beta.47 няма тези команди. Generic relational
activation/native/gateway denial gates, public SDK **1.3** и Core версията са
запазени. Systemd launch/unit I/O в disposable tests са adapters, не live
systemd/Standalone/Hub acceptance. Boot enable, prepared-DB upgrade/general
restore/rekey/nonempty recovery и scoped platform/frontend остават отделни.
**WP4 не е затворен.** Няма commit/push/release, live account/service/grant или
production permission промени; `/opt/3mm-dev`/M21 не са редактирани.

## Prepared boot enable — private foundation, 2026-10-13

Добавен е отделен LOCAL human `enable_prepared_boot` ticket и distinct
`boot_enable`/`boot_enable_result` signing purposes. Приема само **activated**
точен initial или repeated start, без subsequent stop/recovery/reactivation,
с current sealed source revision, нов stable request ID и explicit consent.
Изисква independently current native review и normal review/approve/apply след
старта. Healthy start, manifest или historical start grant не дават boot/SQL
права. Owner/incarnation/artifact/configuration/profile/schema/generation,
existing key digest, non-root principals и trusted runtime/socket layout се
проверяват отново. Bool не се приема за UID/GID, включително при реален UID 1.

Existing sealed Action journal резервира успешния start за **един** boot request.
Lost issue ACK не позволява друг request да използва същия source. Caller CAS е
за issue; ticket съдържа new post-reservation source revision. Begin/check/finish
отново проверяват exact source reservation/digests, current administrator/session,
grant/native/epoch/generation/boot/deadline и active installation. Няма нов DB
model/migration, automatic grant restoration, source receipt rewrite или промяна
на installation enabled/status/socket, grant или authority epoch от boot action.
Stop-only recovery може да fence-не и този request; late completion отказва.

Root използва existing release/runtime mutation locks, exact protected **archived
successful start witness** и signed receipt. Pending/absent/conflicting/changed/
unprotected/symlink/ambiguous/oversized evidence не се приема за boot readiness.
Prepared key/wheel/active/lifecycle/own DB ownership и bounded read-only schema
readiness са проверени преди effect. Current health е по подписания existing
transport и не дава factory/health SQL access. Fixed systemd unit non-root
credentials и **kernel process incarnation (PID + start time)** трябва да
останат същите преди и след enable. Ordinary prepared start продължава да
изисква disabled unit; новият boot adapter не отслабва този gate.

Единствената успешна systemd mutation е **`enable`**, без `--now`, start, restart,
stop, migration, key/lineage replacement или DB rollback. Успехът е
**`boot_enabled_not_started`**, не нов runtime grant. Normal boot host създава
нов runtime nonce; всяка SQL admission пак изисква актуалните независими права.
Това е source contract, не доказателство за реален reboot на VM/systemd.

Root записва bounded `0600` per-request witness преди begin и signed result преди
potentially lost Core finish ACK. Budget е 32 retained boot witnesses с bounded
enumeration, без automatic prune. Unknown enable/check/finish/publication остава
**unconfirmed / do not retry**. След attempted enable има best-effort **disable
only**, без да stop/restart-ва работещото приложение; failed cleanup или crash
не се представя за disabled outcome. Existing explicit stop/review е пътят за
reconciliation, а не replay/reset на old ticket. Core historical confirmation
не замества проверка на protected Root evidence/current unit.

Проверки върху disposable native WSL Ubuntu/Python **3.14.4** / SQLite
**3.46.1**: целият финален boot файл минава **97 passed, без failures/errors/skips**.
Core-only cases проверяват sealed metadata, не physical health. Physical cases
изпълняват actual Root coordinator и actual **UID/GID 1200/1201** prepared host,
existing real native review/approve/apply и подписан health/SDK transport.
Проверени са unchanged process/data/key/lineage/current grant, independent fresh
runtime permissions, initial/repeated exact start witness, CAS/one-use/atomic
failed writes, actor/native/grant/key/generation/configuration/socket/clock drift,
strict principals, lost begin/check/finish/enable/cleanup ACK, witness/ownership
откази и bounded evidence без prune. Няма fabricated active version или grants
за successful physical flows. Core callbacks тук са in-process, не нов Core-UID
boot CLI pipeline; systemd enable/state са test adapters, не live boot.

Съвместимостта минава **277 existing cases, без failures/errors/skips**: 64
initial activation, 56 start recovery, 52 reactivation, плюс 105 SDK wire/shared
helper/activation/lifecycle/generic denial/systemd cases. Общият regression run
е **367 passed** с тогавашните 90 boot cases; след него са затегнати strict
principal checks преди metadata access и добавени още 7 cases, после целият boot
файл е повторен върху final source — горните 97. Shared wire/supervisor и
compatibility source не са променяни между тези runs. Така финалното покритие е
**374 distinct targeted tests** (277 + 97), не 367 + 97. Предходният 84-case
проход преди socket/layout tightening не се прибавя повторно. Frontend production
build, scoped Black/isort и whitespace checks минават; existing deprecation и
short fixture JWT-key warnings не са потиснати. Това не е full release suite.

**Граница на този foundation етап:** тогава това е private Core/Root foundation
с authenticated callbacks; още няма boot CLI команда/closed helper socket/
Core-UID worker dialect или UI. Следващият срез по-долу добавя **boot-time current
trust/start admission преди package import** за Root-managed boot. Самата
existing lifecycle/SQL grant проверка не е pre-import gate и foundation тестовете
не трябва да се обявяват за завършено boot acceptance.
Systemd command/unit assertions са adapters; physical tests използват actual
непривилегирован host, не live units/accounts. Reviewed-native остава не-sandbox.
Следват отделното local-admin wiring и live systemd/reboot acceptance.
Generic activation/native/gateway refusal gates, public SDK **1.3** и Core
**beta.47** са запазени. **WP4 не е затворен.** Няма commit/push/release, live
account/service/grant/permissions промени или редакции в `/opt/3mm-dev`/M21.

## Root-managed boot — current-trust admission преди import, 2026-10-13

Root boot coordinator вече публикува `boot-required.json` **преди каквото и да е
unit enable**, следван от `boot-authority.json` с `boot_pending`. Двата файла са
bounded/closed signed metadata, Root-owned `0640` с точния application GID, без
symlink/hardlink или caller-selected path. Само exact Core finish ACK **и**
confirmed Root witness позволяват `boot_confirmed` publication. Partial write,
missing companion, lost finish/publication ACK или Core-confirmed/Root-pending
разминаване отказват следващия import; historical Core receipt не ги поправя.

Наличието на **който и да е** от двата markers прави новия gate задължителен.
Trusted prepared host отваря своя bounded metadata-only listener и изпраща една
заявка през existing signed platform socket **преди добавяне на application wheel
към import path, service module import или factory**. Request body носи само
fresh host nonce, не PID/UID/GID, path, deadline, SQL, token или чужд ticket.
Existing private dispatcher подава actual kernel `SO_PEERCRED`; Core проверява
metadata socket на **същия PID/UID/GID**, не просто друг процес със същия UID.

Core изисква protected confirmed Root policy + exact sealed confirmed enable
Action + latest unconsumed original/repeated source и preparation/lifecycle
chain. Independently current native review, exact applied grant, owner/package/
configuration/schema/key/generation/epoch/socket/active state се проверяват отново.
Author на durable boot consent трябва още да е unblocked Core administrator;
старият login token/session не се replay-ва при unattended boot и не се създават
нови human/service права. ZIP validation, protected file и host metadata I/O са
извън Core key/authority lease; journal/audit mutation е атомична в existing model.

Успехът е distinct private `boot_startup` permit, не SQL/start/migration ticket:
current kernel boot, **5-second maximum** budget, exact PID + process start ticks,
UID/GID, fresh runtime nonce и digests на exact policy/lifecycle/current grant.
Nonce е one-use sealed Action; bounded journal exhaustion отказва без prune.
Host проверява signature/purpose/clock/process/bindings и отново protected policy
преди import. Lost/tampered reply не се retry-ва и не допуска import/factory;
ако Core вече е записал admission, nonce остава consumed. Отделен последващ
процес има нов nonce и трябва да мине нов current-authority admission. Това не
повтаря SQL/business operation. Factory/health продължават без implicit SQL/files;
всяка business transaction има отделния existing current-grant gate.

Historical enable ticket не се подновява за нов boot/deadline. Само новият кратък
startup permit се отнася за текущия kernel boot/process. Disposable old-boot
scenario проверява тази разлика; той не е реален VM reboot/clock-expiry acceptance.

**Обхват:** gate е за Root-managed boot installations. Когато **и двата** markers
липсват, ordinary explicit one-shot prepared manual start запазва existing consent
и supervisor contract; legacy SDK/host не получават нов implicit boot grant.
Единственото поддържано премахване на boot markers е existing fresh-human
stop-only reconciliation **след независимо проверени stopped + disabled unit**
и exact source/prepared identity. То пази проверими recoverable Root-only `0600`
копия под helper state, премахва required marker последен и никога не overwrite-ва
original start/enable witness, key, DB или lifecycle. Interrupted archive може да
се довърши с нов explicit stop request, не с automatic replay. След confirmed stop
нов manual start изисква separate fresh review/reactivation consent.

Финалният нов startup файл минава **49 passed, без failures/errors/skips** върху
disposable native WSL Ubuntu/Python **3.14.4** / SQLite **3.46.1**. Real cold host
използва actual application UID/GID **1200/1201**; отделен случай използва actual
Core UID/GID **1202/1203** platform server и kernel peer checks, без Root fallback
за metadata writer. Module-level import witness и factory witness доказват отказа
преди application import, не само отказ на последваща SQL transaction. Successful
flows използват existing real ZIP/native review/approve/apply, без SQL enable/fake
active version или fabricated grants. Unit/launch I/O още са adapters, не live
systemd boot.

Покрити са fresh nonce/one-use, short distinct permit и current grants/native/
author/key/generation/epoch/configuration/socket/source drift; malformed/protected/
missing/pending Root proof, lost finish/reply, foreign/Root/Core peer и another
same-UID process, journal limit/atomic rollback, verified stop/archive interruption
и separate fresh manual reactivation. Първите диагностични runs намериха negative
clock в fresh-boot fixture, грешно fixture key-directory attribute и липсващи
fixture configuration key/Core ownership на SQLite WAL/SHM. Поправени са само
disposable fixture boundaries; production paths/guards/deadlines/assertions не са
отслабени. Финалният целият startup файл е повторен след поправките.

Отделният compatibility run върху същия production source минава **449 passed,
без failures/errors/skips**: всички boot-enable/initial activation/start recovery/
reactivation cases, normal relational host/session/wire и existing platform/file
host/shared helper/activation/lifecycle/systemd/generic refusal suites. JUnit
потвърждава **498 distinct cases** (49 + 449), без припокриване между final runs.
Предишните 41-case, diagnostic и subset повторения не се добавят към този total.
Десетте production файла са byte-identical по SHA-256 между working checkout и
двата native test clones, проверено докато runs вървят. Frontend production build
минава; scoped Black/isort и whitespace checks също минават. Existing Pydantic/
utcnow/AnyIO deprecation и short fixture JWT-key warnings не са потиснати. Това
не е full release suite или live VM acceptance.

Това не е sandbox или защита срещу hostile Root, който премахва и двата markers,
нито пълна защита срещу reviewed-native код извън trusted host. General backup/
restore/upgrade/rekey/nonempty recovery трябва да запазват или fence-ват boot
authority metadata и още не са приети. На този startup етап boot-enable
local-admin/helper/Core-UID worker wiring още предстои; то е описано в следващия
срез по-долу. Live systemd/reboot и общото Standalone/Hub acceptance остават.
Няма нов публичен endpoint/SDK export/feature advertisement, DB model/migration,
grant restoration или промяна на generic relational activation/native gates.
SDK **1.3**, Core **beta.47** и `/opt/3mm-dev`/M21 са запазени; няма commit/push/
release или live account/unit/grant/production permission промяна. **WP4 остава
отворен.**

## Local-admin/helper prepared boot enable — 2026-10-13

`enable-relational-boot` е отделна LOCAL Core admin команда: exact installation,
successful initial/repeated activation ID, expected sealed source revision,
current grant-record revision, нов stable request ID и mandatory
**`--confirm-enable-prepared-boot`**. Existing `inspect-relational-start` показва
Core source revision без process/Root effects; историческият status не е boot
permission. Hidden current login token не е argv/environment override или output.
Командата не approve-ва права, не start/restart-ва service и не мигрира/rekey-ва DB.
Source е непубликуван; инсталираната beta.47 още няма тази команда.

Existing helper socket допуска този action само от actual **Core OS UID** чрез
`SO_PEERCRED`, не Root/app UID или просто Core group. Closed payload отказва
paths/runtime root, configuration, UID/GID, secret, grants, receipt, worker
commands и implicit consent. Fixed Core-UID worker има отделни closed
`inspect_boot_enable` / `issue_boot_enable` / `boot_enable_checkpoint` операции.
Trusted application root идва от worker argv и трябва да съвпада с Core config
**преди engine import**; не е JSON field или silent layout fallback.

Read-only private snapshot проверява current LOCAL actor/native/exact grants,
active installed package/owner/socket и exact successful unconsumed source CAS
**преди Root да отвори existing instance key**. Това е Core-sealed metadata,
не твърдение за текущ process outcome. Issue и всяка следваща фаза независимо
проверяват transport signatures, preparation/source chain и current authority.
Key/token са само в bounded private pipes към actual non-root Core writer;
Core leases са затворени преди Root file/health/unit I/O.

Caller source CAS се използва само за issue. След atomic source reservation
checkpoints изискват **post-reservation revision от exact new ticket**, не стария
request CAS или silent refresh. Root използва existing enable-only coordinator,
shared mutation locks, exact protected successful start witness и unchanged
kernel process incarnation. Existing pending/confirmed Root boot publication и
current-trust pre-import admission са запазени, не заменени с CLI success.

Успехът е **boot_enabled_not_started**, exact source/request-bound receipt,
`boot_autostart_enabled: true`, `permission_approval: not_evaluated`. Това е само
confirmed setting след проверка, не SQL grant или твърдение за успешно бъдещо
reboot. Ambiguous/duplicate/malformed/timeout/lost reply остава **unconfirmed /
do not retry**. New request не може да заеме вече reserved source. Existing
fresh-human inspect/new-CAS/stop-only recovery пази prepared state и Root evidence;
след него нов start/review/boot enable са отделни операции.

Новият boot-control файл минава **44 passed, без failures/errors/skips** върху
disposable native WSL Ubuntu/Python **3.14.4** / SQLite **3.46.1**. Actual Core CLI/
UID **1202/1203** → real Unix peer → Root helper → actual Core-UID metadata writer
проверява enable-only на actual **1200/1201** healthy host. Допълнителен full flow
минава през explicit stop → human review → confirmed reactivation → нов runtime
review → exact repeated-source boot enable. Kernel PID/credentials, unchanged
DB/key/lifecycle/original witnesses/grants/epoch и post-reservation CAS са проверени;
няма SQL enable/fake active version или fabrication на successful permissions.

Negative cases покриват current actor/source/grant/layout **преди key access**,
mandatory CLI consent преди prompt/helper, actual Root/app peer дори в Core group,
closed payload/worker dialect и ambiguous/duplicate client/helper frames. Actual
lost issue/begin/finish Core-UID ACK запазва uncertainty/source reservation и не
повтаря enable; fresh inspect/new-CAS/verified stop пази prepared data и архивира
matching Root boot markers. First `-x` run спря след **7 passed** при неправилно
test expectation за lost begin: без ACK Root правилно още не публикува policy.
Поправен е само този assertion да изисква **absence + no enable**; production
source/guards/deadlines не са отслабени. Целият final файл е повторен след това.
Отделният preliminary repeated-source case е покрит повторно в горните 44 и не
се добавя към total. Unit/launch I/O още са adapters, не live systemd/reboot.

Отделната final compatibility регресия минава **402 passed, без failures/errors/
skips**: всички 42 activation-control, 44 recovery-control, 37 reactivation-control,
28 production-preparation, 97 boot-enable и 49 pre-import startup cases, плюс
105 shared helper/activation/lifecycle/generic refusal/systemd-template/SDK wire
cases. JUnit потвърждава **446 distinct targeted tests** (44 + 402), без двойно
броене на preliminary/subset runs или историческите проверки от предишния срез.
Шестте production Python файла са byte-identical по SHA-256 между working
checkout и final/compatibility native clones, проверено докато runs вървят;
final new-test source също е проверен byte-identical. Frontend production build,
scoped Black/isort и whitespace checks минават. Existing Pydantic/utcnow/AnyIO
deprecation и short fixture JWT-key warnings са запазени, не потиснати. Това не
е пълният release пакет или live acceptance.

Няма нов HTTP/SDK writer, feature advertisement, DB model/migration, automatic
grant restoration или generic relational activation fallback. Boot-enable live
systemd/reboot, общото Standalone/Hub acceptance, prepared-DB upgrade/general
restore/rekey/nonempty recovery и scoped platform/frontend остават. **WP4 не е
затворен.** SDK **1.3**, Core **beta.47** и `/opt/3mm-dev`/M21 са запазени; няма
commit/push/release или live account/unit/grant/production permission промяна.

## Проверени източници

### Release кандидат beta.47 — пълни локални проверки, 2026-10-11

- Пълният default Python пакет върху изолиран Linux checkout и Python **3.14.4**,
  с root за реалните protected-helper cases: **3008 passed, 4 skipped**, още
  **5 subtests passed**. Два skip-а са non-POSIX откази; третият е opt-in HTTPS
  acceptance, а четвъртият е worker permission test, който изисква non-root.
- Отделното non-root повторение на целия file-worker suite минава **12 tests**,
  включително пропуснатия от root-run положителен search-only случай. Това е
  припокриващо се покритие, не допълнителен unique-test total.
- Пълните deployment и Application SDK suites минават **300 tests** с non-root
  Linux потребител. Реалните migration workers с отделен UID/GID също са
  изпълнени в пълния root-run, не са заменени с mocks или skips.
- Frontend: **313 tests / 44 files**, TypeScript check и production build минават.
  След ограничение на паметта в Windows тестовете са повторени с един worker;
  assertions, timeouts, scripts и production поведение не са променени.
- GitHub Python **3.13**/Node **22** CI и tag-driven reproducible builds остават
  задължителният gate за публикуване на точния commit. Тези локални проверки не
  са live scoped-file, HTTPS ingress, hardware или M15/WP4 completion acceptance.

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
- [Private first preparation / protected key handoff](../three_mm_runtime/application_relational_installation.py),
  [empty-bootstrap Core recovery](../backend/services/application_relational_namespace_recovery.py)
  и [root reconciliation](../three_mm_runtime/application_relational_namespace_recovery.py).
- [Local admin command](../backend/services/application_authority_admin.py),
  [inert registration/provenance](../backend/services/application_relational_registration.py),
  [registration tests](../backend/tests/test_application_relational_registration.py),
  [fixed Core-UID metadata worker](../backend/services/application_relational_admin_worker.py),
  [helper preparation control](../three_mm_runtime/application_relational_control.py)
  и [production-control regression](../backend/tests/test_application_relational_production.py).
- [Private Core activation consent/fence](../backend/services/application_relational_activation.py),
  [root prepared-service activation](../three_mm_runtime/application_relational_activation.py)
  и [activation regression](../backend/tests/test_application_relational_activation.py),
  [CLI/helper activation regression](../backend/tests/test_application_relational_activation_control.py).
- [Private Core interrupted-start recovery](../backend/services/application_relational_activation_recovery.py),
  [root verified stop/reconciliation](../three_mm_runtime/application_relational_activation_recovery.py)
  и [actual crash/lost-ACK regression](../backend/tests/test_application_relational_activation_recovery.py).
- [CLI/helper/Core-UID recovery regression](../backend/tests/test_application_relational_recovery_control.py).
- [Private fresh reactivation consent](../backend/services/application_relational_reactivation.py),
  [protected confirmed-stop verification](../three_mm_runtime/application_relational_reactivation.py)
  и [repeat-start/recovery regression](../backend/tests/test_application_relational_reactivation.py).
- [Actual CLI/Core-UID reactivation regression](../backend/tests/test_application_relational_reactivation_control.py).
- [Private boot-enable consent/journal](../backend/services/application_relational_boot.py),
  [Root enable-only coordinator](../three_mm_runtime/application_relational_boot.py)
  и [boot/drift/lost-ACK regression](../backend/tests/test_application_relational_boot.py).
- [Private current boot startup admission](../backend/services/application_relational_startup.py),
  [protected Root boot publication/archive](../three_mm_runtime/application_relational_boot_policy.py),
  [trusted host pre-import gate](../three_mm_runtime/application_relational_startup.py)
  и [actual cold-host/current-trust/lost-reply regression](../backend/tests/test_application_relational_startup.py).
- [Actual CLI/Core-UID boot enable regression](../backend/tests/test_application_relational_boot_control.py).
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
