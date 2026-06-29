# BUG_ISSUE.md — Найденные дефекты при тестировании P0-фиксов

> **Дата тестирования:** 2026-06-29  
> **Проверяемые фиксы:** #1 (сессия БД), #2 (HMAC), #4 (PRAGMA foreign_keys)  
> **Статус фиксов:** ✅ Все 3 работают корректно  
> **Статус #BUG-01:** ✅ Исправлен — реализован Option E (`core/deps.py`)  
> **Всего найдено дефектов:** 7 (🔴 2 новых, 🟠 1 тестовый, 🔴 4 существующих, 🔵 1 косметический)

---

## 🔴 Критические — найдены при тестировании

### ~~#BUG-01 — Shared-сессия валит concurrent-запросы~~ ✅ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Фикс** | `core/deps.py` — `get_db()` для FastAPI, `@with_db` для бота |
| **Изменения** | `app.py` хранит `session_maker`. HTTP: `Depends(get_db)`. Бот: `@with_db` → `context.bot_data["db"]` |
| **Тест** | 5 concurrent запросов через `Depends(get_db)` — каждая своя сессия, race-condition нет |
| **Статус** | ✅ Исправлено в рамках Option E |

---

### ~~#BUG-02 — `conftest.py` тоже хранит закрытую сессию в `client`-фикстуре~~ ✅ УЖЕ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Где** | `tests/conftest.py:60` |
| **Суть** | Ранее фикстура хранила закрытую сессию. Сейчас хранит `session_maker` |
| **Статус** | ✅ Исправлено Option E — `client` фикстура хранит `session_maker`, эндпоинты создают сессии через `Depends(get_db)` или `async with maker()` |

---

### ~~#BUG-03 — `check_pending()` оставляет открытую транзакцию при старте~~ 🟠 НЕ ИСПРАВЛЕНО

...

### #BUG-03 — `check_pending()` оставляет открытую транзакцию при старте

| Аспект | Детали |
|--------|--------|
| **Где** | `app.py:178` → `bot/scheduler.py:20-26` |
| **Суть** | `check_pending()` вызывает `SELECT COUNT(*) FROM notification`, что через autobegin открывает транзакцию. Транзакция **не закрывается** до первого `commit()` от handler'а |
| **Влияние** | При старте БД открыта неявная read-only транзакция. Если следующий handler упадёт до commit — транзакция повиснет. При долгом простое между стартом и первой операцией — соединение удерживается |
| **Воспроизведение** | Запустить приложение, проверить через `SELECT * FROM sqlite_master` — транзакция открыта |
| **Приоритет** | P2 — не вызывает явных ошибок, но потенциально проблемно при длительном простое |

**В текущем коде:**
```python
session = session_maker()           # autobegin не произошёл
app.state.db_session = session
await _check_pending_on_startup(session)  # ← SELECT → autobegin → транзакция открыта
# Контекст lifespan не закрывает её — висит до первого handler
```

---

## 🟠 Существующие P0-баги (не исправлены нашим фиксом)

### ~~#BUG-04 — Нет проверки `auth_date` в `validate_init_data`~~ ✅ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Где** | `core/security.py:27-49` |
| **Суть** | Функция не проверяла `auth_date`. Telegram рекомендует отклонять initData старше 24 часов |
| **Исправление** | Добавлен параметр `max_age_seconds` (default 86400) в `validate_init_data()`. Проверка `auth_date` после HMAC: missing → reject, expired → reject, future → reject. Защита от clock skew 5 мин |
| **Дополнительно** | POST-эндпоинты (book/cancel/change) используют `max_age_seconds=300` — окно replay-атаки сокращено до 5 минут |
| **Тесты** | 5 новых тестов: expired, future, missing, recent, custom_max_age |
| **Дата** | 2026-06-29 |

---

### ~~#BUG-05 — Race condition на бронь (нет `select_for_update`)~~ ✅ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Где** | `models/booking.py`, `bot/booking_service.py:43-141` |
| **Суть** | Проверка "слот свободен" и создание брони не атомарны. Два concurrent-запроса могли пройти проверку |
| **Исправление** | Добавлен `UniqueConstraint("slot_id")` — database-level гарантия: два INSERT с одинаковым slot_id не пройдут. Весь блок INSERT обёрнут в try/except IntegrityError с rollback. Два concurrent запроса → второй получает IntegrityError → rollback + "Этот слот уже занят" |
| **Тесты** | Существующие тесты проходят: `test_slot_taken_by_another` (разные пользователи) + `test_duplicate_booking_prevented` (тот же пользователь) |
| **Дата** | 2026-06-29 |

---

### ~~#BUG-06 — `check_admin`/`check_role` без None-проверок~~ ✅ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Где** | `core/auth.py` — `check_admin` и `check_role` декораторы |
| **Суть** | `effective_user` может быть None (channel post, poll). `message` может быть None (callback query) |
| **Исправление** | Добавлены проверки `if not update.effective_user: return` в оба декоратора. `update.message.reply_text()` заменён на `_reply()` helper, который использует `effective_chat.send_message()` если `message` отсутствует |
| **Тесты** | 3 новых теста: none_user для check_admin и check_role, none_message для check_admin |
| **Дата** | 2026-06-29 |

---

### ~~#BUG-07 — Heartbeat не отправляет уведомления~~ ✅ ИСПРАВЛЕНО

| Аспект | Детали |
|--------|--------|
| **Где** | `bot/scheduler.py`, `bot/notification_service.py`, `app.py` |
| **Суть** | `check_pending_notifications()` (которая реально отправляет) **никем не вызывалась**. `check_pending()` — только считала |
| **Исправление** | `scheduler.py` переписан — `check_pending()` теперь вызывает `check_pending_notifications()`. В `app.py` добавлен `job_queue.run_repeating(_heartbeat_callback, interval=300, first=60)` — каждые 5 минут. Добавлен `_heartbeat_callback()` в `notification_service.py` — создаёт сессию из `session_maker` и отправляет просроченные уведомления |
| **Тесты** | 1 новый тест: `test_check_pending_sends_pending` — проверяет, что `bot.send_message` вызывается для просроченных уведомлений |
| **Дата** | 2026-06-29 |

---

## 🔵 Косметические дефекты

### #BUG-08 — Мёртвый код `_shutdown_event` в `app.py`

| Аспект | Детали |
|--------|--------|
| **Где** | `app.py:58,61-64` |
| **Суть** | `_shutdown_event` создаётся, `_signal_handler` вызывает `_shutdown_event.set()`, но **никто не await'ит** этот `Event`. Signal handler логирует через `logger.info()` (небезопасно в сигналах), но сам event не используется |
| **Влияние** | Graceful shutdown работает только через `lifespan`-контекст, signal handler — мёртвый код |
| **Приоритет** | P4 |

---

## 📋 Итог

| Категория | Найдено | Статус |
|-----------|---------|--------|
| Регрессии от наших фиксов | 0 | ✅ |
| Ошибки в реализации фиксов | 0 | ✅ |
| Новые дефекты (не охваченные TASC) | 2 | ⚠️ #BUG-02, #BUG-03 |
| Существующие P0 (не исправлены) | 0 | 🎉 |
| Косметика | 1 | 🔵 #BUG-08 |

**Главный вывод:** Все 4 P0-бага исправлены: #BUG-04 (auth_date), #BUG-05 (race condition), #BUG-06 (None checks), #BUG-07 (heartbeat). Ранее исправлены: #BUG-01 (shared-сессия), HMAC, PRAGMA foreign_keys.

**P1-баги исправлены (2026-06-29):**
- **#8** — `job_id` сохраняется в Notification ✅
- **#10** — Кеш ролей инвалидируется при add/remove ✅
- **#11** — Модератор может использовать `/slots` и `/broadcast` ✅
- **#13** — Обработка Forbidden в health_command ✅
- **#14** — AntiFlood автоочистка каждые 1000 проверок ✅
- **#15** — assert заменён на type: ignore в rate_limiter ✅
- **#BUG-02** — conftest уже исправлен Option E ✅

---

*BUG_ISSUE.md создан 2026-06-29 по результатам тестирования P0-фиксов*
