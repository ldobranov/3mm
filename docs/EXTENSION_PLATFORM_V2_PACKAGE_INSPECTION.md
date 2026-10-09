# Milestone 20 — read-only Package Inspection

Дата: 2026-10-08. Статус: първата одобрена малка стъпка след ограничен WP0
е реализирана локално. Не е завършен WP1/M20 или production-security приемане.
Без deploy, commit/push или release в тази задача.

## Как се използва

В Extensions администраторът избира ZIP и натиска „Преглед на пакета“.
Резултатът е временен и се изчиства при избор на друг файл; стар отговор не
може да се покаже за новоизбрания файл. Качването остава отделно действие
със съществуващите проверки. Прегледът не инсталира и не активира нищо.

Поддържат се съществуващите Module Manifest v2 пакети: Agent module,
runtime UI, compiled UI, application и theme v1/v2. Използват се техните
авторитетни validators/descriptors, без втори manifest или SDK bump.
Legacy language/backend форматът не се поддържа от inspector-а и няма
автоматичен fallback към legacy upload. Самият стар upload поток не е променян.

## API contract v1

`POST /api/v1/modules/packages/inspect`

- Съществуващата admin authentication; guest/user, blocked/revoked/expired
  сесии и device tokens нямат достъп. Няма нов permission/grant модел.
- Raw ZIP request body, `Content-Type: application/zip` или
  `application/octet-stream`. Това **не е multipart** endpoint.
- До 10 MiB compressed body, проверени и по време на streaming; архивът се
  валидира в паметта, без временни ZIP файлове или извличане на диска.
- Съществуващите validator лимити остават: до 256 entries и 40 MiB expanded.
- Успех: HTTP 200 и `Cache-Control: no-store`; `inspection_version: 1`.
- 401/403 при липса на право; 413 при прекалено голям body; 415 при
  неподдържан Content-Type; 422 при невалиден/несъвместим/unsafe пакет.

Response съдържа exact `module_id`, `version`, `sha256`, `size_bytes`,
`package_kind`, целия валидиран `manifest` и наличните typed `descriptors`.
Права, capabilities, dependencies/conflicts и configuration изисквания са
декларации, не разрешение или решен install plan.

Сравнение с текущия каталог чрез ID/version, без четене на стария ZIP:

| `catalog.status` | Значение |
| --- | --- |
| `new` | ID/version не присъства в каталога |
| `exact_artifact` | Същият ID/version и SHA-256 вече е наличен |
| `version_conflict` | ID/version е зает от различен SHA-256 |

Конфликтът е резултат от inspection с HTTP 200, не каталогова промяна.
`existing_sha256` е наличният digest или null. Каталогът може да се промени
след прегледа; истинският upload задължително валидира отново.

### Опционален application authority преглед

`?include_authority_review=true` добавя read-only сравнение с действително
инсталирания application пакет и запазената конфигурация; Extensions го включва.
По подразбиране `authority_review` е null, без четене на стария ZIP. Няма нов
endpoint, DB/SDK промяна или предоставяне на права. Вътрешното сравнение е
declarations → declarations, не approved grants → requests.

Advisory `review_version: 1` различава `available`, `unavailable` и
`not_applicable`. Липсващ/повреден стар архив не се представя като first install
или нулева разлика. Canonical bounded archive read и конфигурацията се избират
от Core, не от клиента или най-новата версия в каталога. Виж
[authority review contract](EXTENSION_PLATFORM_V2_AUTHORITY_REVIEW.md) за границите,
redaction, selected baseline и before/after UI. Permissions остават `not_evaluated`.

## Какво НЕ е проверено или разрешено

- Protocol compatibility се проверява от съществуващия validator.
  Core requirement се проверява спрямо работещата Core версия, когато пакетът
  има Core runtime; иначе `core: not_checked`.
- Няма избрано target устройство: Agent, architecture и target_device са
  `not_checked`. Source/build/runtime availability също не се доказват тук.
- Publisher и signature са `not_verified`; SHA-256 не доказва авторство.
- Dependencies/conflicts са `not_resolved`; permissions са `not_evaluated`.
- Няма DB/catalog writes, package storage, compiler, subprocess, activation,
  downloads, migration или grant changes. Catalog lookup не auto-flush-ва ORM.
- Няма обещание за успешна инсталация или sandbox. WP5 isolation и legacy
  execution рисковете от WP0 остават отворени.

## Проверки

- **46 backend теста**: новият HTTP/auth/inspection flow и съществуващият
  `test_module_packages.py`; supported types, malformed/unsafe/expanded/oversized
  ZIP, real admin/user/guest/revocation, repeated inspection и immutable conflict.
  Write sentinels забраняват DB flush/write, файлов запис/extraction, temporary
  files, compiler и subprocess. Те не заменят live isolation acceptance.
- **25 frontend теста**: 8 за inspector-а и 17 съществуващи Extensions проверки;
  raw File transport, no legacy fallback, stale response/abort, limits, i18n
  и escaped untrusted text. Type-check и production build са успешни.
- Визуален преглед с изолиран fixture: светъл desktop EN и тъмен desktop/mobile
  BG; 390 px mobile без хоризонтално преливане, дълги ID/digest се пренасят.
  Fixture API е симулиран; реалната auth/validator връзка е проверена с TestClient,
  не с live Raspberry/browser upload. Няма live данни или инсталирани пакети.

Read-only authority прегледът е добавен като последваща локална стъпка;
проверките за нея са описани в свързания authority review report.
Owner visual review на authority UI е одобрен на **2026-10-08**; това приема
само локалния read-only изглед, не package grants или production isolation.
Следва отделен избор на следващия договор от WP1/WP4/WP5.
Не се започват registry, signing, dependency resolver или runtime refactor автоматично.
