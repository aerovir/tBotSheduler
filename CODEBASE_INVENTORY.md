# CODEBASE INVENTORY — tBotSheduler

> **Дата:** 2026-06-27  
> **Версия:** 0.1.0  
> **Описание:** Telegram-бот для бронирования часовых слотов в канале. Админ создаёт слоты, пользователи бронируют через Telegram Web App.  
> **Стек:** Python 3.11+, FastAPI, python-telegram-bot v20+, SQLAlchemy async + SQLite, Vanilla HTML/CSS/JS

---

## 1. Архитектура проекта

```
┌──────────────────────────────────────────────────────────────┐
│                   tBotSheduler (FastAPI)                      │
│                                                               │
│  ┌──────────────┐  ┌────────────────┐  ┌──────────────────┐  │
│  │  Bot Layer    │  │  API Layer     │  │  Core            │  │
│  │  admin_hand.. │  │  booking.py    │  │  database.py     │  │
│  │  slot_hand..  │  │  health.py     │  │  auth.py         │  │
│  │  booking_ser. │  │  webapp.py     │  │  security.py     │  │
│  │  developer..  │  │  router.py     │  │  config.py       │  │
│  │  notification │  └────────────────┘  │  logging.py      │  │
│  │  scheduler    │                      │  rate_limiter.py │  │
│  │  waiting_ser. │  ┌────────────────┐  │  tz_utils.py     │  │
│  │  forgotten_s. │  │  Models (ORM)   │  └──────────────────┘  │
│  │  export_svc   │  │  Admin,Channel, │                        │
│  └──────┬───────┘  │  Slot,Booking,  │  ┌──────────────────┐  │
│         │          │  Notification,  │  │  Web App (HTML)  │  │
│         │          │  AuditLog,      │  │  book.html       │  │
│         │          │  WaitingEntry   │  │  create_slots..  │  │
│         │          └────────────────┘  └──────────────────┘  │
│         │                                                     │
│         └──────────── SQLite (bot.db) ◄───────────────────────┘
└──────────────────────────────────────────────────────────────┘
         │                        │
   Telegram Bot API          Telegram Web App
   (polling)                 (initData auth)
```

---

## 2. Структура директорий

```
/opt/tBotSheduler/
├── src/tbot_sheduler/          # 34 source files
│   ├── __main__.py             # Entry point
│   ├── app.py                  # FastAPI factory, bot lifecycle
│   ├── api/                    # REST API layer (5 files)
│   ├── bot/                    # Telegram bot handlers (10 files)
│   ├── core/                   # Infrastructure (7 files)
│   ├── models/                 # SQLAlchemy ORM (8 files)
│   └── webapp/                 # Static HTML (2 files)
├── tests/                      # 22 test files
│   ├── unit/                   # 17 unit test files
│   ├── integration/            # 5 integration test files
│   └── e2e/                    # Placeholder (empty)
├── deploy/                     # Deployment scripts (3 files)
├── Dockerfile                  # Multi-stage Docker build
├── docker-compose.yml          # Single-service compose
├── pyproject.toml              # Build + test config
├── requirements.txt            # Python dependencies
├── CLAUDE.md                   # AI assistant context (~1210 lines)
├── MILESTONES.md               # Development milestones
└── CODEBASE_INVENTORY.md       # This file
```

---

## 3. Модули — детальное описание

### 3.1. Entry Point (`__main__.py`)

| Файл | Назначение |
|------|-----------|
| `__main__.py` (18 строк) | `python -m tbot_sheduler` — запускает uvicorn на `0.0.0.0:8000` |

### 3.2. Application (`app.py`)

| Компонент | Описание |
|-----------|---------|
| `create_app()` | FastAPI фабрика, lifespan=lifespan, монтирует api_router |
| `lifespan()` | Startup: БД → таблицы → heartbeat → healthcheck → бот (polling). Shutdown: bot → engine dispose |
| `_create_bot_app()` | Сборка Application: DefaultRateLimiter (30/сек), регистрация всех CommandHandler |
| `_signal_handler()` | SIGTERM/SIGINT → asyncio.Event, graceful shutdown |
| `_check_pending_on_startup()` | Heartbeat при старте — догоняет просроченные уведомления |
| `_on_error()` | Глобальный error handler для бота |

**Зарегистрированные команды бота:**

| Команда | Handler | Роли |
|---------|---------|------|
| `/start` | `start_command` | Все |
| `/setup` | `setup_command` | Все (создаёт owner) |
| `/add_moderator` | `add_moderator_command` | owner |
| `/remove_moderator` | `remove_moderator_command` | owner |
| `/moderators` | `moderators_command` | admin (любая роль) |
| `/add_developer` | `add_developer_command` | owner |
| `/remove_developer` | `remove_developer_command` | owner |
| `/developers` | `developers_command` | admin (любая роль) |
| `/health` | `health_command` | developer, owner |
| `/logs` | `logs_command` | developer, owner |
| `/version` | `version_command` | developer, owner |
| `/create_slots` | `create_slots_command` | owner, moderator |
| `/slots` | `slots_command` | owner, moderator |
| `/free_slot` | `free_slot_command` | owner, moderator |
| `/broadcast` | `broadcast_command` | owner, moderator |

### 3.3. API Layer (`api/`)

#### `api/router.py` (12 строк)
- Агрегирует три sub-router: health, webapp, booking

#### `api/health.py` (268 строк)
- **`GET /health`** — системный healthcheck
- 6 проверок: database, bot, telegram_api, disk, memory, scheduler
- `run_healthcheck(request_or_bot)` — вызывается из HTTP `/health` и Telegram `/health`
- `HealthContext` — контейнер зависимостей, заполняется из Request или Application
- Статусы: `ok` / `degraded` / `down`
- Параллельный запуск через `asyncio.gather`

#### `api/booking.py` (225 строк)
- **`GET /api/book/slots?channel_id=X&date_str=YYYY-MM-DD`** — свободные слоты
- **`POST /api/book`** — создать бронь (тело: BookingRequest)
- **`GET /api/my-bookings`** — брони текущего пользователя
- **`POST /api/cancel`** — отменить бронь
- **`POST /api/change`** — изменить слот брони
- Аутентификация: `X-Init-Data` header → `validate_init_data()` → user_id
- Anti-flood: `anti_flood.check(user_id)` → 429 если слишком часто
- Pydantic модели: BookingRequest, CancelRequest, ChangeRequest

#### `api/webapp.py` (29 строк)
- **`GET /webapp/create-slots`** — админский Web App (create_slots.html)
- **`GET /webapp/book`** — пользовательский Web App (book.html)

### 3.4. Bot Layer (`bot/`)

#### `bot/handlers.py` (25 строк)
- `/start` — приветственное сообщение

#### `bot/admin_handlers.py` (323 строки)
- **`/setup`** — привязка бота к каналу, создатель становится owner. Создаёт Admin + Channel
- **`/add_moderator <user_id>`** — owner добавляет модератора
- **`/remove_moderator <user_id>`** — owner удаляет модератора
- **`/moderators`** — список модераторов
- **`/add_developer <user_id>`** — owner добавляет разработчика
- **`/remove_developer <user_id>`** — owner удаляет разработчика
- **`/developers`** — список разработчиков
- Все sensitive-операции логируются в AuditLog через `_log_action()`

#### `bot/slot_handlers.py` (266 строк)
- **`/create_slots`** — кнопка с Web App для создания слотов
- **`/slots`** — просмотр активных слотов (группировка по дате, статус брони)
- **`/free_slot <id>`** — форсированно освободить слот (удаляет брони)
- **`/broadcast`** — публикация кнопки "📅 Забронировать" в канал

#### `bot/booking_service.py` (273 строки)
- **`get_available_slots()`** — свободные слоты для канала/даты
- **`create_booking()`** — создание брони + Notification + AuditLog. Race condition: проверка `(user_id, slot_id)` уникальности
- **`cancel_booking()`** — отмена брони (cascade на Notification). Возвращает job_id для удаления из JobQueue
- **`change_booking()`** — cancel + create в одной операции. AuditLog с old/new slot_id
- **`get_user_bookings()`** — все брони пользователя с данными слота

#### `bot/notification_service.py` (156 строк)
- **`schedule_notification()`** — регистрация JobQueue.run_once на `notify_at`
- **`_send_notification_callback()`** — JobQueue callback: отправка сообщения в Telegram
- **`check_pending_notifications()`** — Heartbeat: все `sent=0 AND notify_at <= now` → отправка + `sent=1`
- Двойная гарантия: JobQueue (точное время) + Heartbeat (страховка при перезагрузке)

#### `bot/scheduler.py` (31 строка)
- **`check_pending()`** — проверка количества просроченных уведомлений. Вызывается при старте и при каждом апдейте

#### `bot/developer_handlers.py` (153 строки)
- **`/health`** — запускает `run_healthcheck()`, форматирует в Telegram-сообщение с эмодзи
- **`/logs <lines>`** — последние N строк лога (по умолч. 20, макс 100)
- **`/version`** — версия, uptime, время запуска
- `format_health_message()` / `format_uptime()` — форматтеры

#### `bot/forgotten_service.py` (138 строк)
- **`check_inactive_bookings()`** — поиск броней старше 24ч без активности. Отправляет предупреждение. Если нет ответа через 1 час → автоотмена
- **`confirm_booking()`** — пользователь подтвердил бронь (логируется как `forgotten_confirmed`)

#### `bot/waiting_service.py` (108 строк)
- **`join_waiting()`** — встать в очередь ожидания на занятый слот
- **`leave_waiting()`** — выйти из очереди ожидания
- **`notify_waiting_users()`** — уведомить всех ожидающих при освобождении слота. Очищает очередь

#### `bot/export_service.py` (89 строк)
- **`export_schedule_json()`** — экспорт расписания в JSON (слоты + статус брони)
- **`export_schedule_csv()`** — экспорт расписания в CSV

### 3.5. Core Layer (`core/`)

#### `core/config.py` (28 строк)
- `BOT_TOKEN`, `CHANNEL_USERNAME`, `WEB_APP_URL`, `DATABASE_URL`
- `INTEGRATION_ENCRYPTION_KEY`, `EXTERNAL_API_CORS_ORIGINS`
- `BOT_VERSION = "0.1.0"`, `LOG_LEVEL`, `LOG_DIR`, `DB_PATH`
- Загрузка `.env` через `dotenv`

#### `core/database.py` (70 строк)
- SQLAlchemy `Base` (DeclarativeBase)
- `get_engine()` — singleton engine с WAL + busy_timeout=5000 + foreign_keys=ON
- `get_session_maker()` — singleton async_sessionmaker
- `create_tables()` — Base.metadata.create_all
- `dispose_engine()` — graceful shutdown

#### `core/auth.py` (148 строк)
- **`user_has_role(db, user_id, roles)`** — проверка роли с 5-минутным кэшем
- **`@check_admin`** — декоратор: проверка любой админ-роли
- **`@check_role(*roles)`** — декоратор: проверка конкретных ролей

#### `core/security.py` (90 строк)
- **`validate_init_data(init_data, bot_token)`** — HMAC-SHA256 верификация Telegram Web App initData
- **`AntiFlood`** — in-memory anti-flood (1 действие / 5 сек на user_id). Метод `cleanup()` для stale entries

#### `core/rate_limiter.py` (86 строк)
- **`SlidingWindowRateLimiter`** — in-memory sliding window. Thread-safe через asyncio.Lock
- **`RateLimiter(Protocol)`** — протокол для rate limiter'ов
- Методы: `check(key, limit, window_seconds)`, `cleanup()`

#### `core/logging.py` (49 строк)
- Три destination: stdout, `logs/app.log` (INFO+), `logs/error.log` (ERROR+)
- Подавление `httpx`/`httpcore` до WARNING

#### `core/tz_utils.py` (64 строк)
- Часовые пояса России (UTC+2..+12)
- `utc_to_tz()`, `tz_to_utc()`, `format_slot_time()`, `get_available_tz_names()`

### 3.6. Models (`models/`)

| Модель | Таблица | Ключевые поля | Связи | Уникальность |
|--------|---------|---------------|-------|-------------|
| `Admin` | `admin` | user_id, username, role (owner/moderator/developer), added_by | added_by_admin → self | user_id UNIQUE |
| `Channel` | `channel` | chat_id, title, owner_id, booking_horizon_days, default_notify_minutes | — | chat_id UNIQUE |
| `Slot` | `slot` | channel_id, date, start_time, end_time, is_active, created_by | bookings → Booking[] | (channel_id, date, start_time) |
| `Booking` | `booking` | slot_id, user_id, user_name, comment, notify_minutes | slot → Slot, notifications → Notification[] | (user_id, slot_id) |
| `Notification` | `notification` | booking_id, user_id, notify_at, sent (bool), job_id | booking → Booking | Index(notify_at, sent) |
| `AuditLog` | `audit_log` | action, user_id, slot_id, booking_id, details (JSON) | — | — |
| `WaitingEntry` | `waiting_entry` | slot_id, user_id, user_name | — | (slot_id, user_id) |

---

## 4. API Routes

### 4.1. FastAPI HTTP

| Метод | Path | Назначение | Аутентификация |
|-------|------|-----------|---------------|
| GET | `/health` | Системный healthcheck | Нет |
| GET | `/webapp/create-slots` | Web App создания слотов | Нет |
| GET | `/webapp/book` | Web App бронирования | Нет |
| GET | `/api/book/slots` | Список свободных слотов | X-Init-Data |
| POST | `/api/book` | Создать бронь | X-Init-Data |
| GET | `/api/my-bookings` | Мои брони | X-Init-Data |
| POST | `/api/cancel` | Отменить бронь | X-Init-Data |
| POST | `/api/change` | Изменить бронь | X-Init-Data |

### 4.2. Telegram Bot Commands

| Команда | Роли | Назначение |
|---------|------|-----------|
| `/start` | Все | Приветствие |
| `/setup` | Все | Привязка бота к каналу |
| `/add_moderator` | owner | Добавить модератора |
| `/remove_moderator` | owner | Удалить модератора |
| `/moderators` | owner/moderator/developer | Список модераторов |
| `/add_developer` | owner | Добавить разработчика |
| `/remove_developer` | owner | Удалить разработчика |
| `/developers` | owner/moderator/developer | Список разработчиков |
| `/health` | developer/owner | Healthcheck |
| `/logs` | developer/owner | Последние строки лога |
| `/version` | developer/owner | Версия и uptime |
| `/create_slots` | owner/moderator | Web App создания слотов |
| `/slots` | owner/moderator | Просмотр слотов |
| `/free_slot` | owner/moderator | Освободить слот |
| `/broadcast` | owner/moderator | Кнопка бронирования в канал |

---

## 5. Security

### 5.1. Защита Web App
- Все `/api/*` эндпоинты проверяют `X-Init-Data` через `validate_init_data()` (HMAC-SHA256)
- Пользователь извлекается из подписанных данных
- Anti-flood: не чаще 1 действия / 5 сек на user_id

### 5.2. RBAC
- **owner** — полный доступ, может делегировать
- **moderator** — управление слотами, нет делегирования
- **developer** — только технические команды (/health, /logs, /version)
- Декораторы: `@check_admin`, `@check_role('owner')`, `@check_role('owner','moderator')`
- Кэш ролей: 5 минут (in-memory)

### 5.3. Database
- WAL mode + busy_timeout=5000 + foreign_keys=ON
- Уникальные индексы: (user_id, slot_id) для защиты двойного нажатия
- Cascading deletes: Slot → Booking → Notification

### 5.4. Telegram API
- `DefaultRateLimiter`: 30 msg/sec overall, 20 msg/sec per group
- Глобальный error handler

---

## 6. Scheduling & Notifications

### Двойная гарантия доставки:

```
Бронирование → notify_at = start_time - notify_minutes
    ↓
JobQueue.run_once(callback, when=notify_at) + Notification(sent=0)
    ↓
В notify_at → JobQueue шлёт уведомление (если бот жив)
    ↓
Heartbeat при каждом апдейте: check_pending() → отправляет просроченные
    ↓
Heartbeat при старте: check_pending() → догоняет уведомления после перезапуска
```

### Защита от забытых броней:
- `check_inactive_bookings()` — поиск броней старше 24ч → предупреждение → автоотмена через 1ч

---

## 7. Тестирование

**22 тестовых файла / ~2400 строк**

| Уровень | Файлы | Назначение |
|---------|-------|-----------|
| unit (17) | test_models.py (282) | SQLAlchemy модели, индексы, constraints |
| | test_security.py (292) | HMAC, хеши, токены |
| | test_security_initdata.py (106) | Telegram initData validation |
| | test_health_formatting.py (119) | Форматирование healthcheck |
| | test_anti_flood.py (63) | Rate limiting |
| | test_config.py (30) | Config loading |
| | test_database.py (59) | DB operations |
| | test_database_init.py (39) | DB creation |
| | test_export.py (71) | CSV/JSON export |
| | test_forgotten.py (40) | Forgotten booking logic |
| | test_handlers.py (60) | Bot handler responses |
| | test_logging.py (51) | Logging setup |
| | test_rate_limiter.py (61) | Sliding window limiter |
| | test_scheduler.py (43) | Heartbeat |
| | test_shutdown.py (45) | Graceful shutdown |
| | test_tz_utils.py (53) | Timezone conversion |
| | test_waiting.py (63) | Waiting list |
| | test_waiting_queue.py (83) | Queue ordering |
| integration (5) | test_admin_handlers.py (190) | Admin flows |
| | test_booking_flow.py (260) | Full booking lifecycle |
| | test_developer_handlers.py (154) | Developer commands |
| | test_health.py (60) | /health endpoint |
| | test_health_edge.py (121) | Health edge cases |
| e2e | — | Placeholder (empty) |

**Фикстуры (conftest.py):** `db` (in-memory SQLite), `mock_telegram_api` (aioresponses), `app` (FastAPI), `client` (httpx.AsyncClient)

---

## 8. Deployment

### Docker
- **Dockerfile:** multi-stage, python:3.12-slim, HEALTHCHECK, port 8000
- **docker-compose.yml:** single service `bot`, volume mounts for `data/` и `logs/`

### VPS (Timeweb)
- **deploy/setup-vps.sh:** полная автоматизация — зависимости → пользователь `tbot` → репозиторий → venv → systemd → fail2ban → cron backup
- **deploy/tbotsheduler.service:** systemd, auto-restart, EnvironmentFile=.env
- **deploy/backup.sh:** ежедневный бэкап SQLite, хранение 7 дней

---

## 9. Dependencies

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| python-telegram-bot | >=20.0, <21 | Telegram Bot API (async) + JobQueue |
| fastapi | >=0.115.0 | Web framework + lifespan events |
| uvicorn | >=0.30.0 | ASGI server |
| sqlalchemy | >=2.0.0 (asyncio) | ORM + async engine |
| aiosqlite | >=0.20.0 | SQLite async driver |
| pydantic | >=2.0.0 | Data validation |
| pydantic-settings | >=2.0.0 | Env-based settings |
| python-dotenv | >=1.0.0 | .env loading |
| psutil | >=5.9.0 | System monitoring |
| pytest | >=8.0.0 | Test runner |
| pytest-asyncio | >=0.24.0 | Async test support |
| pytest-cov | >=5.0.0 | Coverage |
| aioresponses | >=0.7.6 | HTTP mock |

---

## 10. Web App (HTML)

### `webapp/create_slots.html` (226 строк)
- Админский интерфейс: календарь → выбор дат → выбор часов → создание слотов
- Telegram Web App integration

### `webapp/book.html` (383 строки)
- Пользовательский интерфейс: календарь → дата → свободные слоты → бронирование
- Просмотр/отмена/изменение своих броней
- Telegram Web App integration

---

## 11. Что НЕ реализовано (External API — будущие милстоуны)

| Компонент | Модуль | Статус |
|-----------|--------|--------|
| API-ключи (ApiClient) | `app/api/external/` | ❌ Запроектировано |
| REST /api/v1/* | `app/api/external/` | ❌ Запроектировано |
| Исходящие вебхуки | `app/webhook/` | ❌ Запроектировано |
| iCal экспорт/импорт | `app/integration/ical.py` | ❌ Запроектировано |
| Google Calendar bridge | `app/integration/base.py` | ❌ ABC готов |
| External API rate limiter | `core/rate_limiter.py` | ✅ Реализован |
| E2E тесты | `tests/e2e/` | ❌ Пусто |
| External API тесты | `tests/*/test_external*` | ❌ Пусто |

---

## 12. Статистика

| Метрика | Значение |
|---------|---------|
| Source files | 34 Python + 2 HTML |
| Source lines (Python) | ~3 400 |
| Test files | 22 (17 unit + 5 integration) |
| Test lines | ~2 400 |
| SQLAlchemy models | 7 |
| FastAPI routes | 8 |
| Telegram commands | 16 |
| Bot handlers | 16 |
| Тестовое покрытие (цель) | ≥80% |
| Docker image size | ~150 MB (slim) |
| RAM (runtime) | ~145 MB RSS |
