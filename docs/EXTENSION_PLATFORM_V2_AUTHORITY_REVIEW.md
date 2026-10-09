# M20 — read-only application authority comparison

Дата: 2026-10-08. Статус: малка read-only стъпка с Extensions преглед, локално.
Не е approval contract, завършен WP4/WP5 или включено ново прилагане на права.
Няма нов endpoint, промяна в инсталатора, DB или SDK 1.3.

Owner visual review: **одобрен на 2026-10-08**. Приета е тази локална read-only
UI стъпка; това не е одобрение на package permissions, production isolation,
целия milestone или разрешение за commit/deploy/release.

## Обхват и вход

[review_application_authority](../backend/services/application_authority_review.py)
приема кандидат и по избор предишен `ValidatedModulePackage`, получени чрез
съществуващия ZIP/descriptor validator. Засега поддържа **application пакети**;
другите типове се отказват изрично, без legacy fallback. Общият Package Inspection
продължава да поддържа останалите съществуващи типове без промяна.

Предишният пакет трябва да е със същия module ID. За всяка страна caller-ът
подава отделна, пълна **ефективна конфигурация** от доверения Core контекст.
Тя се проверява със съществуващия configuration validator. Helper-ът не чете
инсталации или файлове и не предполага, че package defaults са реални bindings.
Липсваща/невалидна/непълна конфигурация остава `unresolved`, без wildcard scope.

Това е сравнение **declarations → declarations**, НЕ approved grants → requests.
Няма още persistence за новия grant модел. Полето `baseline` изрично е
`previous_declarations` или `no_previous_package`; `permission_approval` винаги
е `not_evaluated`. Стар manifest не е доказателство за одобрен достъп.

## Какво се сравнява

- Manifest permissions, provides/consumes и platform permission IDs отделно от
  човешките application permission IDs.
- Command bindings: capability/contract/action, bounded argument schema и
  канали, TTL, конфигурирани target/sensor device IDs и sensor identity.
- Event subscriptions: event/capability/handler, backlog и конфигуриран device ID.
- Connectors: конфигуриран plain origin, schemes, path prefix, mutations,
  authentication, opaque secret reference и request/response/timeout лимити.
  Origin validation използва съществуващия connector broker validator.
- Operations/routes: audiences, human permission requirements, idempotency,
  emitted events, limits, public HTTP paths/methods и schema change markers.
- Jobs, private storage/lifecycle declarations, runtime/SDK/entrypoints и
  compiled UI entrypoints. Няма присвояване на „sandboxed“ execution class.

Резултатът съдържа стабилно сортирани `added`, `removed`, `changed` scopes,
before/after projection и отделни `unresolved` причини за двете страни.
`potential_expansion` е true за additions/changes: **консервативен сигнал**,
не доказателство за семантично widening/narrowing на произволни schemas.
Премахнат declaration не доказва, че реални grants вече са отнети.

Сменено устройство, origin или reference зад същото configuration key се засича,
включително без смяна на package digest. Cosmetic names, labels, navigation order
и configuration object key order не променят authority diff. Unordered permission,
audience, command required/enum и descriptor collections се сравняват по смисъл.
Произволен JSON Schema не получава универсална semantic equivalence проверка.

Новият artifact digest се отчита отделно дори при празен authority diff.
Version/digest се запазват за двете страни. `declaration_review_required: false`
означава само „няма установена разлика/неизяснен declaration“, никога разрешение
за инсталация, активация или външно действие.

## Redaction и непроверени граници

Не се връща цялата конфигурация, defaults или secret values. Device/reference
стойности се проектират само при валиден `dev_<32 hex>` / `secret_<32 hex>` формат.
Password/token вместо secret reference, URL credentials/query/path и невалидни
device IDs не се отразяват в резултата или validation error текста.
Operation/configuration schemas и UI capability plan имат само детерминистични
change fingerprints; те **не са** approval hashes, подписи или secret verification.

`not_checked` винаги запазва: approved grants, device availability/contracts,
реални stored connector bindings/secret generations, trust, dependencies и
OS/browser isolation. Configured origin/reference не доказват активен broker
binding, credential ownership, rotation generation или revocation status.
Peer scope остава unresolved. Ефектите на compiled same-origin UI не могат да се
изведат от descriptor и се маркират unresolved, дори при еднакъв пакет.

Helper-ът не записва DB/файлове, не извлича ZIP, не стартира процеси, не прави
network заявки и не предоставя достъп. Не е свързан с runtime/lifecycle enforcement.

## Read-only интеграция в Package Inspection

Съществуващият admin-only `POST /api/v1/modules/packages/inspect` приема
опционално `?include_authority_review=true`. Без него старото поведение остава,
с additive `authority_review: null`, без четене на предишен ZIP. Extensions
включва опцията; upload/activation остават отделни, непроменени действия.

Core избира baseline чрез реалния `ApplicationExtensionInstallation.module_package_id`,
не чрез най-новия каталогов пакет, candidate version или client-supplied ID.
Само стабилна active/disabled инсталация със съвпадаща active/package version
може да се сравнява. Запазената конфигурация се използва непроменена и за
candidate preview; не се сливат defaults, не се записват настройки и не се
предполага, че това е бъдещ одобрен install plan.

Предишният архив се чете само от Core uploads namespace `modules/<sha256>.zip`,
не от произволния catalog `file_path`. Четенето е bounded (10 MiB), само regular
file, без symlink/FIFO; пакетът се валидира отново и се сверяват ID/version/digest.
Невалиден/липсващ baseline или нестабилна инсталация връща `unavailable`, без
raw exception/path/secret и **без fallback към first install или нулева разлика**.
При липсваща инсталация catalog-only пакетите не стават baseline; новите
declarations се показват с неизяснена конфигурация. Другите типове са
`not_applicable`, без четене на application baseline.

Advisory field има `review_version: 1`, status, bounded reason,
`configuration_source` и optional review. Това не е approval/signing wire format
или SDK договор за предоставяне на права; `permission_approval` остава
`not_evaluated`. Нов преглед може да е необходим след всяка промяна на пакета,
инсталацията или bindings; резултатът никога не е activation gate.

Extensions показва installed/selected versions и digests, counts за
added/removed/changed/unresolved, разгъваеми before/after projections и ясни
ограничения. Няма approve/install/grant бутони в сравнението. Стар Core без
полето се показва като „няма сравнение“. Текстът е escaped, преведен EN/BG и
се изчиства заедно с inspection при смяна на файла; late/aborted response не
може да остане върху нов файл.

## Проверки и следваща стъпка

[Целевите тестове](../backend/tests/test_application_authority_review.py) използват
реалния package validator и проверяват additions/removals, cosmetic-only artifact
change, same-key device/origin/reference changes, command bounds/TTL/channels,
sensor scope, human access, determinism, unresolved configuration, redaction,
unsupported types и липса на I/O/input mutation. Няма live devices или connectors.

Предишната backend стъпка: **71 целеви backend теста passed** — 22 authority-review случая
и 49 съществуващи configuration/package/inspection проверки (132 warnings),
22.38 s в изолиран WSL/Linux. Frontend production build passed (10.57 s),
без визуални промени. Full release suite и live security acceptance не са пускани.
Без deploy, commit/push, release или нова dependency.

Read-only представянето с доверен baseline/configuration вече е локално.
Проверки за интеграцията: **70 backend теста passed** (authority inspection,
pure authority review и съществуващ inspection HTTP/auth flow; 207 warnings,
21.95 s). Проверени са actual installed pointer вместо catalog/client hints,
active/disabled/transition states, missing/corrupt/digest/size/link/FIFO baseline,
private configuration, real admin denial и repeated SELECT-only/no-write преглед.
**29 frontend теста passed** (12 inspector + 17 Extensions), type-check и
production build passed. Стари responses/non-application пакети, EN/BG, escaped
before/after text, reset/abort и липса на approval actions са покрити.

Визуален преглед с изолиран синтетичен fixture: desktop light EN, desktop dark BG
и 390 px mobile dark BG. Няма хоризонтално преливане; mobile before/after е
едноколонен, без вложено вертикално скролиране на change list. Browser error log
е празен. Screenshot evidence е локално/ignored под
`.runtime/m20-inspection/authority-{desktop-light-en,desktop-dark-bg,mobile-dark-bg}.jpg`.
Fixture API е симулиран; реалният HTTP/auth/validator/DB път е проверен с TestClient,
не с live Raspberry upload. Full release suite/live isolation acceptance не са
пускани. Без deploy, commit/push, release или нова dependency.

Approval schema/persistence, generation binding,
secret rotation/device authority checks и effect-boundary enforcement остават
отделни задачи; този helper не ги замества и не се използва като activation gate.

Следващата ограничена design стъпка е описана в
[договора за изрично одобрени права](EXTENSION_PLATFORM_V2_APPROVAL_CONTRACT.md):
resource subsets, точен artifact/configuration/credential-version контекст,
invalidation/concurrency и безопасен преход/restore за съществуващи инсталации.
Статус: design contract, не реализирано одобрение. След последващо owner approval
е добавен локален [pure typed context/selection validator](EXTENSION_PLATFORM_V2_CONTEXT_VALIDATOR.md)
с canonical vectors, без route/live resolver или предоставяне на права. DB
persistence, approval API/UI и runtime enforcement остават отделни стъпки;
сегашното сравнение/инспекция не ги активира.
