# API_MAP.md — tBotSheduler

> Карта всех API проекта: HTTP-эндпоинты, Telegram-команды, внутренние сервисы, события и интеграции.
> Составлена по исходному коду (`src/tbot_sheduler/`, `tests/`).

---

## Customer API

API для конечных пользователей — бронирование слотов, просмотр своих броней, отмена/изменение.

### HTTP (Web App — Telegram Web App)

Пользователь открывает Web App через кнопку в канале. Все запросы аутентифицируются через `X-Init-Data` (HMAC-SHA256 подпись Telegram).

| Метод | Путь | Аутентификация | Описание | Код ответа |
|-------|------|---------------|----------|-----------|
| GET | `/webapp/book` | Нет | HTML-страница бронирования (`book.html`) | 200 / 404 |
| GET | `/api/book/slots?channel_id=&date_str=` | `X-Init-Data` | Список свободных слотов на дату | 200 / 403 / 400 |
| POST | `/api/book` | `X-Init-Data` | Создать бронь | 200 / 403 / 409 / 429 |
| GET | `/api/my-bookings` | `X-Init-Data` | Список броней текущего пользователя | 200 / 403 |
| POST | `/api/cancel` | `X-Init-Data` | Отменить бронь | 200 / 403 / 404 / 429 |
| POST | `/api/change` | `X-Init-Data` | Изменить слот брони | 200 / 403 / 409 / 429 |

**Детали:**

- **POST `/api/book`** — тело: `BookingRequest { slot_id: int, notify_minutes?: int (default 10), comment?: string | null }`
  - Ответ: `{ success: true, booking_id, slot_id, date, start_time, end_time, notify_at }`
  - После создания планирует JobQueue-уведомление
- **POST `/api/cancel`** — тело: `CancelRequest { booking_id: int }`
  - Ответ: `{ success: true, slot_id }`
  - Удаляет JobQueue-задачу через `job_queue.scheduler.remove_job()`
- **POST `/api/change`** — тело: `ChangeRequest { booking_id: int, new_slot_id: int, notify_minutes?: int }`
  - Ответ: то же, что `/api/book` + `{ old_booking_id, old_slot_id }`
  - Создаёт новую JobQueue-задачу

### Бот-команды (Telegram, доступные всем)

| Команда | Описание | Кто может |
|---------|----------|-----------|
| `/start` | Приветствие, список команд | Любой пользователь |

### Web App UI (Telegram Web App)

| Страница | Файл | Описание |
|----------|------|----------|
| `/webapp/book` | `webapp/book.html` | Календарь → дата → свободные часы → бронирование |
| `/webapp/create-slots` | `webapp/create_slots.html` | (админ) Выбор дат и часовых интервалов |

### Модели данных (Customer-слой)

```python
# slot — часовой слот
Slot(id, channel_id, date, start_time, end_time, is_active, created_by)
    # Уникальный индекс: (channel_id, date, start_time)

# booking — бронь пользователя
Booking(id, slot_id, user_id, user_name, comment, notify_minutes, created_at)
    # Уникальный индекс: (user_id, slot_id) — защита от двойного клика

# notification — запись на отправку уведомления
Notification(id, booking_id, user_id, notify_at, sent, job_id)
    # Индекс: (notify_at, sent) — быстрый поиск просроченных
```

### Сервисы (Customer-слой)

| Сервис | Функция | Назначение |
|--------|---------|-----------|
| `booking_service.py` | `create_booking()` | Создать бронь + Notification + AuditLog |
| `booking_service.py` | `cancel_booking()` | Отменить бронь, удалить Notification, найти job_id |
| `booking_service.py` | `change_booking()` | cancel + create в одной операции |
| `booking_service.py` | `get_available_slots()` | Список свободных слотов по channel_id + date |
| `booking_service.py` | `get_user_bookings()` | Все брони пользователя с данными слота |
| `notification_service.py` | `schedule_notification()` | JobQueue `run_once(callback, when=delay)` |
| `notification_service.py` | `check_pending_notifications()` | Heartbeat — отправка просроченных уведомлений |
| `notification_service.py` | `_send_notification_callback()` | JobQueue callback — отправка сообщения в Telegram |
| `scheduler.py` | `check_pending()` | Только COUNT просроченных (вызывается при старте) |

### События (AuditLog)

| Действие | audit_log.action | Где создаётся |
|----------|-----------------|---------------|
| Создание брони | `booking_created` | `booking_service.create_booking()` |
| Отмена брони (пользователь) | `booking_cancelled` (cause: "user") | `booking_service.cancel_booking()` |
| Изменение брони | `booking_changed` | `booking_service.change_booking()` |
| Уведомление отправлено | — | `notification_service.*` (не пишет AuditLog) |

---

## Support API

API для поддержки — админ/модератор управляют слотами, бронями, ролями.

### Бот-команды (Telegram)

#### Владелец (owner) — полный доступ

| Команда | Описание | Права | Файл-хендлер |
|---------|----------|-------|-------------|
| `/setup` | Привязать бота к каналу, стать owner | Любой (первый) | `admin_handlers.setup_command` |
| `/add_moderator <user_id>` | Назначить модератора | owner | `admin_handlers.add_moderator_command` |
| `/remove_moderator <user_id>` | Удалить модератора | owner | `admin_handlers.remove_moderator_command` |
| `/moderators` | Список модераторов | owner, moderator, developer | `admin_handlers.moderators_command` |
| `/add_developer <user_id>` | Назначить разработчика | owner | `admin_handlers.add_developer_command` |
| `/remove_developer <user_id>` | Удалить разработчика | owner | `admin_handlers.remove_developer_command` |
| `/developers` | Список разработчиков | owner, moderator, developer | `admin_handlers.developers_command` |

#### Модератор (moderator) — управление слотами

| Команда | Описание | Права | Файл-хендлер |
|---------|----------|-------|-------------|
| `/create_slots` | Открыть Web App для создания слотов | owner, moderator | `slot_handlers.create_slots_command` |
| `/slots` | Просмотр всех активных слотов | owner, moderator | `slot_handlers.slots_command` |
| `/free_slot <id>` | Принудительно освободить слот | owner, moderator | `slot_handlers.free_slot_command` |
| `/broadcast` | Опубликовать кнопку бронирования в канал | owner, moderator | `slot_handlers.broadcast_command` |

### Сервисы (Support-слой)

| Сервис | Функция | Назначение |
|--------|---------|-----------|
| `slot_handlers.free_slot_command()` | Удалить все брони слота, slot.is_active = True | Освобождение занятого слота |
| `slot_handlers.broadcast_command()` | InlineKeyboard с web_app → канал | Публикация кнопки бронирования |

### События (AuditLog)

| Действие | audit_log.action | Где создаётся |
|----------|-----------------|---------------|
| Настройка завершена | `setup_completed` | `admin_handlers.setup_command()` |
| Модератор добавлен | `moderator_added` | `admin_handlers.add_moderator_command()` |
| Модератор удалён | `moderator_removed` | `admin_handlers.remove_moderator_command()` |
| Разработчик добавлен | `developer_added` | `admin_handlers.add_developer_command()` |
| Разработчик удалён | `developer_removed` | `admin_handlers.remove_developer_command()` |
| Слот освобождён админом | `slot_freed` | `slot_handlers.free_slot_command()` |
| Broadcast отправлен | `broadcast_sent` | `slot_handlers.broadcast_command()` |

### Внутренние проверки безопасности

| Компонент | Механизм | Параметры |
|-----------|----------|-----------|
| `auth.user_has_role()` | Проверка `Admin.role`, кеш 5 мин | roles: str | list[str] |
| `auth.check_admin` | Декоратор — roles: owner/moderator/developer | `update, context` |
| `auth.check_role(*roles)` | Декоратор — roles: любые комбинации | `'owner'`, `'owner', 'moderator'` |
| `deps.with_db` | Декоратор — открывает сессию, кладёт в `context.bot_data["db"]` | `@with_db` (внешний из 2+) |
| `deps.get_db` | FastAPI Depends — сессия на каждый HTTP-запрос | `Depends(get_db)` |
| `security.AntiFlood` | In-memory per-user, 1 action / 5 sec | `check(user_id) → bool` |
| `DefaultRateLimiter` | Встроенный в python-telegram-bot | 30/s overall, 20/s per group |

---

## Dashboard API

Системные/внутренние API для мониторинга и диагностики.

### HTTP

| Метод | Путь | Аутентификация | Описание | Источник |
|-------|------|---------------|----------|----------|
| GET | `/health` | Нет | Healthcheck всех узлов системы | `api/health.health_endpoint()` |
| GET | `/webapp/create-slots` | Нет | HTML-страница создания слотов для админа | `api/webapp.create_slots_page()` |

### Healthcheck (`/health`)

**Формат ответа:**
```json
{
  "status": "ok" | "degraded" | "down",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "response_time_ms": 45,
  "checks": {
    "database":     { "status": "ok", "detail": "wal_mode=ON, size_mb=2.3" },
    "bot":          { "status": "ok", "detail": "running, job_queue_size=5" },
    "telegram_api": { "status": "ok", "detail": "latency_ms=210, bot_name=@..." },
    "disk":         { "status": "ok", "detail": "free_mb=5120, total_mb=10240" },
    "memory":       { "status": "ok", "detail": "rss_mb=145, available_mb=512" },
    "scheduler":    { "status": "ok", "detail": "pending_notifications=0" }
  }
}
```

**Проверки (6):**
1. `_check_database()` — пинг SELECT 1, PRAGMA journal_mode, размер файла
2. `_check_bot()` — Application.running, JobQueue размер (degraded >1000)
3. `_check_telegram_api()` — bot.get_me(), latency (degraded >2000ms)
4. `_check_disk()` — shutil.disk_usage("/") (degraded <1GB free)
5. `_check_memory()` — psutil RSS + virtual_memory (degraded <200MB available)
6. `_check_scheduler()` — COUNT pending notification (degraded >0)

**Вызывается:**
- HTTP GET `/health` — по запросу
- При старте бота (`app.py:lifespan`) — логирует результат
- Из Telegram команды `/health` (developer/owner)

### Бот-команды (Developer)

| Команда | Описание | Права | Файл-хендлер |
|---------|----------|-------|-------------|
| `/health` | Форматированный healthcheck | developer, owner | `developer_handlers.health_command` |
| `/logs <lines>` | Последние N строк лога (макс 100) | developer, owner | `developer_handlers.logs_command` |
| `/version` | Версия + uptime + время запуска | developer, owner | `developer_handlers.version_command` |

**Детали команд:**
- **`/health`**: запускает `run_healthcheck(context.application)`, форматирует через `format_health_message()` с эмодзи. Если команда из группы — ответ в личку.
- **`/logs <lines>`**: читает `logs/app.log`, обрезает до 4000 символов (Telegram limit). Default 20, макс 100 строк.
- **`/version`**: читает `BOT_VERSION = "0.1.0"`, uptime из `context.application._start_time`.

### Внутренние компоненты

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| `run_healthcheck(request_or_bot)` | `api/health.py:200` | Агрегирует 6 проверок, возвращает итоговый статус |
| `format_health_message(health_data)` | `developer_handlers.py:37` | Форматирует healthcheck в HTML для Telegram |
| `format_uptime(seconds)` | `developer_handlers.py:20` | Xд Xч Xм Xс |
| `HealthContext` | `api/health.py:36` | Контейнер зависимостей (engine, bot_app, db_session, started_at) |
| `HealthStatus` | `api/health.py:22` | Enum: `ok` / `degraded` / `down` |

### Обработка ошибок (глобальная)

| Компонент | Описание |
|-----------|----------|
| `_on_error(update, context)` | `app.py:82` — глобальный error_handler, логирует `context.error` |
| Graceful shutdown | SIGTERM/SIGINT → `_shutdown_event` → останов бота → dispose engine |

### Экспорт

| Формат | Функция | Параметры |
|--------|---------|-----------|
| JSON | `export_schedule_json(db_session, channel_id, from_date, to_date)` | Список слотов с booking info |
| CSV | `export_schedule_csv(db_session, channel_id, from_date, to_date)` | ID, Дата, Начало, Конец, Статус, Кто занял |

### Вспомогательные утилиты

| Модуль | Функции |
|--------|---------|
| `core/tz_utils.py` | `utc_to_tz()`, `tz_to_utc()`, `format_slot_time()`, `get_available_tz_names()` — 11 часовых поясов РФ (UTC+2..+12) |
| `core/config.py` | Загрузка .env: BOT_TOKEN, CHANNEL_USERNAME, WEB_APP_URL, DATABASE_URL, LOG_LEVEL |

---

## Внешние интеграции

Компоненты **спроектированы в спецификации (CLAUDE.md и MILESTONES.md), но не реализованы в коде.**

### REST API `/api/v1/*`

| Метод | Endpoint | Permission | Описание |
|-------|----------|-----------|----------|
| GET | `/api/v1/slots` | `slots:r` | Список слотов (фильтр по дате) |
| POST | `/api/v1/slots` | `slots:w` | Создание одного или нескольких слотов |
| GET | `/api/v1/slots/{id}` | `slots:r` | Слот со статусом брони |
| PUT | `/api/v1/slots/{id}` | `slots:w` | Обновление слота |
| DELETE | `/api/v1/slots/{id}` | `slots:w` | Удаление слота (каскад на брони) |
| GET | `/api/v1/bookings` | `bookings:r` | Список броней (фильтр) |
| GET | `/api/v1/bookings/{id}` | `bookings:r` | Детали брони |
| POST | `/api/v1/bookings` | `bookings:w` | Создание брони от имени пользователя |
| DELETE | `/api/v1/bookings/{id}` | `bookings:w` | Отмена брони |
| GET | `/api/v1/channels` | `channels:r` | Список каналов админа |
| PUT | `/api/v1/channels/{id}` | `channels:w` | Обновление настроек канала |
| GET | `/api/v1/schedule.ics` | — | iCal экспорт |
| POST | `/api/v1/schedule.ics` | — | iCal импорт |
| GET | `/api/v1/health` | Нет | Healthcheck (без аутентификации) |

### Модели (не реализованы)

```python
# ApiClient — ключи доступа к External API
ApiClient(id, admin_id, name, key_hash, key_prefix, auth_method,
          permissions, rate_limit, is_active, expires_at,
          last_used_at, created_at, updated_at)

# Webhook — исходящие уведомления
Webhook(id, admin_id, channel_id, url, events, secret, is_active,
        retry_max_attempts, consecutive_failures, is_degraded,
        last_delivery_at, last_delivery_status, created_at, updated_at)

# WebhookDeliveryLog — доставка вебхуков
WebhookDeliveryLog(id, webhook_id, event, delivery_id, payload,
                   status, http_status, response_body, attempts,
                   next_retry_at, created_at, delivered_at)

# Integration — календарные интеграции
Integration(id, admin_id, channel_id, integration_type,
            credentials_encrypted, sync_direction, config,
            is_active, last_sync_at, last_sync_status)
```

### Команды управления (не реализованы)

| Команда | Описание | Права |
|---------|----------|-------|
| `/api_keys` | Список API-ключей | owner |
| `/create_api_key <name>` | Создать ключ (показ 1 раз) | owner |
| `/revoke_api_key <id>` | Деактивировать ключ | owner |
| `/webhooks` | Список вебхуков | owner |
| `/add_webhook <url> <events>` | Зарегистрировать вебхук | owner |
| `/remove_webhook <id>` | Удалить вебхук | owner |
| `/test_webhook <id>` | Отправить тестовое событие | owner |
| `/integrations` | Список интеграций | owner |
| `/add_integration <type>` | Добавить интеграцию (Google/Outlook) | owner |

### Аутентификация External API

| Вариант | Механика | Статус |
|---------|----------|--------|
| API Key (рекомендуется) | `X-API-Key: sk_live_xxx`, SHA-256 в БД | Не реализован |
| API Key + HMAC | Ключ + HMAC-подпись тела + X-API-Signature | Не реализован |
| JWT | Токен с sub/scope/exp | Отложен |

### Инфраструктура вебхуков (не реализована)

**События:** `booking.created`, `booking.cancelled`, `booking.changed`, `slot.created`, `slot.deleted`, `slot.updated`

**Доставка:**
```
Событие → WebhookDispatcher → POST на URL вебхука
  Заголовки: X-Webhook-ID, X-Webhook-Event, X-Webhook-Signature,
             X-Webhook-Delivery (UUID), X-Webhook-Timestamp
  Подпись: HMAC-SHA256(secret, body)
```

**Retry:** Попытка 1 (0s) → 2 (10s) → 3 (1m) → 4 (5m) → 5 (15m) → is_degraded

**Защита от SSRF:** Только HTTPS, запрещены internal IP (10.x, 172.16-31.x, 192.168.x, 127.x.x.x)

### Rate Limiter (реализован, не используется)

**Файл:** `core/rate_limiter.py`
**Класс:** `SlidingWindowRateLimiter` — in-memory sliding window (asyncio.Lock + deque)
**Методы:** `check(key, limit, window_seconds=60) → bool`, `cleanup()`
**Назначение:** для `/api/v1/*` (60 req/min per key + 1000 req/min IP)

### iCal (не реализован)

Зависимость `icalendar` указана в `requirements.txt` как комментарий. Планируется:
- **Экспорт:** `GET /api/v1/schedule.ics` — генерация .ics (RFC 5545)
- **Импорт:** `POST /api/v1/schedule.ics` — парсинг VEVENT, создание слотов
- **Валидация:** дубликаты, пересечение времени, sanity дат

### Шифрование credentials (не реализовано)

- `cryptography` (Fernet) — указана в `requirements.txt` как комментарий
- Ключ из `INTEGRATION_ENCRYPTION_KEY` в `.env` (переменная объявлена в `config.py`)
- Для хранения credentials календарей (Google Calendar, Outlook)

### Готовая инфраструктура

| Компонент | Файл | Статус |
|-----------|------|--------|
| `SlidingWindowRateLimiter` | `core/rate_limiter.py` | ✅ Реализован, Protocol-совместим |
| `with_db` / `get_db` | `core/deps.py` | ✅ Реализован — session-per-request для HTTP и бота |
| `INTEGRATION_ENCRYPTION_KEY` config | `core/config.py:21` | ✅ Объявлен |
| `EXTERNAL_API_CORS_ORIGINS` config | `core/config.py:22` | ✅ Объявлен |
| Модели ApiClient/Webhook/Integration | `models/` | ❌ Не созданы |
| Middleware rate limiter | — | ❌ Не реализован |
| Webhook dispatcher | — | ❌ Не реализован |
| iCal engine | — | ❌ Не реализован |
| Telegram команды управления | — | ❌ Не зарегистрированы |

---

## Открытые вопросы

### Критические баги (P0) — TASC_SPEC.md

| # | Баг | Суть | Статус |
|---|-----|------|--------|
| 1 | **Мёртвая DB-сессия** | `lifespan` закрывал единственную сессию при выходе | ✅ Исправлено — `session_maker` на каждый запрос |
| 2 | **HMAC не работает** | Параметры `validate_init_data` перепутаны | ✅ Исправлено — `hmac.new(bot_token, "WebAppData")` |
| 3 | **Нет auth_date** | initData не проверяет `auth_date` — возможна replay-атака |
| 4 | **PRAGMA foreign_keys** | WAL-прагмы установлены на engine.connect(), но не на новые соединения | ✅ Исправлено — `event.listen` на каждое соединение |
| 5 | **Race condition** | `create_booking()` не использует `select_for_update()` — два пользователя могут забронировать один слот |
| 6 | **No None checks** | `update.effective_user` / `update.message` без проверки в auth-декораторах |
| 7 | **Heartbeat не зовут** | `check_pending_notifications()` никто не вызывает — функция есть, но мёртвая |

### Другие проблемы

| # | Баг | Статус |
|---|-----|--------|
| 8 | `job_id` не сохраняется в Notification.job_id | ✅ Исправлено |
| 9 | `change_booking()` не атомарна — cancel + create в разных транзакциях | ✅ Исправлено — единая транзакция |
| 10 | Ролевой кеш без инвалидации — 5 мин TTL, но нет очистки при добавлении/удалении роли | ✅ Исправлено |
| 11 | AntiFlood.cleanup() никто не вызывает — утечка памяти | ✅ Исправлено — автоочистка |
| 12 | `assert` в коде — удаляется в `python -O` | ✅ Исправлено — type: ignore |
| 13 | Одна DB-сессия на все concurrent запросы — не thread-safe | ✅ Исправлено — Option E |
| 14 | N+1 в `get_user_bookings()` — каждый booking → отдельный SELECT Slot | P3 |
| 15 | `change_booking()` теряет `comment` при переносе | ✅ Исправлено (вместе с #9) |
| 16 | `free_slot_command` не уведомляет очередь ожидания | P3 |

### Пробелы в реализации

| Что | Где должно быть | Статус |
|-----|----------------|--------|
| External API routes `/api/v1/*` | `api/external/` | Не реализовано |
| Webhook dispatcher + signing + retry | `webhook/` | Не реализовано |
| iCal export/import | `integration/ical.py` | Не реализовано |
| Календарный bridge (Google/Outlook) | `integration/base.py` | Deferred |
| E2E-тесты | `tests/e2e/` | Пустой placeholder |
| `UserSettings` / user timezone | — | Не реализовано (только утилиты) |
| `/settings` Telegram команда | упомянута в CLAUDE.md | Не реализована |
| Модели: ApiClient, Webhook, WebhookDeliveryLog, Integration | `models/` | Не реализованы |
| Команды: `/api_keys`, `/create_api_key`, `/webhooks`, `/add_webhook`, `/integrations` | — | Не зарегистрированы |
| `Integration` encrypt/decrypt credentials | Fernet из INTEGRATION_ENCRYPTION_KEY | Не реализовано |
| Web App валидация на клиенте | `window.Telegram.WebApp.initDataUnsigned` check | Не реализована |
| `check_pending_notifications()` вызов при апдейтах | `app.py` / heartbeat hook | ✅ Подключено — startup + repeating job каждые 5 мин |
| `job_id` не сохраняется в Notification | `booking_service.py` + `notification_service.py` | ✅ Исправлено — `schedule_notification()` сам сохраняет job_id |

### Архитектурные вопросы

| Вопрос | Описание |
|--------|----------|
| ~~Одна DB-сессия на всех~~ | ✅ Исправлено (Option E). `session_maker` хранится в `app.state`. Каждый HTTP-запрос получает сессию через `Depends(get_db)`. Каждый хендлер бота — через `@with_db`. |
| **Role cache не сбрасывается** | 5-минутный кеш в `auth._role_cache` — добавление/удаление модератора не сбрасывает кеш. Может кешироваться старая роль. |
| **Notification.job_id не сохраняется** | `schedule_notification()` возвращает `job.name`, `booking_service.create_booking()` сохраняет его в Notification. ✅ Исправлено — `schedule_notification()` сам пишет job_id если передан `db_session`. |
| **SQLite для production** | До ~1000 DAU работает, но race condition на записи уже сейчас (P0 #5). При росте потребуется PostgreSQL. |
| **Нет healthcheck для External API** | `run_healthcheck()` не включает `external_api` и `webhook_dispatcher` (запланировано) |
| **Нет Swagger/ReDoc** | FastAPI автоматически генерирует OpenAPI, но в коде нет настроенных `openapi_tags` или summary для эндпоинтов |

### Внешние зависимости (requirements.txt)

| Пакет | Назначение | Статус |
|-------|-----------|--------|
| python-telegram-bot[job-queue] | 20.x, бот + JobQueue | ✅ |
| fastapi, uvicorn | HTTP-сервер | ✅ |
| sqlalchemy[asyncio], aiosqlite | БД async | ✅ |
| python-dotenv | .env | ✅ |
| pydantic | Валидация (BookingRequest, CancelRequest, ChangeRequest) | ✅ |
| psutil | Мониторинг памяти | ✅ |
| httpx | Не используется (для External API) | 📦 В requirements |
| icalendar | Не используется (для iCal) | 📦 В requirements |
| cryptography | Не используется (для Fernet шифрования) | 📦 В requirements |
| aiofiles | Не используется | 📦 В requirements |

---

*Сгенерировано из исходного кода `src/tbot_sheduler/`, `tests/`, `CLAUDE.md`, `MILESTONES.md`*
