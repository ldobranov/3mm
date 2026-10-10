# M20 — scoped relational storage върху SDK 1.3

Дата: 2026-10-10. Статус: **декларация, валидатори, exact grant metadata и вътрешен
bounded SQLite engine, вътрешен signed Core admission journal и atomic commit
receipts, вътрешен prepared-host session resolver с реален Unix metadata
transport, проверени SQLite preimages в съществуващия activation rollback и
private initial existing-schema SDK metadata preparation/publication и отделно
потвърден non-root business migration worker и explicit accept-candidate recovery
с fresh lineage/epoch и explicit readonly confirmation на напълно публикуван
прекъснат recovery реализирани локално**. Нормалният application host вече
подава scoped SDK adapter **само за проверена вече подготвена база** и използва
подписания Core transport за всяка транзакция. Full first-install namespace/key
setup, prepared-DB upgrade и backup/rollback/key recovery остават за реализация;
общите activation/native gates и каталогът още не обявяват relational runtime
за завършено production feature. Валиден descriptor или само approval не
предоставя SQL право; всяка supported transaction изисква current exact grant,
валидна protected lifecycle и Core-derived enclosing invocation.
Обхват: общият Standalone/Hub application platform; няма Fleet зависимост,
конкретен extension, нов ORM или Core SQL executor. SDK остава **1.3**.

Това конкретизира DB остатъка от [WP4 closure audit](EXTENSION_PLATFORM_V2_WP4_CLOSURE_AUDIT.md).
Използва се наличният [approval lifecycle](EXTENSION_PLATFORM_V2_APPROVAL_CONTRACT.md),
а не втори механизъм за одобрение. Read/write правата тук са service resource
grants, не потребителски роли или разрешение за физически/външни действия.

## 1. Какво запазваме и какво добавяме

Запазваме `ApplicationStorage`, собствената `data/state.sqlite3`, forward
`ApplicationMigration`, schema history и transactional outbox. Не променяме
старите constructor позиции, application identity, credentials или данните.

Днес `_connect()` отваря writable връзка и задава WAL дори за `status()` и
`due_outbox()`. `transaction()` връща raw `sqlite3.Connection` и започва
`BEGIN IMMEDIATE`. Това **не е** runtime DB read/write policy.

Добавя се host-selected scoped adapter към същия storage contract, а не база в
Core. Core разрешава точно собствената DB операция; SQL и business payloads
остават в application host. Няма клиентски DB path, URI, VFS или foreign namespace.
Root се извежда от защитената инсталация, никога от manifest/configuration.

Reviewed-native Python може да отвори SQLite или файл извън helpers. Този adapter
контролира поддържания SDK достъп; **не е sandbox или OS quota**. Защита срещу
злонамерен native код и твърди process/filesystem лимити остава WP5.

## 2. Requested profile и exact review

Additive полето `storage.relational` в storage descriptor се валидира за SDK 1.3.
Всички полета и лимити са задължителни. Каталогът различава структурната поддръжка
от runtime: `declaration_validation=supported`, `runtime_authority=not_implemented`,
`activation=blocked`. Пример:

```json
{
  "contract_version": 1,
  "mode": "read_write",
  "limit_class": "cooperative_v1",
  "max_database_bytes": 67108864,
  "auxiliary_pause_bytes": 16777216,
  "max_statement_bytes": 65536,
  "max_value_bytes": 262144,
  "max_result_bytes": 1048576,
  "max_result_rows": 1000,
  "max_transaction_ms": 5000,
  "max_busy_ms": 1000
}
```

Closed schema: без unknown keys, bool вместо integer, дублирани JSON ключове,
wildcards, отрицателни/нулеви лимити освен `max_busy_ms=0`. Няма paths или
package-supplied `approved`, execution profile, lifecycle token или grant ID.

При raw ZIP descriptor авторитетният parser е `parse_application_extension`:
той отказва дублирани ключове и non-finite числа преди typed validation.
JSON Schema или вече декодирана dict не могат да възстановят изхвърлени duplicate
keys. Parser-ът се използва за всички application descriptors; валидните legacy
декларации остават съвместими, но malformed JSON вече не се приема чрез last-key-wins.

| Поле | Граници за първия adapter | Значение |
| --- | --- | --- |
| `contract_version` | точно integer `1` | Независима версия, не SDK major |
| `mode` | `read` / `read_write` | Runtime достъп до собствените business tables |
| `limit_class` | точно `cooperative_v1` | Не означава hostile-code enforcement |
| `max_database_bytes` | 64 KiB–256 MiB | Логически SQLite pages × действителен page size, включително SDK tables/free pages |
| `auxiliary_pause_bytes` | 64 KiB–64 MiB | Operational pause threshold за собствените WAL/SHM/journal files, не peak disk quota |
| `max_statement_bytes` | 1–64 KiB | UTF-8 SQL statement bytes |
| `max_value_bytes` | 1 byte–1 MiB | Единична text/blob parameter/result стойност |
| `max_result_bytes` | 1 byte–1 MiB | Общ bounded result за една транзакция |
| `max_result_rows` | 1–1000 | Общ брой върнати редове за една транзакция |
| `max_transaction_ms` | 100–30000 ms | Общ budget от admission заявката до приключване |
| `max_busy_ms` | 0–5000 ms; ≤ transaction budget | Lock wait влиза в общия budget |

Изискват се `max_value_bytes ≤ max_result_bytes` и
`max_value_bytes ≤ max_database_bytes`. Adapter-ът може да откаже профил според
реалния host/SQLite support; няма silent clamp до други одобрени лимити.

Core review извежда exact ресурс от текущата инсталация:
Core identity, logical application identity/incarnation, module, точен package
digest, effective configuration identity, schema revision/migration entrypoint,
декларация/лимити и Core-owned adapter/trust/policy revisions. Физическият path
не се изпраща на клиента. Runtime instance ID е routing identity, не собственик.

Scope keys за вътрешните v5 review/grant records: `storage:relational_read` и
`storage:relational_write`. `read` изисква само read; `read_write` изисква и двете
за първия adapter. Избира се целият точен профил или се отказва — няма UI
свободен JSON, стесняване на лимити или read-only downgrade на read_write request.
Одобрение не изпълнява SQL/migration; apply отново проверява baseline и epoch.
Файлово право не предоставя DB достъп и обратно.

## 3. Runtime SDK операции

| Операция | Право / поведение в scoped adapter |
| --- | --- |
| `read_transaction()` — additive API | Current relational read; readonly snapshot, bounded results, без upgrade до write |
| Съществуващото `transaction()` | Current relational read + write; business mutation/outbox commit или rollback заедно |
| `due_outbox()` / application `status()` | Current read; същите bounds, без implicit creation/migration |
| `enqueue_outbox(connection, ...)` | Само собствената активна write session; не нов connection/второ admission |
| `update_outbox()` | Собствена write transaction с current grant, не writable bypass helper |
| `migrate()` върху runtime context | Отказ; host lifecycle adapter е отделен и не се подава на service factory |
| Transaction outcome lookup | Само собствен metadata receipt; не SQL/data read или повторно изпълнение |

Legacy raw connection contract остава за compatibility installations. Scoped
adapter връща transaction-bound facade с `execute`/`executemany`, bounded cursors
и обичайните row values, **не произволен raw connection**. Няма `executescript`,
caller `commit`/`rollback`, authorizer/progress-handler replacement, extension
loading, arbitrary UDF registration, backup/serialize или connection escape.
Cursor и session стават невалидни след приключване; nested transactions се отказват.

Runtime SQL не прави schema migrations. Отказват се DDL, `ATTACH`/`DETACH`,
`VACUUM INTO`, virtual tables/extension functions и опасни PRAGMA промени.
Допустимите readonly schema introspection PRAGMA са изричен allowlist с тестове,
не prefix/SQL regex. SDK migration/receipt tables не се променят с business SQL;
outbox writes минават през SDK helpers в същата транзакция. Authorizer трябва да
покрива и trigger/view actions. Заявката се отказва, не се връщат тихо NULL колони.

Readonly означава без business/schema/receipt writes и без writable `_connect()`
fallback. SQLite WAL reads може да изискват собствени coordination sidecars;
това се отделя от правото за промяна на business data. Липсваща/невъзстановена
база дава explicit unavailable, не се създава автоматично. Не се използва
`immutable=1` за жива променяща се база. [SQLite WAL](https://www.sqlite.org/wal.html#read_only_databases)

## 4. Transaction admission, revoke и изгубен резултат

1. Host adapter създава fresh transaction identity, точно mode/budget и текущ
   host boot/session identity. Подписаният platform transport удостоверява
   инсталацията; package payload не може да избира друг principal/namespace.
2. Core под съществуващия installation authority fence проверява exact current
   artifact/config/profile/grants/epoch, disable/revoke/recovery state и наличния
   budget. Записва durable metadata admission преди връщане на отговора.
3. Adapter приема единствено съответстващия admission за тази заявка/session и
   започва own DB transaction в останалия budget. Admission не се кешира за
   следваща транзакция и не се преиздава след uncertain response/restart.
4. Write session записва commit receipt в **същата** SQLite транзакция като
   business mutation/outbox. При rollback няма committed receipt. Core journal
   получава отделно bounded outcome metadata, не business SQL/parameters/results.

Budget е ограничен и от Core-verified enclosing operation deadline, когато има
такъв. Монотонният local deadline не се удължава от clock rollback, lock retry
или receipt lookup; host restart обезсилва неизползваните session admissions.
Повторена transaction identity с друго съдържание е conflict, не ново admission.
Receipt/journal retention е bounded; при запълване се отказва нова работа,
не се изтрива uncertain evidence, за да се допусне retry.

Core lock не се държи през IPC, application SQLite callback или application disk I/O. Не се взема Core
admission lock докато се държи SQLite write lock; completion reporting е след
освобождаването му. Забранени са connector/device/event dispatch и други platform
calls вътре в scoped DB session; намерението се записва в outbox, отделното
изпълнение отново изисква своите текущи права.

Revoke/disable, committed преди admission, печели. Вече admitted transaction
може да приключи в първоначалния си budget; revoke не отменя вече committed SQL.
Deadline се проверява при всяка facade операция, с SQL progress checks и преди
commit. Това не може да прекъсне произволен Python callback/blocking OS I/O;
WP5 supervisor isolation е отделна гаранция. Няма автоматично повторение.

Ако adapter доказано не е започнал SQL session, отказ/изгубен admission response
е `not_started`: Core approval/admission не е DB commit. След започната работа
confirmed rollback е failed/rolled_back. Crash, изгубен commit outcome или commit
error без сигурен rollback води до `execution_unconfirmed`, не invented success.
Core не извежда сигурен rollback само от липсващо completion съобщение.
Lookup показва собствен
committed receipt само след проверка на DB lineage, schema/receipt integrity и
историята на recovery. Липсващ receipt сам по себе си не доказва rollback след
restore/unknown lineage. SQL callback никога не се възпроизвежда от lookup.
SDK service може да прочете само owned outcome metadata след revoke; business
данни/export остават под отделната admin/human policy.

## 5. Ограничения без фиктивна дискова квота

Adapter проверява logical pages с actual page size и настройва SQLite page limit
преди write. База, която вече е над approved limit, не се изтрива/свива: runtime
writes спират, controlled recovery остава възможно. SQLite не позволява page
ceiling под текущия размер. [SQLite max_page_count](https://www.sqlite.org/pragma.html#pragma_max_page_count)

WAL/SHM/journal accounting се проверява при admission, SQL progress boundaries
и приключване. Над threshold се спира нова write работа и се докладва bounded
reason; guarded checkpoint/cleanup е host maintenance, не arbitrary package SQL.
Threshold **не** обещава, че единичен write не може временно да го надхвърли.
След successful commit overage не се представя като rollback: committed outcome
се пази и следващите writes остават paused. `journal_size_limit` не е hard peak
quota. [SQLite journal_size_limit](https://www.sqlite.org/pragma.html#pragma_journal_size_limit)

SQL/values/results/lock waits имат отделни bounds; limit failure преди commit
rollback-ва цялата session. TEMP usage не може да избира произволна директория;
за първия adapter няма package TEMP schema/UDF/virtual table support. Memory/temp
peak isolation не се обещава чрез row cap или in-memory temp настройка.
Backup/snapshot space се резервира от lifecycle policy отделно; file quota,
DB pages и host free space не се сумират като измислена обща гаранция.

## 6. Migration, startup, health и recovery са host lifecycle

Сегашният host извиква `migrate()` преди service factory. Не добавяме безусловно
live grant към този ред: първото adoption/health иначе се блокира. Новият adapter
разделя host lifecycle storage от service runtime storage:

- Migration само при защитено Core/runtime lifecycle действие за exact candidate,
  own namespace и target revision, след потвърден stop/quiesce и проверен DB/file
  preimage (или записана липса при fresh install). Това изисква explicit local
  install/activation authority; descriptor validation/review не стартира package
  import/migration code. Forward history и atomic migration semantics се запазват.
- Normal restart не предоставя maintenance mode на package context. Ако schema
  вече съвпада, host проверява metadata и стартира без нов migration callback;
  несъответствие без валидно lifecycle действие е recovery-required.
- Health може да провери само host-owned readiness/schema metadata без runtime
  grant. Не получава `internal` → writable DB bypass; service factory/health SQL
  изискват съответното runtime право. Apps с write-on-startup трябва да адаптират
  този код преди DB opt-in; не ги спираме чрез неявна миграция.
- Backup/export/restore използват explicit admin/lifecycle policy, consistent
  SQLite backup и ownership validation, не application-supplied maintenance flag.
  Защитава се coherent DB + sdk-files preimage; WAL не се изтрива от жива база.
- Restore/rollback променя recovery lineage/authority epoch и отменя in-flight
  admissions. Исторически grants/receipts не предоставят fresh authority или
  право за outbox replay; uncertain jobs/commands остават quarantined.

Съществуващият activation/backup механизъм се използва; тук не се обявява за
завършен WP3 staged lifecycle. Protected lifecycle admission/lineage adapter е
задължителна част от DB реализацията, не пропуск за по-късно. Unconfirmed stop,
snapshot/restore или drift оставя safe stopped/recovery-required state, без
автоматично връщане към по-широки права.

## 7. Rollout и finite acceptance

Няма bulk adoption/grants от manifest. Старите SDK 1.0–1.3 приложения запазват
явно означеното compatibility поведение. Наличните scoped files/commands не
доказват scoped SQLite: каталогът трябва да различава legacy DB от enforced DB.
За включване на relational enforcement се изисква exact supported declaration,
валидирано приложение, local review/apply и controlled lifecycle transition.
След този opt-in няма raw writable fallback при missing/stale grant.

Следващата реализация се разделя само на три ограничени части; те са acceptance
за тази DB задача, не нови milestone/work packages:

| Част | Задължителни проверки преди supported status |
| --- | --- |
| Request/review contract | Closed coherent limits; exact owner/artifact/schema/config binding; read/read_write selection; no foreign/path/file-grant substitution; canonical vectors; stale/revoke tests |
| Admission + SDK/host | Real signed transport; read denied write; write+outbox atomicity; all helpers gated; statement/row/value/deadline/busy/page bounds; SQL escapes/triggers/cursor lifetime; concurrent revoke/disable; lost ACK/crash/receipt lookup without replay |
| Lifecycle + recovery | First startup without self-grant; no migrate bypass on restart/health; migration failure restores coherent preimage; over-limit existing DB retained; preserved legacy APIs/data; restore/rollback fresh lineage/epoch; Linux SQLite/WAL tests and Standalone/Hub host flow |

Core persistence changes require Alembic migration + migration tests; adding SDK
receipt tables requires forward application-SDK metadata migration with rollback
tests. Текущата metadata стъпка използва наличните sealed JSON plan/grant records
без нов DB model или migration. Test records must distinguish
cooperative bounds, measured supported SQLite behavior and deferred OS isolation.
SQLite build/version and relevant vendor fixes are recorded in host acceptance,
not inferred from Python version; no installer dependency change is made here.

## Проверени source точки

- [Storage SDK](../three_mm_application_sdk/__init__.py) и
  [migrations/outbox tests](../three_mm_application_sdk/tests/test_storage.py).
- [Storage descriptor](../three_mm_protocol/application_extension.py),
  [host startup](../three_mm_runtime/application_host.py),
  [activation DB/file rollback](../three_mm_runtime/application_activation.py).
- [Installed authority resolver](../backend/services/application_authority_sources.py),
  [authority management](../backend/services/application_authority_management.py) и
  [signed platform dispatcher](../backend/services/application_platform.py).
- [Private files](EXTENSION_PLATFORM_V2_PRIVATE_FILES.md): отделен ресурс и limits.
- [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html): connection
  SQL restriction, не отмяна на Core grant при вече compiled statement.

## Реализирана първа стъпка — declaration validation, не DB authority

- Typed closed profile с exact integer version, coherent strict limits и SDK 1.3
  requirement; старите приложения без `relational` запазват SDK 1.0–1.3 support.
- Real ZIP validation използва строгия raw parser. Advisory package review
  показва `storage:relational` отделно от legacy `own_storage` и private files,
  включително променени/премахнати лимити. Това **не е** exact grant review/apply.
- В първата стъпка installed authority resolver отказваше relational authority.
  Следващата metadata стъпка по-долу добавя exact resolution/review; runtime
  activation и SQL admission остават отказани.
- Activation отказва профила преди paths/keys, stop или package code. Host също
  отказва relational metadata преди import, migrations, SQLite или file worker.
  Няма падане към стария writable SQLite adapter.

Тестовете са в [protocol declarations](../three_mm_protocol/tests/test_application_relational_storage.py),
[ZIP/review/installed denials](../backend/tests/test_application_relational_declarations.py)
и [activation/host guards](../three_mm_runtime/tests/test_application_relational_gate.py).
Проверка: **303 passed** под Linux — трите нови файла и целевите съществуващи
protocol/package/review/authority-management/activation/file-host/SDK storage
проверки. Това не е пълният release suite или live Standalone/Hub acceptance.
Тази първа стъпка сама не изпълнява целия „Request/review contract“ acceptance.

## Втора стъпка — exact installed review / approve / apply / revoke metadata

- Един и същ resolver/coordinator изгражда собствен DB ресурс от валидирания ZIP:
  owner/incarnation, package и service digests, schema revision, migration
  entrypoint, пълната декларация и фиксирания Core `owned_sqlite_request_v1` профил.
  Configuration HMAC, recovery generation и trust/policy revisions остават в
  общия sealed binding. Не се отваря application DB или package migration code.
- Вътрешни subject/evidence/context/selection **v5**; v1–v4 не получават нови
  scopes или променени canonical fingerprints. Това не променя SDK **1.3**.
- `read_write` е цял профил: read + write, без half-policy или downgrade.
  File grants и DB grants са отделни. Няма wildcard, foreign/path resource или
  caller-supplied limits/approval в административната заявка.
- Съществуващият admin-only API приема избраните DB scope IDs; exact resources
  идват от Core. Local native attestation, актуален admin/session, отделно
  approval/apply, disabled first adoption, seals, audit и idempotent historical
  receipts се запазват. Approve не създава grant; apply не изпълнява SQL.
- Новият профил не може да бъде инсталиран/стартиран преди runtime/lifecycle
  adapter. Activation/host guards остават; `native_activation` и generic
  `effect_admission` също отказват relational execution. `inspect` връща
  `grant_effective=false` и `runtime_blockers=["relational_runtime_unavailable"]`.
  Каталогът рекламира само `core_admin_review_metadata_only`, не DB runtime.

Проверки: [exact v5 policy/context vectors](../backend/tests/test_application_relational_authority_context.py)
и [реален ZIP/admin API/sealed lifecycle](../backend/tests/test_application_relational_review_api.py).
Installed fixture моделът подава действителен валидиран artifact pin; grants се
създават през нормалните административни операции, не SQL inserts. Това **не е**
first-install/startup, UI integration, transaction admission или live acceptance.
Промени на лимити/schema/configuration/recovery/key/session/review clock отказват
approve/apply; предишна native attestation не приема нов package digest.

Linux regression: **471 passed, 1 skipped** (non-POSIX refusal test), плюс
**1 passed** за фиксирания v5 canonical vector. Обхватът включва новите DB
declaration/review/host guards и съществуващите v1–v4 context/policy/sources/
subjects/management/file API договори. Това не е пълен release suite или live тест.

Следват transaction admission + SDK/host и lifecycle/recovery. Няма relational
SQL executor или DB model/migration; legacy own DB runtime е непроменен.
Няма live действие, commit, push, deployment или release.

## Трета стъпка — вътрешен bounded SQLite engine, без runtime включване

[ApplicationScopedStorage](../three_mm_application_sdk/scoped_relational.py) е
вътрешна реализация, не top-level SDK export или избран host adapter. Няма нов
Core SQL endpoint, migration или application receipt table. Старият
`ApplicationStorage` и позициите на `ApplicationContext` са непроменени.

- За всяка транзакция engine-ът изисква отделно host admission преди SQLite I/O.
  По подразбиране то липсва и всички DB helpers отказват. Проверяват се fresh
  transaction ID, mode, declaration/schema fingerprint и монотонен deadline,
  който не може да се удължи. Това **не е** реализация на подписаното Core
  admission: тестовият callback доказва реда/отказите, не текущ sealed grant,
  principal/artifact/configuration/recovery/boot binding или durable journal.
- Отваря само съществуващата own `state.sqlite3` чрез `mode=ro`/`mode=rw`, без
  `immutable=1`, mkdir, нова база или runtime migration. Schema mismatch отказва
  работа; symbolic links/non-regular/multiply linked DB/sidecars се отказват.
  Това не обещава защита от filesystem races или злонамерен native код.
- `read_transaction`, `transaction`, `status`, `due_outbox`, `update_outbox` и
  `enqueue_outbox` използват еднакви admission/bounds. Business data + outbox са
  atomic; helper-ът не взема второ admission докато държи SQL write lock. Outbox
  приема само own active write session. Няма автоматичен outbox drain/replay.
- SQL authorizer отказва schema/transaction control, ATTACH/DETACH, TEMP,
  virtual/shadow tables и unsafe PRAGMA/functions; trigger writes към SDK tables
  също са отказани. Readonly introspection и built-in functions имат явен allowlist.
  VACUUM е отказан и от винаги активната SQLite transaction. Няма raw connection,
  cursor connection, caller commit/rollback, scripts или replacement hooks в facade.
- UTF-8 statement/value bounds, aggregate result rows/bytes, streaming batches,
  busy wait в оставащия монотонен budget, progress checks и pre-commit deadline.
  Прихваната SQL/limit/input-batch грешка оставя session failed; частичен batch
  не се commit-ва. Cursor/session отказват след приключване.
  Namespace, declaration/schema и session mode/limits са readonly в поддържания
  API; не могат да се подменят с обикновено assignment след admission.
- Профилът на engine допълнително ограничава параметрите до 999, общите parameter
  bytes за един statement до `max_result_bytes` и compound SELECT до 50 terms.
  Result accounting включва по един framing byte на стойност; empty/NULL cells
  не са unbounded. SQLite LENGTH ceiling е `max(4096, max_result_bytes)` за engine
  allocations/schema metadata; facade прилага exact per-value limit отделно.
  Тези ограничения трябва да останат explicit в final reviewed adapter profile;
  не са silent промяна на одобрените declaration values или hard memory quota.
- Логически SQLite page ceiling с actual page size; WAL/SHM/journal threshold
  спира writes без изтриване, read inspection остава възможен. Successful commit
  не се преименува на rollback заради последващ sidecar overage. След неясен commit
  outcome няма автоматичен retry или измислен success/rollback.
- SDK platform calls са отказани в текущия scoped SQL execution context преди
  socket I/O. Scoped file mutations се отказват преди uncertainty handling, за
  да не се представя доказано незапочнала операция като изгубен write result.
  Това не спира package-created threads, raw sockets или произволен Python I/O — WP5.

Тестове: [реален SQLite engine](../three_mm_application_sdk/tests/test_scoped_relational.py),
с legacy-prepared disposable DB и explicit admission test double. Тестовата
подготовка през стария migration helper **не е** production lifecycle authority.
Загубен резултат след действителен commit се симулира без повторение на callback.

Последна целева проверка: **223 passed** под Linux (SDK suite, relational protocol
и activation/host guards), плюс **41 passed** за existing signed private-file
execution и exact relational review/apply/revoke API. Общо **264**, не пълният
release suite или live deployment. Среда: Ubuntu/WSL x86_64, Python **3.14.4**,
SQLite **3.46.1**. Под Windows/SQLite **3.50.4** SDK/protocol regression също мина
(**195 passed, 16 skipped** за POSIX file semantics, преди последните два API
immutability/empty-batch tests). Production Linux/Pi и реален relational host
flow не се извеждат от тези резултати. Няма промяна на SDK version или runtime
активиране заради наличието на engine тестовете.

**След третата стъпка „Admission + SDK/host“ не беше приключен:** signed/durable Core
admission, exact current authority + operation deadline/host session binding,
atomic DB commit receipt, bounded Core journal, completion/lookup след unlock,
concurrent revoke/disable и recovery lineage. След това protected migration/
startup/health/recovery интеграцията и Standalone/Hub acceptance. Activation,
generic relational effect admission и `native_activation` остават блокирани;
каталогът не рекламира enforced DB runtime. WP4 остава отворен.

## Четвърта стъпка — вътрешен Core admission journal и atomic own-DB receipts

[Core coordinator](../backend/services/application_relational.py) използва
действителния installed ZIP resolver и `_require_grant`, Core key → authority
guard → application fence. Artifact/configuration/native trust/grant/epoch се
проверяват отново за всяка транзакция. ZIP I/O е преди leases; application SQL,
parameters, business values и physical paths не се изпращат на Core.

- Fresh permit се записва в съществуващите **sealed Action records** и commit-ва
  преди връщането. Повторен transaction ID винаги отказва нов permit, дори при
  същото съдържание. Lookup връща само исторически outcome, никога permit. Липсващ
  journal/completion остава `execution_unconfirmed`, не доказателство за rollback.
- Вътрешният [closed wire format](../three_mm_application_sdk/relational_wire.py)
  подписва purpose-separated admission/receipt/lineage metadata с instance
  transport key. Permit обвързва exact profile и sealed subject digest,
  grant revision/epoch, instance, runtime nonce, DB lineage и recovery/boot
  generation. CLOCK_BOOTTIME deadline е минимумът на original transaction budget
  и trusted enclosing-operation deadline; local SDK budget не се удължава.
  Scoped engine проверява и абсолютния boot deadline при SQL/progress/commit,
  така че suspend не удължава допуснатата работа.
- Core journal има лимит **4096 Action records за installation**, включително
  останалите административни записи. При запълване отказва нов admission, без
  изтриване или eviction на uncertain evidence. В тази стъпка няма автоматичен
  GC/retention policy. Read admission също е durable metadata, не business write.
- [Receipt store](../three_mm_application_sdk/relational_receipts.py) добавя
  forward SDK metadata v1: `three_mm_relational_lineage` и
  `three_mm_relational_commits`. Подготовката изисква вече започната отделна
  lifecycle transaction; не започва/commit-ва сама, не се извиква от стария
  `ApplicationStorage.migrate` и не променя legacy DB автоматично. Повторение с
  друга lineage/key/schema или непълна/подменена metadata структура отказва.
  Tests доказват atomic preparation rollback и запазване на business data.
- Write receipt се подписва и вмъква в **същата** SQLite transaction като
  business mutations/outbox, преди commit. SDK authorizer отказва business SQL
  writes към тези tables; privileged receipt insert допуска само own insert,
  без trigger writes към бизнес/други SDK tables. Receipt schema/lineage/key и
  expected migration revision се валидират преди callback. Лимитът е
  **4096 committed receipts**; full journal отказва нови writes преди callback,
  без eviction. SQLite page ceiling включва receipt tables.
- Optional completion callback се изпълнява след connection close и reset на
  scoped SQL context. Изгубен completion ACK дава `execution_unconfirmed` и
  transaction ID; own receipt lookup доказва committed outcome без повторение
  на callback или нов admission. Липсващ receipt връща unknown, не rollback.
- Core приема само подписан exact committed receipt за оригиналния write
  admission и schema/lineage. Няма service-authored `rolled_back`/`not_started`
  операция, която да изчиства uncertainty. Completion на вече admitted работа
  е допустим след grant revoke; recovery/key/incarnation/host-session drift
  отказва старото evidence. Това не разрешава нов SQL или outbox replay.

**Границата е изрична:** `_HostTransactionContext` е вътрешна trusted Core
dependency, не authentication proof сам по себе си. Future protected host
resolver трябва да установи runtime nonce/DB lineage/current authority и
enclosing invocation deadline. Не се десериализира от manifest/service payload.
Няма нов public HTTP/platform action или top-level SDK export; gateway отказва
`relational.admit/complete/status`. Production activation/host/native guards и
каталогът остават unchanged/blocked, докато тази dependency и recovery adapter
не са действително реализирани и проверени.

HMAC потвърждава reviewed-native transport metadata; не е независима hostile-code
SQL attestation. Native package има свои Python/file възможности — WP5. Receipt
lookup със съвпадаща lineage сам не открива restore на по-стара DB от същата
lineage: protected restore/rollback **трябва** да сменя lineage/epoch. Това още
не е wired. Transport-key rotation също отказва старите receipts; migration/
recovery трябва изрично да координира rekey/историческо evidence, без self-repair.

Тестове: [actual sealed Core grants/admission](../backend/tests/test_application_relational_admission.py),
[SQLite receipts](../three_mm_application_sdk/tests/test_relational_receipts.py) и
[closed wire/signatures](../three_mm_application_sdk/tests/test_relational_wire.py).
Core fixture използва реални ZIPs/native attestations/admin approve/apply, не
SQL-inserted grants; verified host context се подава директно **само в fixture**.
Integrated test свързва Core permit → verifier → SQLite business/outbox/receipt
→ Core completion. Това е internal integration, **не реален Unix transport,
first activation или deployed Standalone/Hub acceptance**.

Няма промяна на Core DB model/schema; journal използва наличния sealed model,
затова не се добавя Alembic migration. SDK metadata preparation е отделна
forward/rollback-tested стъпка. SDK остава **1.3**. Следват protected host
session/transport, migration/startup/health/recovery и общото Standalone/Hub
приемане; WP4 не се затваря с тази вътрешна стъпка.

Проверка под Ubuntu/WSL, Python **3.14.4**, SQLite **3.46.1**: **332 passed** за
SDK suite, relational protocol/activation guards, Core admission/review и
existing signed private-file execution. След финалните suspend-aware deadline
и handoff validations: **154 passed** за engine/receipts/wire/Core admission
(повторени целеви проверки, не 154 допълнителни уникални теста). Покрит е и revoke,
който commit-ва докато admission още валидира ZIP извън authority lock. Това не е
пълният release suite, frontend build, deployed host или live acceptance.
Няма commit, push, deploy или release.

## Пета стъпка — prepared-host сесия и реален Unix metadata resolver

[Host session reader](../three_mm_runtime/application_relational_session.py)
чете fixed `relational.json` от root-protected instance, **не** от application
configuration/manifest или `data`. Това е вътрешна част за следващия lifecycle
coordinator; текущият production installer **не публикува** такъв запис и няма
ръчна инструкция за заобикаляне на activation gate.

- Closed signed record обвързва instance, Core-owned owner digest, exact package/
  service/profile/configuration digests, schema, lineage и recovery generation.
  Reader проверява root owner (UID **0**), липса на group/world write, regular
  single-link files, real namespace/release directories и реалния wheel digest.
  Unresolved activation/database rollback marker отказва normal readiness.
- Startup отваря само existing own SQLite в `mode=ro`, `query_only` snapshot;
  проверява SDK receipt schema/lineage/key и target migration revision с bounded
  progress deadline. Няма migration import/callback, DB creation, key/lineage
  repair или application table query. SQLite WAL coordination sidecars могат да
  се променят при read; това не означава business/SDK metadata write authority.
- Fresh nonce/boot identity се създава за всяка host сесия. Отделен serial worker
  на fixed `run/relational.sock` (**0660**) обслужва **само** празна `context`
  заявка през подписан transport. Няма setter за lifecycle/invocation/deadline,
  SQL endpoint или maintenance flag. Заявките/отговорите са bounded **8 KiB**,
  без duplicate keys, non-finite values и unknown fields; IPC има timeout.
- Core проверява hello срещу своите actual installed artifact/configuration/
  owner/profile/recovery sources и текущия sealed read grant. Вътрешният
  `prepare_host_invocation` издава purpose-separated signed ticket за declared
  operation/audience, с deadline от **Core descriptor timeout**, максимум **30 s**.
  Той е dependency **след** наличната route/actor/payload authorization, не нов
  invocation endpoint или заместител на user access checks. Ticket сам не допуска
  SQL. Host boundary го сравнява с действителния handler operation ID.
- Host пази само един активен invocation; exact duplicate/foreign/stale ticket
  отказва. Replay set е bounded **128** unexpired entries, без eviction за нова
  работа при full set. Restart променя nonce и старият ticket/permit не се ползва.
  Factory/health извън такъв invocation не получават implicit SQL admission.
- `admit_host_transaction` вече извежда `_HostTransactionContext` от реалния
  worker и current Core authority, не от service JSON. След IPC прави новата
  durable admission проверка; revoke/disable/drift преди commit отказват.
  Transaction budget започва при Core admission request (преди IPC/ZIP I/O),
  отделно от operation start; deadline е ограничен и от enclosing ticket.
  Нито hello, нито ticket се ползва като cached grant за следваща транзакция.
- Host-selected permit expectations идват от prepared/session/ticket state,
  не се копират от получения permit, за да се „потвърди“ самият той.
  `record_host_commit` проверява live metadata и оригиналния signed receipt
  **след SQL unlock**, без new grant/admission, включително след grant revoke.
  Expired, но още активен invocation може да докладва committed receipt; не
  може да започне SQL или да удължи budget. Ending/restarting invocation не
  превръща неизвестния outcome в rollback и не възпроизвежда callback.
- Host IPC е извън Core DB/key leases. Worker не отваря SQLite по време на
  metadata lookup и не се обажда обратно в заетия service socket.

Codec границата е изрична: lifecycle/configuration/profile wire digests използват
fixed metadata JSON codec; owner/subject digests, изведени от Core, запазват
съществуващия private typed authority codec. Не променяме canonical v1–v5 review
fingerprints или SDK **1.3**. HMAC/purpose separation и root ownership не са
hostile native Python isolation; mutable namespace races/raw I/O остават WP5.

Тестове: [real Unix session/readiness](../three_mm_runtime/tests/test_application_relational_session.py)
и [actual installed grants + Core resolver + own SQLite](../backend/tests/test_application_relational_host.py).
Fixture подготвя DB/receipt tables/lifecycle record изрично и използва actual ZIP,
native attestation и admin approve/apply. Unix socket, metadata signatures, Core
resolver, bounded engine и atomic SQL/outbox/receipt са реални. **Това не е**
production activation/service dispatch, protected migration/publication/restore
coordinator или live Standalone/Hub acceptance. Root Linux run проверява UID 0;
unprivileged CI fixture използва отделна disposable owner policy, не production
configuration override.

Production activation/host/native guards, unsupported platform relational
actions и каталогът остават **blocked**; няма public SDK export/endpoint или
нов Core DB model/Alembic migration. Следващата ограничена част е coherent
protected lifecycle preparation/publication/rollback/recovery с fresh lineage и
key coordination; после включване на тези dependencies в нормалния host
dispatch/SDK transport и общото Standalone/Hub acceptance. WP4 остава отворен.

Последна целева Linux проверка (Ubuntu/WSL, root disposable fixtures, Python
**3.14.4**, SQLite **3.46.1**): **245 passed**. Включва session/readiness и Core
resolver, original admission/receipts/wire/engine, production guards и legacy
host/file-host/activation regression. Покрити са atomic business + outbox +
receipt commit, completion след revoke и изгубен completion ACK без replay.
Black/isort и Git whitespace check минават. Това не е пълният release suite,
frontend build, реален production lifecycle или live deploy. Няма commit/push/
release; SDK остава **1.3**, Core версията е непроменена.

## Следваща lifecycle част — проверен SQLite preimage и migration rollback

[Database snapshot helper](../three_mm_runtime/application_database_snapshot.py)
е свързан със **съществуващия** activation DB/files checkpoint. Няма втори
activation coordinator, нов restore endpoint или application maintenance flag.

- След потвърден stop/quiesce се копира само existing own SQLite с `mode=ro`
  и SQLite backup API, включително committed WAL pages. При липса не се създава
  source DB; записва се изрична absence evidence в fixed `database.json`.
- Closed, bounded manifest обвързва presence, size и SHA-256 на затвореното
  preimage. Snapshot и source/sidecars трябва да са regular single-link files.
  Symlinks, hardlinks, orphan source sidecars и непосочени snapshot sidecars
  отказват; неизвестен WAL не може да override-не проверените main DB bytes.
- SQLite copy/quick-check има **10 s cooperative deadline**, без infinite busy
  retry. Partial snapshot остава в rollback директорията без complete manifest
  и не се използва повторно. Това не е твърд filesystem I/O timeout или disk quota.
- Преди DB/files rollback да смени който и да е namespace, DB evidence се
  проверява. Restore подготвя проверено отделно копие; candidate DB/WAL/SHM/journal
  се отделят като evidence, вместо WAL да бъде изтрит преди успешно staging.
  Preimage, staged copy и candidate се пазят при mid-switch failure. Service
  остава спрян, marker блокира нов lifecycle/replay; това не е multi-file atomic
  commit или автоматично възстановяване след crash.
- Реални forward SDK migrations в disposable activation test доказват rollback
  на вече committed междинна миграция плюс последващ failure: business tables,
  schema history, outbox и sdk-files се връщат към общия preimage. Тестът използва
  legacy migration callback през candidate health test double; **не** доказва
  protected first-adoption migration authority или production scoped host.
- Legacy activation отказва при наличен `relational.json` **преди** paths/keys/
  stop. Не допуска неявен downgrade към writable legacy SQLite и не препубликува
  стар lineage като fresh authority. Record сам по себе си не предоставя grant.

Protected relational lifecycle admission, migration execution/publication,
restore с **fresh lineage/authority epoch**, key coordination и normal host/
SDK dispatch остават задължителният остатък. Snapshot helper не ги замества.
Activation/host gates остават блокирани за relational декларации; SDK **1.3**
и Core версията са непроменени. Няма live restore, deployment или release.

Тестове: [database evidence и activation migration rollback](../three_mm_runtime/tests/test_application_database_snapshot.py).
Финална целева проверка: **301 passed** под Ubuntu/WSL, root disposable fixtures,
Python **3.14.4**, SQLite **3.46.1**. Включва existing activation/private-files
rollback, relational guards, prepared-host/Core admission и SDK engine/receipts/
wire regression. Първите **69 passed** са повторен поднабор, не допълнителни
уникални тестове. Black/isort и Git whitespace check минават. Това не е пълен
release suite или live Standalone/Hub acceptance. Няма commit/push/release.

## Следваща lifecycle част — initial preparation на съществуваща точна схема

[Private Core coordinator](../backend/services/application_relational_lifecycle.py)
и [protected helper](../three_mm_runtime/application_relational_preparation.py)
доказват ограничен initial adoption поток. Това **не е** публична install/SDK/
helper операция и не е разрешение за production relational runtime.

- Отделно, изрично потвърждение от текущ local admin/session, след exact installed
  native review и resource approve/apply. Инсталацията трябва да е disabled.
  Resource grant сам не започва подготовка. Core издава signed, closed, **one-use**
  ticket за точния owner/artifact/configuration/profile/schema/grant/epoch/
  recovery/boot, с максимум **5 min CLOCK_BOOTTIME**. Ticket няма path или
  maintenance/migration флаг. Записва се преди връщане в наличния sealed Action
  journal; повторна заявка не преиздава ticket. Лимитът е 4096 записи без eviction.
- Core проверява отново текущите sources, human session, native trust и grants
  при authorize/begin/check/finish. Begin записва `execution_unconfirmed` преди
  SDK SQL; finish приема само exact purpose-separated signed metadata receipt.
  Историческо повторение на finish не изпълнява helper-а и не позволява нов start.
  Core leases не се държат през helper/application I/O; helper callback никога
  не се прави докато е отворена application SQLite write transaction.
- Root helper използва **existing release-mutation/runtime locks**, проверява
  root-protected key/instance/release metadata и own data/run directories.
  Няма създаване/поправка на key, database, чужд namespace или permission bypass.
  Verified stop/quiesce предхожда existing DB + sdk-files preimages и SQL.
- Подготвят се само двете фиксирани SDK receipt tables в **вече съществуваща**
  own SQLite, чиято target migration revision съвпада. Не се изпълняват package
  Python imports, factory, migration callback или health code като root.
  Липсваща/несъвпадаща business схема се отказва; business migrations остават
  за отделен непривилегирован maintenance процес. Съществуващи/частични receipt
  tables или `relational.json` са explicit recovery, не автоматично relineage/rekey.
  Fixed SDK metadata write е отделна human lifecycle authority, не runtime write
  grant; приложението може да е декларирало read-only business достъп.
- SQLite използва existing-only URI, trusted-schema off, без extension loading,
  logical page ceiling, bounded busy/progress/boot deadline и auxiliary pause
  threshold. Това са cooperative bounds, не OS disk/memory quota. Business data,
  schema history, outbox и sdk-files не се изменят от подготовката.
- Wheel-ът се проверява като bytes, без import. Shared activation metadata builder
  запазва legacy формата; helper добавя validated relational declaration и
  публикува signed root-owned `relational.json`. Записите и SDK DB metadata се
  проверяват след публикацията. Успехът е **`prepared_not_started`**; няма enable,
  restart или factory/health grant. Normal reader продължава да отказва pending
  rollback marker, без нов bypass режим.
- При failure преди completion attempt, изменените SDK DB metadata/active pointer
  се връщат от проверения DB/files preimage. Service остава спрян, checkpoint и
  Core uncertainty се пазят за review; не се изчиства автоматично journal.
  При unconfirmed stop не се твърди, че service е спрян; SQL не започва и няма
  автоматичен restart, snapshot reuse или нов lifecycle опит.
  **След започнат finish**, изгубен ACK може да следва committed Core receipt:
  candidate + snapshot + marker се запазват, без rollback/replay. Cleanup failure
  също не стартира service-а. Това не е multi-file atomic filesystem transaction.

Проверки: [actual grants + existing-schema preparation](../backend/tests/test_application_relational_preparation.py).
Fixture използва real ZIP/admin sessions/native review/approve/apply; няма
SQL-fabricated grants. Root helper cases работят само в disposable Linux paths,
без ownership override в production; non-root CI ги маркира skipped явно.

**Остава:** fresh install/business migration чрез непривилегирован worker;
upgrade на вече prepared DB; restore/rollback с fresh lineage/authority epoch;
transport-key coordination и explicit recovery на pending checkpoints; normal
dispatch/SDK wiring и Standalone/Hub acceptance. Production activation/host/
native/platform guards и каталогът остават blocked. Няма new public SDK export,
Core DB model/Alembic migration или промяна на SDK **1.3**/Core версията. WP4 не
се затваря с този private existing-schema поток.

Финална целева Linux проверка: **334 passed** (33 нови preparation проверки +
301 existing activation/snapshot/private-files/host/relational admission/session/
engine/wire/receipt проверки). Среда: Ubuntu/WSL root disposable fixtures,
Python **3.14.4**, SQLite **3.46.1**. Първите 21 preparation теста са повторен
поднабор, не още уникални тестове. Black/isort и Git whitespace check минават.
Това не е пълният release suite, frontend build или live Standalone/Hub тест.
Няма commit, push, deploy или release.

## Initial schema / forward business migrations — отделен non-root worker

[Core coordinator](../backend/services/application_relational_lifecycle.py) добавя
отделно `issue_migrated_schema_preparation`, с изрично потвърждение за изпълнение
на **точния migration code**, не само за SDK metadata. Използва текущите local
admin/session/native review/installed ZIP/exact grants и същия sealed Action
journal. Няма нов public HTTP/helper/platform endpoint или SDK export.

- Closed ticket `prepare_migrated_schema` има отделен signing purpose и digest
  на fixed worker policy. Metadata-only ticket не може да се преобразува в
  migration authority; replay, чужда/изтекла/отнета authority или променен worker
  profile отказва. Begin се записва преди стартирането на процеса.
- [Preparation helper](../three_mm_runtime/application_relational_preparation.py)
  запазва release/runtime locks, confirmed service stop, проверения DB/files
  preimage и exact wheel bytes. Може да подготви първа схема при **доказана липса
  на DB в вече създаден own namespace**, или forward legacy schema преди първо
  relational adoption. Това не създава instance/service account/key и не е
  завършен production first install. Вече prepared DB/частични receipt metadata
  все още отказват и изискват отделна upgrade/recovery реализация.
- [Migration worker](../three_mm_runtime/application_relational_migrations.py)
  е реален отделен POSIX процес с exact non-root application UID/GID, без
  supplementary groups, inherited credentials/env/Core tokens или transport key.
  Exact wheel imports и migration factory/callback са само там; service factory
  не се импортира. Използва isolated Python startup и фиксирания installed runtime,
  без shell, caller executable/PYTHONPATH или application-supplied maintenance flag.
- Fixed private policy: максимум **128 migrations**, **30 s CLOCK_BOOTTIME** за
  целия worker (включително import/factory), 512 MiB `RLIMIT_AS`, bounded CPU и
  per-file `RLIMIT_FSIZE` = DB limit + auxiliary threshold. Тези guardrails не са
  hostile-code/process-tree isolation, обща disk quota или твърд filesystem I/O
  timeout. Бъдеща промяна на policy изисква нов digest/точен ticket.
- Reuse на SDK forward history и outbox compatibility, без промяна на legacy
  `ApplicationStorage.migrate`. Всяка migration е atomic; при failure на следваща
  migration helper връща **общия** проверен preimage, включително първоначалната
  DB absence. Няма replay на callback, repair на lineage или автоматичен restart.
- Callback получава bounded SQL facade със същите statement/value/row/busy/page/
  deadline bounds, плюс own business DDL. Transaction control, ATTACH/TEMP/virtual
  tables, extension loading/unsafe PRAGMA и SDK metadata writes са отказани;
  ALTER към reserved SDK name се проверява и след DDL. Прихваната SQL/limit грешка
  оставя transaction failed, вместо partial commit. Platform/file dispatch е
  отказан в worker context; raw Python I/O остава reviewed-native/WP5 граница.
- Helper проверява отново current Core authority след **затворени** worker/SQL,
  преди fixed SDK receipt metadata и protected publication. Успехът остава
  `prepared_not_started`, не runtime authority. Lost finish ACK пази migrated
  candidate + backup + marker, без rollback/replay. При **непотвърден worker stop**
  не се връща snapshot върху потенциално жива база; evidence остава за review.

Проверки: [real signed lifecycle + non-root migrations](../backend/tests/test_application_relational_migrations.py).
Покриват initial absence/forward history/data/outbox, действителни UID/GID,
отделно потвърждение/подпис/one-use/current grant, SQL escapes и bounds, factory
timeout, rollback на committed междинна migration, revoke след worker, lost ACK
и explicit unconfirmed stop. Root-only cases са disposable Linux fixtures;
няма production ownership override, live data или migration code като root.

Остават full first-install setup, prepared-DB upgrade, fresh-lineage/epoch/key
recovery, explicit pending-checkpoint resolution и normal host/SDK dispatch;
след тях Standalone/Hub acceptance. Production guards, каталогът, SDK **1.3** и
Core версията са непроменени. WP4 остава отворен; няма commit/push/deploy/release.

Linux проверки: **103 passed** за lifecycle/preparation, wire, legacy SDK storage
и production guards; **34 passed** за разширения migration файл. След финалната
защита срещу reaped/reused worker PID: **7 passed** (целеви повторен поднабор,
включително новия PID regression test). Общо **35 нови migration cases** са
проверени; резултатите се припокриват и не се сумират като 144 уникални теста.
Среда: Ubuntu/WSL root disposable fixtures, Python **3.14.4**, SQLite **3.46.1**.
Black/isort и Git whitespace check минават. Това не е пълен release suite,
frontend build или live Standalone/Hub тест.

## Explicit recovery — приемане на проверен published candidate

[Private Core recovery](../backend/services/application_relational_recovery.py) и
[root helper](../three_mm_runtime/application_relational_recovery.py) реализират
**един ограничен recovery избор**: приемане на точната подготвена база след
успешна публикация, включително изгубен preparation finish ACK преди/след Core
commit. Това не е general backup restore, избор на произволен snapshot, prepared
schema upgrade, key rotation или replay на migration/external operation.

- Ново изрично потвърждение от current local admin/session, exact installed
  native review и current applied grant. Source се извежда от наличния sealed
  preparation Action; caller не задава lifecycle record, DB path или recovery
  generation. Старият ticket може да е изтекъл; **не се подновява**. Издава се
  отделен closed, one-use recovery ticket/purpose, максимум 5 min CLOCK_BOOTTIME,
  с source lifecycle digest и fresh database lineage.
- При issue Core веднага сменя application authority epoch, изисква нов review
  и обезсилва physical command authorization чрез съществуващия lifecycle
  invalidator. Съществуващите bounded relational Action records от старата
  lineage получават sealed recovery fence; техният original permit/outcome/
  receipt остава evidence. Стар context не може да потвърди стар admission след
  recovery, дори след ново apply. Това **не** е отмяна на вече committed SQL и
  не обявява uncertain работа за failed/committed. Ordinary revoke completion
  behavior се запазва. Не се променя Core-wide recovery generation или други apps.
- Един source се резервира за точно един recovery request; повторна заявка не
  връща ticket. Всеки authorize/begin/check/finish проверява current actor,
  exact source/profile/config/native/grant-record/epoch/key/boot/generation.
  След issue старият grant е binding/evidence, не runtime authority. Успехът
  остава disabled/review_required/prepared_not_started, без enable/restart.
- Helper използва същите release/runtime locks, protected namespaces/key,
  действителен service UID/GID и confirmed stop. Само exact published
  active.json + signed relational.json + wheel digest + original receipt schema
  и lineage се приемат. Един matching preparation marker е допустим само в
  completion_unconfirmed/prepared_not_started; pending migration, unconfirmed
  worker stop, partial publication, unknown/overlapping markers и key drift
  **отказват**, вместо да се изчистят с checkbox.
- Преди fixed SDK SQL се записва blocking recovery marker и coherent verified
  DB/files preimage плюс previous root metadata. Няма package import/factory,
  migration callback, произволен SQL или application maintenance flag.
  SDK metadata transaction сменя само lineage payload. Exact schema, подписи
  и bounded commit journal (4096) се проверяват; business tables, schema history,
  outbox, sdk-files и original commit receipts не се променят. Старите receipts
  запазват original lineage и не могат да acknowledge-нат new-lineage работа.
  Full receipt journal не се изпразва; новите writes остават paused при full cap.
- След SQL unlock Core recheck, exact protected publication и signed recovery
  finish предшестват освобождаването на marker. Evidence директориите се
  **архивират в същия protected instance**, не се изтриват. Readiness не получава
  bypass. Stop/SQL/publication/ACK/archive failure пази evidence и блокира start;
  няма автоматичен rollback върху possibly committed lineage или replay.

Следващата част по-долу добавя само readonly confirmation на напълно публикуван
прекъснат recovery. Partial publication/unconfirmed stop, restore на
verified preimage/backup с нова lineage, full first-install setup, prepared-DB
upgrade, rekey/global-generation coordination и production host/SDK dispatch
остават. Historical evidence не става ново право за outbox drain или external
POST. Това е reviewed-native cooperative lifecycle, не WP5 isolation. Production
guards/каталогът, Core version и SDK **1.3** остават непроменени; няма public
endpoint/export, ORM/Alembic model, live действия или release.

Проверки: [actual Core + root/SQLite recovery](../backend/tests/test_application_relational_recovery.py)
с real installed ZIP/admin/native/approve/apply, purpose/one-use/epoch fences,
preserved data/receipts, lost preparation/recovery ACK, authority/namespace/key
drift и отказ при неясен worker. Linux targeted regression: **159 passed**, от
които **28 recovery cases**, плюс съществуващите admission/host/preparation,
wire/receipts и production guard проверки. Изпълнено в disposable WSL Ubuntu
fixtures с actual root helper, Python **3.14.4** и SQLite **3.46.1**. Black/isort
и whitespace проверките минават. Това не е full release/live acceptance; няма
commit, push или промени по работеща инсталация.

## Interrupted recovery — explicit readonly confirmation

[Private Core coordinator](../backend/services/application_relational_recovery_confirmation.py)
и [root helper](../three_mm_runtime/application_relational_recovery_confirmation.py)
приключват **вече напълно публикуван** accept-candidate recovery, когато finish
request/response е изгубен преди или след Core commit. Това не повтаря fixed SDK
SQL, не връща snapshot, не сменя отново lineage/key и не пуска package code.

- Отделна explicit current local-admin/session confirmation, exact installed
  native review и sealed grant-record binding, disabled/review_required instance.
  Fresh closed one-use ticket/purpose, максимум 5 min CLOCK_BOOTTIME, обвързва
  original recovery Action/ticket digest, published lifecycle digest и lineage.
  Original ticket може да е expired или от предишен boot: остава само evidence,
  не се подновява. Изменени key/generation/artifact/config/native/grant/epoch
  отказват; historical grant не става runtime permission.
- Issue сменя application epoch и резервира source за exact confirmation ID.
  Original recovery helper вече не може да продължи. Нов изричен human request
  може да замени прекъсната confirmation, но старият sealed record/outcome остава
  и получава superseded reference; няма automatic retry или journal eviction.
- Съществуващите release/runtime locks и confirmed stop предхождат readonly SQL.
  Проверяват се exact active/relational/wheel metadata, current SDK lineage/schema,
  bounded signed historical receipts и checksum-verified DB/files preimage.
  Recovery marker се приема само в completion_unconfirmed/prepared_not_started;
  partial publication, pending migration, unknown/foreign marker, unconfirmed stop
  или corrupt evidence не се поправят и не се архивират.
- Работната база използва normal existing-only readonly URI. Само затвореният,
  checksum-verified snapshot се чете с private `mode=ro&immutable=1`, за да не
  се създадат WAL/SHM до preimage. Това не е опция за service/caller или live DB.
  Няма application SQL write, receipt rewrite, new lineage или callback replay.
- Core checkpoints са след SQL unlock; signed confirmation receipt има отделен
  purpose и exact request/lifecycle identity. При explicit resolution на original
  execution_unconfirmed recovery се пази prior state, а original receipt запазва
  original recovery ID/purpose/lineage. Никакви transaction/outbox/job/external
  outcomes не се разрешават от тази metadata confirmation.
- До confirmed finish нов blocking marker пази readiness отказ. Matching evidence
  се архивира в same protected parent, без delete; максимум 32 pending markers,
  без eviction. Lost confirmation ACK или partial archive изискват **нов human
  request**, повторни проверки и без SQL replay. Success остава
  disabled/review_required/prepared_not_started; fresh approval е отделна стъпка.

Тестове: [actual Core/root readonly reconciliation](../backend/tests/test_application_relational_recovery_confirmation.py).
Покрити са lost ACK преди/след Core, repeated lost confirmation ACK, original
preparation marker, partial archive, expired source, exact receipt/purpose,
namespace/key/policy/clock drift и byte-preserved DB/record/preimage. Финална
Linux targeted regression: **191 passed**, включително **32 нови confirmation
cases** и предходните 159 recovery/admission/host/preparation/wire/receipts/
production guard проверки. Първият 27-case run е повторен поднабор; неговите
два snapshot-sidecar failures са поправени и включени в успешната регресия,
не се добавят като още уникални тестове. Среда: actual root disposable WSL Ubuntu
fixtures, Python **3.14.4**, SQLite **3.46.1**. Black/isort и whitespace проверките
минават; това не е full release suite, frontend build или live acceptance.

Остават partial/непубликуван recovery и general verified-preimage/backup restore
с fresh lineage, full namespace/key setup, prepared-DB upgrade, rekey/global
generation coordination, normal dispatch/SDK wiring и Standalone/Hub acceptance.
Production guards/каталогът и SDK **1.3** са unchanged; няма public endpoint/
export, ORM/Alembic change, frontend промяна, live deployment или WP4 closure.

## Нормален host/SDK transport — само verified prepared database

Реализирана е ограничената normal-host интеграция върху единствените existing
engine/session/admission/receipt договори. Това не добавя втори SDK, DB broker,
public SQL endpoint, ново разрешение или automatic lifecycle adoption.

- `PreparedRelationalRuntime` приема само exact protected `active.json`, signed
  lifecycle record, pinned wheel и проверена own SQLite lineage/schema. Pending
  rollback/recovery evidence блокира startup/readiness. Липсваща база, key или
  namespace не се създават; това остава работа на protected lifecycle.
- Нормалният `application_host` стартира отделния metadata worker и подава
  `ApplicationScopedStorage` на реалната factory само като non-root. Service
  entrypoint е проверен в pinned wheel преди import. Restart не импортира package
  migration module и не изпълнява migrations. Legacy SDK 1.0–1.3 пътят остава.
- `invoke_application` издава enclosing invocation ticket чрез Core resolver
  след съществуващите operation/audience/payload checks. Ticket е отделно поле
  в signed service envelope, не package-authored `OperationContext`. Health не
  получава ticket и не може да придобие неявно SQL право.
- Supported SDK read/write admission изисква host-owned active invocation преди
  IPC. `relational.admit/complete/status` пренасят само bounded exact metadata;
  SQL, DB paths, deadline и lineage не се приемат от package заявката. Current
  grants/revoke и original enclosing deadline отново се проверяват от Core.
- Commit completion е след SQLite close. При lost completion response SDK
  връща unconfirmed/no replay, а historical receipt lookup не предоставя нов
  grant. Нормалният readiness чете само SDK/lifecycle metadata, с explicit
  `outbox_inspected=false`; празният outbox обект не е измислен queue count.
- Relational opt-in без отделна `private_files` декларация получава отказващ
  file adapter, не legacy writable fallback. DB grant не става file grant.

Проверка: [real normal-host integration](../backend/tests/test_application_relational_runtime.py)
с **12 нови cases**. Реален reviewed ZIP, actual root preparation helper и
actual factory/handler child като UID **1200** / GID **1201**, двата Unix sockets
и Core → host → SDK → Core пътят проверяват atomic business/outbox/receipt commit,
read-only refusal, revoke, missing/spoofed ticket/context, metadata-only transport,
foreign SQL/value bounds, lost response, restart без migration import, root
factory refusal и pending-checkpoint refusal. Подготовката е реална и grant-ът
идва от review/approve/apply. Re-enable е **explicit fixture state**, не public
first-install coordinator или административен route acceptance.

Финална targeted regression: **191 passed**, включително тези 12 cases и
existing admission/host, scoped engine/receipts/wire, platform authority и
activation проверки. Отделно **35 passed** за legacy gateway/platform/transport,
file host и неподготвения relational gate: **226 distinct targeted tests** в
тези два финални runs, без skips. Предходният 45-case run е припокриващ се
поднабор и не се добавя към този брой. Среда: disposable root WSL Ubuntu,
Python **3.14.4**, SQLite **3.46.1**. Новите файлове минават Black/isort;
diff whitespace е чист.
SDK остава **1.3**, Core **0.3.0-beta.44**. Това не е full release suite,
frontend/live acceptance, commit/push/release или deployment.

Следва lifecycle orchestration за fresh namespace/key setup и prepared-DB
upgrade/verified restore с coherent lineage/key/epoch; после общият installed
Standalone/Hub acceptance. Unsupported generic activation/native/source gates
не са премахнати, а signed DB actions не разширяват останалите platform права.
Scoped platform/frontend contracts и общото WP4 приемане също остават отворени.
