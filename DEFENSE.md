DEFENSE — Завдання 2: Робочий застосунок (прототип → БД)

## Що я реалізував (1–2 речення):

Реалізував `auth` (signup/login, профіль, завантаження фото в R2 з presigned URL) і `matching` (feed з PostGIS-радіусом + Jaccard-ранжування інтересів, swipe з race-safe визначенням match, keyset-пагінований список матчів) повністю, від міграцій БД до фронтенду; `chat` (бекенд, WS, фронтенд) реалізував колега (`LobanMihajlo`) в цій же гілці. Окремо провів аудит усіх трьох слайсів і виправив знайдений баг.

## Топ-3, де я «зрізав кути» / знайшов і виправив (проти spec):

- **`GET /matching/feed` робив необмежений запит — параметр `limit` був мертвим кодом.** `spec.md` §3.3.1 явно обіцяє, що feed "capped at a fixed page size". `get_candidates(db, caller, radius_km, limit)` приймав `limit`, але ніколи не застосовував його до запиту — вибиралися **всі** рядки за радіусом/gender/seeking/age, і лише потім Python сортував і обрізав до 20. На реальному масштабі (велике місто) — необмежена пам'ять і latency. **Виправлено** в цьому ж PR: додано `.limit()` з явним `.order_by(User.id)` (без `ORDER BY` `LIMIT` у Postgres недетермінований).
- **`matching` ніколи не штовхає live WS-подію при матчі — `chat` робить аналогічний push, `matching` — ні.** `spec.md` каже це двічі (§1 і §3.3.1 п.2): "pushes a live 'match' update directly to both users over the shared WS registry, if connected". `grep -rn "ws_manager" backend/app/matching/` — порожньо. Інший користувач дізнається про матч лише при наступному завантаженні `GET /matching/matches`, не миттєво. **Залишено задокументованим зрізом** — узгоджено з командою не виправляти в цьому проході (fix невеликий, ~10 рядків, перевикористовує `shared/ws.py`, який `chat` вже збудував).
- **Жоден із 4 `except IntegrityError` не перевіряє, яке саме обмеження спрацювало — ADR-0009 прямо цього вимагає.** Розділ "Consequences" ADR-0009: *"Correctness depends on catching the specific unique-violation exception... and verifying its constraint name/columns match"*. Усі 4 місця (`auth.signup`, два в `matching.swipe`, `chat.send_message`) ловлять `IntegrityError` широко й визначають "вже існує" повторним запитом — без перевірки `exc.orig`. Сьогодні це безпечно "за виключенням" (FK-цілі завжди валідовані заздалегідь), але це саме та підміна міркування, проти якої застерігає ADR. **Залишено задокументованим зрізом** — невеликий, але наскрізний фікс (перевірка `constraint_name` у 4 місцях), свідомо не зроблений під час аудиту.

Повний аудит (query correctness / N+1, поведінка на збоях DB/R2/WS) — `ai/audit/lab-2.md`, розділ "Part B".

## Ключове рішення — які альтернативи зважив і чому обрав цю (ADR):

Фото профілю зберігаються в R2 як **приватний бакет + короткоживучі presigned GET URL** (1 год, `R2_PRESIGNED_URL_TTL_SECONDS`), а не публічний бакет із постійним URL. Альтернативи: (а) публічний бакет з випадковим UUID-ключем — найпростіше, але фото — персональні дані, і "безпека через невідомість" (random key) — не той default, який хочеться для dating-застосунку; (б) публічний бакет узагалі без рандомізації — ще гірше. Обрано (в) приватний бакет + presigning: `PhotoStorage.upload()` повертає лише ключ (`User.photo_key`, перейменовано міграцією з `photo_url`), а `get_url()` генерує підписаний URL при кожній відповіді, що містить фото (`/me`, feed, matches) — підписання локальне (HMAC, без мережевого виклику), тож це не N+1. Перевірено на реальному R2-бакеті: завантажив JPEG, отримав presigned URL через API, викачав — отримав ідентичні байти.

Другий наскрізний патерн, який реалізував і покрив тестом: **insert-and-catch-unique-violation** (ADR-0009) для реципрокного matching — замість `SELECT ... FOR UPDATE` (блокування, ризик deadlock) чи `SERIALIZABLE` + retry (найсильніша гарантія, але окрема retry-інфраструктура). Перевірено інтеграційним тестом, який навмисно форсує дві паралельні транзакції на реальному Postgres (testcontainers) гонитися за вставкою одного й того ж нормалізованого `Match`-рядка — і підтверджує, що результат завжди рівно один `Match`, без необроблених винятків.

## Перевірка (на реально запущеній системі):

```
make check → lint (ruff) OK, 31 passed (pytest), uv build OK
make test-integration → 2 passed (testcontainers: duplicate-signup race, concurrent-match race)
```

Запущено локально (`docker compose up -d db && uv run alembic upgrade head && uv run uvicorn app.main:app`):
```
curl localhost:8000/health  → {"status":"ok"}
curl localhost:8000/version → {"sha":"dc2154a4e13ad906dee0e8c08c72ef9ed4adf47e"}
```

версія / `/version`: `dc2154a4e13ad906dee0e8c08c72ef9ed4adf47e`

## Здача:

(а) GitHub PR: https://github.com/Mr-Chekaut-Dungeon-IM-42/kpinder-02/pull/2
(б) цей заповнений DEFENSE.md

---

## Усі коміти `fedorenkoivan` у гілці `feat/lab-2` (лаб-2, без lab-1/initial)

| Коміт | Дата | Опис |
|---|---|---|
| `3a5f4d9` | 2026-10-08 | docs: choose r2 |
| `f77da8d` | 2026-10-08 | docs: lazy loading, hard deleting, cut corners and no logout |
| `5f43631` | 2026-10-12 | infra(auth): docker compose + env example |
| `23213a5` | 2026-10-12 | feat(auth): backend |
| `f245a38` | 2026-10-12 | infra(auth): map local db to host port 5433 |
| `018b93a` | 2026-10-12 | feat(auth): enable CORS for the frontend dev server |
| `96660c3` | 2026-10-12 | feat(auth): frontend |
| `6ce969c` | 2026-10-12 | docs: how to run backend and frontend locally |
| `97de181` | 2026-10-12 | fix(auth): resolve .env relative to backend/, not invocation cwd |
| `37b10e5` | 2026-10-12 | feat(profile): backend |
| `61560c6` | 2026-10-12 | fix(profile): photo upload failures stay inside CORS-wrapped error handling |
| `3528089` | 2026-10-12 | feat(profile): frontend |
| `2ece115` | 2026-10-12 | feat(matching): backend |
| `574dbeb` | 2026-10-12 | feat(matching): frontend |
| `eb37585` | 2026-10-12 | feat(profile): presigned R2 photo URLs instead of a public bucket |
| `989349b` | 2026-10-12 | chore: merge alembic heads (photo_key rename + messages table) |
| `327d42b` | 2026-10-12 | feat(profile): backend — store a human-readable location label |
| `e03eb20` | 2026-10-12 | feat(profile): frontend — show the resolved place name after sharing location |
| `0fcef9f` | 2026-10-13 | fix(matching): feed query was unbounded — limit param was dead code |
| `276fceb` | 2026-10-13 | docs: confirm audit deferrals with the team |
| `70fd31d` | 2026-10-13 | docs: correct audit Part B to the actual cut-corner definition |
| `882b9c3` | 2026-10-13 | docs: third cut corner — IntegrityError sites don't verify constraint name |
| `dc2154a` | 2026-10-13 | feat: add GET /version reporting the running build's git SHA |

Усі коміти, починаючи з `infra(auth): docker compose + env example`, зроблені з Claude Code (`Co-Authored-By: Claude Sonnet 5`). Коміти `chat`-функціоналу (`feat: add messages table`, `feat: add ws connection manager`, `feat: implement chat backend`, `feat: add UI for chatting` та інші) належать `LobanMihajlo` і в цей список не входять.
