# tBotSheduler — Telegram Bot для бронирования расписания

## Описание
Telegram-бот для канала, позволяющий админу создавать часовые слоты, а пользователям — бронировать их через Telegram Web App. При наступлении времени бот уведомляет пользователя.

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Бот | `python-telegram-bot` (v20+, async) |
| Backend | FastAPI |
| База данных | SQLite + SQLAlchemy (async) + aiosqlite |
| Web App | Vanilla HTML/CSS/JS (Telegram Web App) |
| Планировщик | JobQueue (встроенный в python-telegram-bot) + Heartbeat на апдейтах |
| Деплой | Timeweb VPS (189 ₽/мес) — 1 vCPU, 1 GB RAM, 10 GB NVMe |
| Тестирование | pytest + pytest-asyncio + httpx + aioresponses |

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────┐
│  Telegram Bot   │◄───►│  Backend (FastAPI)│◄───►│ SQLite  │
│  (python-telegram-bot)│  + Web App Host   │     │ bot.db  │
└─────────────────┘     └──────────────────┘     └─────────┘
                                │
                         ┌──────┴──────┐
                         │  Telegram   │
                         │  Web App    │
                         │ (HTML/JS)   │
                         └─────────────┘
```

## Модели данных (SQLAlchemy)

- **Admin** — id, user_id (telegram), username
- **Channel** — id, chat_id, title, booking_horizon_days, default_notify_minutes
- **Slot** — id, channel_id (FK), date, start_time, end_time, is_active, created_by (admin_id)
- **Booking** — id, slot_id (FK), user_id (telegram), user_name, comment, created_at, notify_minutes
- **Notification** — id, booking_id (FK), user_id, notify_at (datetime), sent (bool), job_id (str)
- **AuditLog** — id, action (str), user_id, slot_id, booking_id, details (JSON), created_at

### Индексы и ограничения
- `Booking`: уникальный индекс `(user_id, slot_id)` — защита от двойного нажатия на кнопку
- `Slot`: уникальный индекс `(channel_id, date, start_time)` — один слот не создать дважды
- `Notification`: индекс по `(notify_at, sent)` — быстрый поиск просроченных уведомлений

## Безопасность

### Критические меры (встраиваются с Milestone 1)

| Угроза | Мера | Где реализуется |
|--------|------|----------------|
| Доступ к VPS | SSH только по ключу, fail2ban, пользователь `tbot` вместо root | Деплой |
| Утечка токена | `.env` в `.gitignore`, права 600 на файл | Milestone 1 |
| Подделка hash в Web App | Валидация initData через HMAC-SHA256 с токеном бота | Milestone 2-3 |
| Race condition при брони | `select_for_update()` внутри транзакции | Milestone 3 |
| Повреждение SQLite | `PRAGMA journal_mode=WAL`, `busy_timeout=5000` | Milestone 1 |
| SQL-инъекции | Только параметризованные запросы через SQLAlchemy | Milestone 1 |
| Неавторизованный админ | Проверка через `getChatAdministrators` + кеш 5 мин | Milestone 2 |
| Флуд бронированиями | Anti-flood: не чаще 1 действия / 5 сек на пользователя | Milestone 3 |
| Дублирование уведомлений | Флаг `sent = False` в Notification + идемпотентность | Milestone 3 |
| Rate limit Telegram | `DefaultRateLimiter` из python-telegram-bot | Milestone 1 |

### Обязательные паттерны в коде

```python
# 1. Все админ-команды — через декоратор @check_admin()
# 2. Все Web App запросы — validate_init_data() перед обработкой
# 3. Бронирование — внутри транзакции с select_for_update
# 4. SQLite — journal_mode=WAL, busy_timeout=5000 при подключении
# 5. .gitignore — .env, bot.db, __pycache__/
# 6. Rate limiter — включён DefaultRateLimiter при старте бота
# 7. Уведомления — идемпотентны (проверка sent = False)
# 8. AuditLog — логировать каждое изменение (создание слота, бронь, отмена)
# 9. Graceful shutdown — SIGTERM → остановить JobQueue → закрыть БД
# 10. Web App — проверять window.Telegram.WebApp.initDataUnsigned перед отправкой на бэкенд
```

## Логирование и обработка ошибок

### Уровни логирования
| Уровень | Куда пишем | Что попадает |
|---------|-----------|-------------|
| `ERROR` | stderr + файл `logs/error.log` | Ошибки БД, сбои JobQueue, исключения в хендлерах |
| `WARNING` | stderr + файл `logs/error.log` | Anti-flood сработал, невалидный initData, превышение лимитов |
| `INFO` | stdout | Бронирование, отмена, создание слота, отправка уведомления |
| `DEBUG` | stdout (только dev) | Все запросы к API, тело ответов, SQL-запросы |

### Стратегия при ошибках
1. **Ошибка БД** — пользователю: «Техническая ошибка, попробуйте позже». Админу в личку: «⚠️ Ошибка БД: ...»
2. **Ошибка JobQueue** — уведомление догонит Heartbeat при следующем апдейте. Логируем.
3. **Ошибка Telegram API** — повтор через 3 секунды (max 3 попытки). Если не удалось — логируем, пропускаем.
4. **Невалидный initData** — отклоняем запрос, логируем user_id и IP.

### Уведомление админа о сбоях
- Критические ошибки дублируются в личное сообщение админу
- Heartbeat при старте отчитывается: «Бот запущен, догнал X просроченных уведомлений»

## Graceful Shutdown

При получении `SIGTERM` / `SIGINT`:
1. Останавливаем принятие новых апдейтов (бот перестаёт отвечать)
2. JobQueue завершает текущие задачи (не запускает новые)
3. Закрываем все соединения с SQLite
4. Выходим с кодом 0

**Почему это важно:**
- JobQueue не теряет задачи, которые должны были сработать «вот-вот» — они попадут в БД со статусом `sent = False`
- SQLite не остаётся в «горячем» состоянии (WAL checkpoint)
- При перезапуске Heartbeat догонит всё, что не успело отправиться

```python
# Обработка сигналов (регистрируется при старте)
async def shutdown_handler(sig, frame):
    logger.info(f"Получен сигнал {sig}, начинаю graceful shutdown")
    await application.stop()   # остановить бота + JobQueue
    await application.shutdown()
    await engine.dispose()     # закрыть SQLAlchemy
    loop.stop()
```

## Ограничения SQLite и стратегия роста

### Когда SQLite работает хорошо
- До ~1000 активных пользователей в день
- До ~50 одновременных запросов на запись
- Объём данных до ~1 GB (миллионы броней)

### Когда нужен переход на PostgreSQL
- Одновременных бронирований > 20-30 в секунду (начинаются `database is locked`)
- Планируется шардирование или репликация
- Требуется более гибкая система прав доступа

### Стратегия миграции (если понадобится)
1. Все запросы через SQLAlchemy — ORM абстрагирует БД
2. Меняется только `DATABASE_URL` в `.env`:
   - `sqlite+aiosqlite:///bot.db` → `postgresql+asyncpg://user:pass@host/db`
3. WAL-специфичные прагмы убираются, PostgreSQL использует свои настройки
4. Рекомендуемый провайдер при миграции: **Timeweb PostgreSQL** (от 150 ₽/мес) или **Selectel Managed DB**

## Web App — защита API-эндпоинтов

### Проверка на клиенте (JS)
```javascript
// Проверяем, что Web App открыт внутри Telegram
if (!window.Telegram || !window.Telegram.WebApp) {
    document.body.innerHTML = 'Это приложение доступно только внутри Telegram';
    throw new Error('Not in Telegram');
}
const initData = window.Telegram.WebApp.initData;  // строка для отправки на бэкенд
```

### Проверка на сервере (Python)
```python
from hashlib import sha256
import hmac
import urllib.parse

def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись initData из Telegram Web App."""
    parsed = dict(urllib.parse.parse_qsl(init_data))
    hash_received = parsed.pop('hash', None)
    if not hash_received:
        return None
    
    secret_key = hmac.new(
        b'WebAppData', bot_token.encode(), sha256
    ).digest()
    
    data_check_string = '\n'.join(
        f'{k}={v}' for k, v in sorted(parsed.items())
    )
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), sha256
    ).hexdigest()
    
    if hmac.compare_digest(expected_hash, hash_received):
        return parsed  # валидно — возвращаем данные пользователя
    return None
```

### Защита от внешних запросов
- Все API-эндпоинты Web App проверяют initData
- Эндпоинты без initData (`/health`) не раскрывают пользовательских данных
- CORS настроен только на домен Telegram (или отключён для Web App)

## AuditLog — аудит действий

Логируются все ключевые операции для возможности отката изменений и разбора инцидентов.

| Действие | audit_log.action | Детали |
|----------|-----------------|--------|
| Создание слота | `slot_created` | admin_id, date, start_time, end_time |
| Удаление слота | `slot_deleted` | admin_id, slot_id |
| Бронирование | `booking_created` | user_id, slot_id, notify_minutes |
| Отмена брони | `booking_cancelled` | user_id, slot_id, cause (user/admin) |
| Изменение брони | `booking_changed` | user_id, old_slot_id, new_slot_id |
| Уведомление отправлено | `notification_sent` | booking_id, notify_at |
| Попытка взлома | `security_alert` | user_id, reason (invalid_hash, flood, etc.) |

```sql
-- AuditLog не влияет на производительность — вставки идут асинхронно, без ожидания
INSERT INTO audit_log (action, user_id, slot_id, booking_id, details)
VALUES ('booking_created', 12345, 678, 910, '{"notify_minutes": 10}');
```

## Защита от «забытых» броней

Пользователь забронировал слот, но не пришёл — слот простаивает.

### Автоматические правила
- **N часов до начала:** если пользователь не взаимодействовал с ботом > 24ч → бот отправляет запрос на подтверждение. Если нет ответа за 1 час → бронь отменяется, слот свободен.
- **После начала слота:** если прошло 15 минут, а пользователь не отметился → админ получает уведомление, может форсированно освободить слот.

### Для админа
- Команда `/free_slot <id>` — принудительно освободить слот
- Команда `/bookings` — посмотреть все активные брони с таймером «сколько осталось до начала»

## Планировщик уведомлений

### Механизм A — JobQueue (основной, точный)
Встроенный JobQueue python-telegram-bot. При бронировании регистрируется задача `run_once` на время `start_time - notify_minutes`.

### Механизм B — Heartbeat (страховочный)
При каждом апдейте от пользователя (команда, кнопка, Web App) и при старте бота — проверка просроченных непосланных уведомлений в БД.

```
Бронирование → notify_at = start_time - notify_minutes
    ↓
JobQueue.run_once(callback, when=notify_at) + запись в SQLite
    ↓
В notify_at → JobQueue шлёт уведомление → sent = True
    ↓
При перезагрузке → check_pending() при старте догоняет просрочку
    ↓
При любом апдейте → check_pending() как страховка
```

## Команды бота

### Админ
- `/setup` — привязать бота к каналу
- `/create_slots` — открыть Web App для создания слотов (даты + часы)
- `/slots` — просмотр/редактирование слотов
- `/settings` — настройки: горизонт бронирования, время уведомлений
- `/broadcast` — отправить сообщение с кнопкой "📅 Забронировать" в канал

### Пользователи
- Кнопка "📅 Забронировать" в канале → Web App
- Web App: календарь → дата → свободные часы → бронирование
- Мои брони: просмотр, отмена, изменение
- Таблица: кто занял какие слоты (дата, время, пользователь)

## UX Flow

```
Админ → /create_slots → Web App (выбор дат и часов)
    ↓
Бот публикует сообщение с кнопкой "📅 Забронировать"
    ↓
Пользователь → кнопка → Web App
    ↓
Web App: календарь → дата → свободные часы → бронь
    ↓
JobQueue регистрирует задачу через run_once
    ↓
Бот → подтверждение в личку
    ↓
В notify_at → JobQueue → уведомление в личку
    ↓
При любом апдейте → Heartbeat check_pending()
```

## Этапы реализации

### Этап 1 — Основа
- [ ] Инициализация проекта (FastAPI + бот)
- [ ] Модели SQLAlchemy + SQLite
- [ ] Базовый каркас: запуск бота и API
- [ ] Команда `/start`

### Этап 2 — Админ-панель
- [ ] Проверка прав админа
- [ ] Команды: `/setup`, `/create_slots`
- [ ] Web App для создания слотов (выбор даты, выбор часов)
- [ ] Сохранение слотов в БД
- [ ] `/broadcast` — публикация кнопки бронирования в канал

### Этап 3 — Бронирование
- [ ] Web App для пользователей: календарь, список свободных слотов
- [ ] Логика бронирования (запись в Booking + Notification)
- [ ] JobQueue: регистрация уведомления
- [ ] Heartbeat: check_pending() при старте и на апдейтах
- [ ] Подтверждение брони (личное сообщение)
- [ ] Таблица занятых слотов (кто, когда, какое время)

### Этап 4 — Отмена и изменение
- [ ] Отмена брони (удаление Notification + JobQueue.remove_job)
- [ ] Изменение слота (пересоздание уведомления)
- [ ] Оповещение админа об отмене (опционально)

### Этап 5 — Полировка и доп. фичи
- [ ] Временные зоны пользователей
- [ ] Очередь ожидания на занятые слоты
- [ ] Экспорт расписания
- [ ] Dockerfile + docker-compose (опционально)

## Конфигурация (.env)

```
BOT_TOKEN=токен_бота
CHANNEL_USERNAME=@название_канала
WEB_APP_URL=https://домен/webapp
DATABASE_URL=sqlite+aiosqlite:///bot.db
```

## Запуск (dev)

```bash
pip install -r requirements.txt
python -m app.main
```

## Деплой на Timeweb (189 ₽/мес)

### Тариф
**Timeweb VPS «Start»** — 189 ₽/мес (акция, далее ~350 ₽):
- 1 vCPU, 1 GB RAM, 10 GB NVMe
- 100 Mbps, безлимитный трафик
- Дата-центр: Москва или Санкт-Петербург
- Оплата: MIR, СБП, USDT (TRC-20)

### Подготовка VPS
```bash
# Подключение
ssh root@<ip-сервера>

# Обновление системы
apt update && apt upgrade -y

# Установка Python и зависимостей
apt install -y python3 python3-venv python3-pip git
```

### Развёртывание
```bash
# Клонирование репозитория
git clone <url-репозитория> /opt/tBotSheduler
cd /opt/tBotSheduler

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Создание .env
cp .env.example .env
nano .env  # BOT_TOKEN, CHANNEL_USERNAME, WEB_APP_URL
```

### systemd сервис
```ini
# /etc/systemd/system/tbotsheduler.service
[Unit]
Description=tBotSheduler
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tBotSheduler
ExecStart=/opt/tBotSheduler/venv/bin/python -m app.main
Restart=always
RestartSec=10
Environment="PATH=/opt/tBotSheduler/venv/bin"
EnvironmentFile=/opt/tBotSheduler/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable tbotsheduler
systemctl start tbotsheduler
systemctl status tbotsheduler  # проверить
```

### Мониторинг
```bash
journalctl -u tbotsheduler -f  # логи в реальном времени
journalctl -u tbotsheduler --since "1 hour ago"  # логи за час
```

### Обновление
```bash
cd /opt/tBotSheduler
git pull
systemctl restart tbotsheduler
```

### Бэкап SQLite
```bash
# Ежедневный бэкап через cron
0 3 * * * cp /opt/tBotSheduler/bot.db /opt/tBotSheduler/backups/bot-$(date +\%Y\%m\%d).db
# Хранить 7 дней
0 3 * * * find /opt/tBotSheduler/backups/ -name "bot-*.db" -mtime +7 -delete
```

### Особенности Timeweb
- **IP адрес:** при пересоздании сервера IP меняется. Если используете webhook (не long polling), закрепите IP через дополнительный сервис или используйте домен
- **Снапшоты:** бесплатно — 1 снапшот на VPS. Делайте снапшот перед крупными обновлениями
- **Смена тарифа:** требует переустановки ОС. Данные на системном диске теряются — храните `bot.db` на отдельном томе, если планируете апгрейд
- **Мониторинг:** в панели Timeweb доступны графики CPU/RAM/disk. Настройте алерты при загрузке CPU > 80% и при заполнении диска > 85%
- **Поддержка:** тикеты через панель управления, время ответа — от 15 минут до 2 часов в рабочее время

FastAPI: http://localhost:8000
Бот запускается вместе с FastAPI (lifespan event)

## Тестирование

### Подход
**TDD (Test-Driven Development)** — тесты пишутся до реализации. Каждая фича начинается с падающего теста, который описывает ожидаемое поведение.

### Уровни тестов

```
┌─────────────────────────────────────┐
│           E2E (end-to-end)          │  ← бот + Web App + Telegram API (mock)
│   pytest + httpx + aioresponses     │
├─────────────────────────────────────┤
│       Интеграционные тесты          │  ← БД + JobQueue + хендлеры
│   pytest-asyncio + SQLite (:memory:) │
├─────────────────────────────────────┤
│          Юнит-тесты                 │  ← модели, валидация, утилиты
│   pytest (чистые функции)           │
└─────────────────────────────────────┘
```

### Стек тестирования

| Инструмент | Назначение |
|-----------|-----------|
| `pytest` | Основной раннер |
| `pytest-asyncio` | Асинхронные тесты (бот, FastAPI, БД) |
| `httpx.AsyncClient` | Тестирование FastAPI эндпоинтов |
| `aioresponses` / `respx` | Mock Telegram Bot API |
| `sqlite3 :memory:` | Интеграционные тесты БД (чистый старт каждый тест) |
| `pytest-cov` | Замер покрытия |
| `pytest-xdist` | Параллельный запуск тестов |

### Структура тестового проекта

```
tests/
├── conftest.py              # фикстуры: БД, бот, клиент, моки
├── unit/
│   ├── test_models.py       # тесты SQLAlchemy моделей (создание, связи, индексы)
│   ├── test_validators.py   # тесты валидации initData, anti-flood, прав
│   ├── test_scheduler.py    # тесты логики JobQueue + Heartbeat (чистая логика)
│   └── test_security.py     # тесты HMAC, проверки админа, уникальности индексов
├── integration/
│   ├── test_repository.py   # CRUD операции через репозиторий (с SQLite in-memory)
│   ├── test_handlers.py     # хендлеры бота с mock Telegram API
│   ├── test_api.py          # FastAPI эндпоинты (/health, /api/book, /api/cancel)
│   ├── test_notifications.py # полный цикл: бронь → JobQueue → отправка → чек
│   └── test_booking_flow.py # сквозной сценарий: слот → бронь → отмена
└── e2e/
    ├── test_full_scenario.py    # полный сценарий: админ → слот → юзер → бронь → уведомление → отмена
    ├── test_race_conditions.py  # конкурентные бронирования, двойной клик
    └── test_error_scenarios.py  # сломанный initData, слот занят, бот упал и встал
```

### Фикстуры (conftest.py)

```python
@pytest.fixture
async def db():
    """SQLite in-memory БД для каждого теста — чистое состояние."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
def mock_telegram_api():
    """Mock ответов Telegram Bot API (getChatAdministrators, sendMessage и т.д.)."""
    with aioresponses() as m:
        yield m

@pytest.fixture
async def app():
    """FastAPI app + бот (mock Telegram token)."""
    ...

@pytest.fixture
async def client(app):
    """Async HTTP клиент для тестов FastAPI."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

### Критические сценарии для тестов

#### Юнит
- Создание всех моделей с валидными данными
- Уникальные индексы: дубликат брони, дубликат слота → ошибка
- Валидация initData: правильный hash → OK, неправильный → None
- Anti-flood: 1 запрос → OK, 2 запроса за 3 сек → блок

#### Интеграционные
- CRUD: создать слот → забронировать → прочитать бронь → отменить
- JobQueue: регистрация задачи → запуск в нужное время → отправка
- Heartbeat: запуск `check_pending()` с просроченными → отправляются
- FastAPI healthcheck: `/health` → 200 OK

#### E2E
- Полный сценарий: админ логинится → создаёт слоты → broadcast → юзер бронирует → уведомление → отмена
- Race condition: 5 одновременных броней на 1 слот → проходит только 1
- Восстановление после падения: бот упал → перезапустился → Heartbeat догнал уведомления

### Покрытие

**Цель:** минимум 80% покрытия кода (lines + branches) для production-модулей.

Измеряется `pytest-cov`, проверяется в CI:

```bash
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

### TDD-цикл для каждой фичи

```
1. Написать тест (падает — RED)
2. Написать минимальную реализацию (тест проходит — GREEN)
3. Рефакторинг кода (тест всё ещё проходит — REFACTOR)
```

### Что не тестируется
- Статика Web App (HTML/CSS/JS) — визуальная верификация вручную
- Интеграция с реальным Telegram API (используем mock)
- Производительность под нагрузкой (отдельное нагрузочное тестирование)

