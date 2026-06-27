# Milestones — tBotSheduler

## 1. Milestone 1: Основа проекта
**Цель**: Рабочий каркас приложения — FastAPI запускается, бот стартует, БД создаётся.

**Задачи:**
- Инициализация структуры проекта (FastAPI + python-telegram-bot)
- Настройка pytest + pytest-asyncio + репозитория тестов
- Написание conftest.py: фикстуры db (in-memory), mock_telegram_api, app, client
- Модели SQLAlchemy + создание таблиц (SQLite)
- **TDD:** unit-тесты моделей (создание, связи, уникальные индексы)
- **Безопасность:** SQLite `PRAGMA journal_mode=WAL, busy_timeout=5000`
- **Безопасность:** `.env` в `.gitignore`, права 600
- **Безопасность:** `DefaultRateLimiter` при старте бота
- **Безопасность:** уникальные индексы Booking (user_id + slot_id), Slot (channel_id + date + start_time)
- **Надёжность:** graceful shutdown (SIGTERM → останов бота + JobQueue + закрытие БД)
- **Надёжность:** настройка логирования (stdout + файл, rotate по размеру)
- Запуск бота через lifespan event FastAPI
- **Healthcheck:** эндпоинт `/health` с проверкой database + bot + telegram_api + disk + memory
- **Healthcheck:** функция `run_healthcheck()` — вызывается при старте бота
- **TDD:** интеграционный тест healthcheck (200 OK, структура ответа, каждый check)
- Команда `/start` — приветствие
- **TDD:** интеграционный тест /start (бот отвечает)
- **TDD:** unit-тест graceful shutdown (задачи JobQueue сохраняются в БД)

**Планировщик**: Heartbeat при старте (заготовка `check_pending()`).

**Критерий приёмки**: `python -m app.main` → бот отвечает на `/start`, БД `bot.db` (WAL mode) создалась с индексами, FastAPI доступен на `:8000/health`, rate limiter активен, graceful shutdown не роняет JobQueue задачи. `pytest --cov-fail-under=80` проходит для модулей Milestone 1.

### External API (после Milestone 1)
- **[Модели]** ApiClient, Webhook, WebhookDeliveryLog, Integration — включить в `Base.metadata.create_all`
- **[Rate limiter]** In-memory sliding window (asyncio.Lock + deque). Middleware для `/api/v1/*`
- **[Deps]** Добавить `httpx`, `icalendar`, `cryptography` в `requirements.txt`
- **[Healthcheck]** Добавить проверки `external_api`, `webhook_dispatcher` в `/health`
- **[TDD]** — unit-тесты новых моделей (создание, связи, каскады, индексы)
- **[TDD]** — unit-тест rate limiter: 60 запросов разрешены, 61-й блокирован, окно сдвигается
---

## 2. Milestone 2: Админ-панель
**Цель**: Админ может создавать слоты, публиковать кнопку бронирования в канал и делегировать права модераторам и разработчикам.

**Задачи:**
- @check_admin — написать тест
- **TDD:** unit-тест проверки прав: owner, moderator, developer, не-админ, пользователь без прав
- **TDD:** unit-тест разграничения ролей: moderator не может вызвать /add_moderator
- **TDD:** unit-тест: developer может вызвать /health, но не /create_slots
- **TDD:** интеграционный тест — owner добавляет developer → developer вызывает /health
- **TDD:** интеграционный тест — moderator вызывает /add_moderator → отказ
- Проверка прав через таблицу `Admin` (owner/moderator/developer) + кеш 5 мин
- **Безопасность:** декоратор `@check_admin()` для всех админ-команд
- **Безопасность:** декоратор `@check_role('owner')` для команд делегирования
- **Безопасность:** декоратор `@check_role('developer', 'owner')` для /health, /logs, /version
- **AuditLog:** логировать создание/удаление слотов и добавление/удаление модераторов/разработчиков
- Модель **Admin** с полем role, added_by, created_at
- Команда `/setup` — привязка к каналу, создатель становится owner
- Команда `/add_moderator <user_id>` — owner добавляет модератора
- Команда `/remove_moderator <user_id>` — owner удаляет модератора
- Команда `/moderators` — список модераторов канала
- Команда `/add_developer <user_id>` — owner добавляет разработчика
- Команда `/remove_developer <user_id>` — owner удаляет разработчика
- Команда `/developers` — список разработчиков
- Команда `/health` — healthcheck в Telegram (developer/owner)
- Команда `/logs <lines>` — последние N строк лога (developer/owner)
- Команда `/version` — версия + uptime (developer/owner)
- Healthcheck: функция `format_health_message()` + хендлер /health
- Web App для админа: выбор дат и часовых интервалов
- **TDD:** unit-тесты CRUD слотов (создать, удалить, список по дате)
- Сохранение слотов в БД
- Команда `/broadcast` — сообщение с кнопкой "📅 Забронировать" в канал
- Web App для просмотра созданных слотов
- Команда `/free_slot` — принудительное освобождение слота админом
- **TDD:** интеграционный тест healthcheck — проверка telegram_api (mock)
- **TDD:** интеграционный тест healthcheck — database WAL mode check
- **TDD:** интеграционный тест — /health в Telegram (форматирование, emoji, статусы)

**Критерий приёмки**: Owner создал слоты, добавил модератора и разработчика, broadcast в канал. Модератор создал/удалил слот, не может добавить модератора. Developer вызывает /health, /logs, /version, не может создать слот. Healthcheck на `/health` показывает ok по всем узлам. `pytest --cov-fail-under=80` проходит.

### External API (после Milestone 2)
- **[Команды]** `/api_keys`, `/create_api_key <name>`, `/revoke_api_key <id>`
- **[Команды]** `/webhooks`, `/add_webhook <url> <events>`, `/remove_webhook <id>`, `/test_webhook <id>`
- **[Контроль доступа]** `@check_role('owner')` на все команды управления API/вебхуками
- **[Scaffold]** Роутер `/api/v1/*`, auth-dependency (проверка X-API-Key, is_active, expires_at, permissions)
- **[Endpoints]** GET/PUT `/api/v1/channels` (read-only или настройки)
- **[AuditLog]** Логировать каждый API-запрос (api_client_id, method, endpoint, IP, status)
- **[TDD]** — интеграционные тесты: создание/отзыв/список API-ключей, auth (200/401/403), permissions
- **[TDD]** — интеграционный тест: read-only ключ пробует POST → 403
- **[TDD]** — интеграционный тест: rate limiter → 429

---

## 3. Milestone 3: Бронирование + Уведомления
**Цель**: Пользователи могут бронировать слоты, видеть таблицу занятости и получать уведомления.

**Задачи:**
- **TDD:** unit-тест validate_init_data (правильный hash, подделка, просроченный auth_date)
- **TDD:** интеграционный тест — бронь с select_for_update (5 конкурентов → 1 успех)
- **TDD:** интеграционный тест — дубликат брони (user_id + slot_id) → ошибка
- **TDD:** unit-тест anti-flood (лимит 5 сек, сброс через 5 сек)
- **TDD:** интеграционный тест — JobQueue: регистрация → срабатывание → mark_sent
- **TDD:** интеграционный тест — Heartbeat: check_pending() догоняет просрочку
- **TDD:** интеграционный тест — Notification не отправляется дважды (sent=True)
- **TDD:** e2e-тест — полный цикл: слот → бронь → уведомление → таблица занятости
- **TDD:** e2e-тест — race condition: 5 одновременных броней на 1 слот
- **TDD:** интеграционный тест healthcheck — JobQueue размер, scheduler pending count
- **Безопасность:** валидация initData Web App через HMAC-SHA256 (клиент + сервер)
- **Безопасность:** `select_for_update()` внутри транзакции при бронировании
- **Безопасность:** anti-flood — не чаще 1 действия / 5 сек на пользователя
- **Безопасность:** уникальный индекс (user_id + slot_id) — защита от двойного клика
- **AuditLog:** логировать бронирование и отправку уведомлений
- Web App для пользователя: календарь → выбор даты → свободные слоты
- Кнопка "Забронировать" — запись в Booking + Notification
- JobQueue: `run_once` на `notify_at`
- Heartbeat: `check_pending()` при старте и на каждом апдейте
- **Безопасность:** идемпотентность уведомлений (флаг `sent = False`)
- Подтверждение брони в личное сообщение пользователю
- Отображение таблицы: дата, время, кто занял
- Настройка времени уведомления через Web App (5/10/15/30 мин)

**Критерий приёмки**: Пользователь забронировал слот → получил подтверждение → за N минут до начала пришло уведомление в личку (без дублей). В таблице видно занятые слоты. Race condition исключён. AuditLog хранит цепочку действий. `pytest --cov-fail-under=80` проходит.

### External API (после Milestone 3)
- **[Endpoints]** GET/POST `/api/v1/slots` — список + создание слотов
- **[Endpoints]** GET `/api/v1/slots/{id}` — слот со статусом брони
- **[Endpoints]** GET/POST `/api/v1/bookings` — список + создание брони
- **[Webhook dispatcher]** Модуль `app/webhook/dispatcher.py` — находит подписанные вебхуки по событию, POST через `httpx.AsyncClient`
- **[Webhook событие]** `booking.created` → dispatch
- **[Webhook подпись]** HMAC-SHA256(body, secret), заголовки X-Webhook-*
- **[TDD]** — интеграционный тест: создание брони через API (валидный ключ)
- **[TDD]** — интеграционный тест: webhook delivery на booking.created (mock aioresponses)
- **[TDD]** — unit-тест: webhook signing + verification

---

## 4. Milestone 4: Отмена и изменение
**Цель**: Пользователь может отменить или изменить свою бронь. Уведомления корректно отменяются/пересоздаются.

**Задачи:**
- **TDD:** unit-тест отмены: удаление Booking + Notification + JobQueue
- **TDD:** e2e-тест изменения слота: старая бронь отменена → новая создана → уведомление перепланировано
- **TDD:** интеграционный тест — после отмены слот снова свободен (другой бронирует)
- **TDD:** e2e-тест — отмена брони, восстановление после падения (имитация SIGTERM)
- **AuditLog:** логировать отмену и изменение брони
- Web App: кнопка "Мои брони" → список броней пользователя
- Отмена брони: удаление Booking + Notification + `JobQueue.remove_job`
- Изменение слота: отмена старой + создание новой брони
- Слот после отмены снова становится свободным
- Уведомление админу об отмене (опционально)
- **Надёжность:** подтверждение отмены (пользователь подтверждает действие)

**Критерий приёмки**: Пользователь отменил бронь → слот освободился → уведомление в JobQueue удалено → другой может забронировать. Изменение слота работает. AuditLog фиксирует изменения. `pytest --cov-fail-under=80` проходит.

### External API (после Milestone 4)
- **[Endpoints]** PUT/DELETE `/api/v1/slots/{id}` — обновление + удаление слота
- **[Endpoints]** DELETE `/api/v1/bookings/{id}` — отмена брони
- **[Webhook события]** `booking.cancelled`, `booking.changed`, `slot.created`, `slot.deleted`, `slot.updated`
- **[Webhook retry]** Retry-механизм: 5 попыток (0s → 10s → 1m → 5m → 15m), запись в WebhookDeliveryLog
- **[Webhook degradation]** После 5 неудач → флаг `is_degraded = True`, уведомление админу
- **[Webhook idempotency]** X-Webhook-Delivery UUID, один UUID на всю цепочку ретраев
- **[SSRF защита]** Проверка URL вебхука: только HTTPS, блокировка internal IP
- **[TDD]** — интеграционный тест: отмена брони через API → webhook cancelled
- **[TDD]** — интеграционный тест: retry (500 → retry → 200 → delivered)
- **[TDD]** — интеграционный тест: max retries → is_degraded
- **[TDD]** — unit-тест: SSRF-валидация (приватные IP блокирует)

---

## 5. Milestone 5: Полировка и доп. фичи
**Цель**: Улучшение UX, дополнительные возможности.

**Задачи:**
- **TDD:** интеграционный тест очереди ожидания (встать → слот освободился → уведомление)
- **TDD:** интеграционный тест автоотмены забытых броней (нет активности → запрос → отмена)
- **TDD:** e2e-тест экспорта расписания (CSV → парсинг → проверка данных)
- **TDD:** unit-тест конвертации временных зон (UTC → Europe/Moscow → Asia/Vladivostok)
- Временные зоны пользователей (выбор в Web App)
- Очередь ожидания: встать в лист на занятый слот, уведомление при освобождении
- Автоотмена «забытых» броней (нет активности > 24ч → запрос подтверждения → отмена)
- Экспорт расписания (JSON/CSV)
- Dockerfile + docker-compose (опционально)
- Инструкция по деплою на Timeweb VPS
- systemd сервис + автостарт
- Настройка бэкапов SQLite (cron)
- Настройка fail2ban для SSH
- Создание пользователя `tbot` вместо root для бота
- Проверка финального покрытия: `pytest --cov=app --cov-fail-under=80`

**Критерий приёмки**: Все доп. фичи работают. Проект готов к деплою на Timeweb VPS с systemd, fail2ban, бекапами и пользователем `tbot`. Покрытие кода тестами ≥ 80%.

### External API (после Milestone 5)
- **[iCal экспорт]** `GET /api/v1/schedule.ics` — генерация .ics из расписания
- **[iCal импорт]** `POST /api/v1/schedule.ics` — парсинг VEVENT, создание слотов
- **[iCal валидация]** Дубликаты, пересечение времени, sanity check дат
- **[Интеграции]** Telegram команды: `/integrations`, `/add_integration <type>`, `/remove_integration <id>`
- **[Webhook degradation]** Фоновый мониторинг: уведомление админу при is_degraded
- **[Auto-cleanup]** Удаление delivery logs старше 30 дней
- **[API docs]** Swagger/ReDoc на `/api/v1/docs`
- **[TDD]** — unit-тест: генерация .ics → валидный iCal
- **[TDD]** — интеграционный тест: импорт .ics → создание слотов → проверка дубликатов
- **[TDD]** — e2e-тест: API-ключ → слот → броня → webhook → отмена → webhook
- **[TDD]** — e2e-тест: iCal экспорт → парсинг → импорт → верификация
