# TASC — Технический Анализ и Спецификация Ошибок

> **Проект:** tBotSheduler  
> **Дата анализа:** 2026-06-29  
> **Ветка:** `dev`  
> **Версия:** 0.1.0  
> **Всего ошибок:** 35 (🔴 0 · 🟠 0 · 🟡 0 · 🔵 10 · ✅ 25)

---

## 🔴 Критические (7)

### #1 — Закрытая сессия БД передаётся всем хендлерам

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/app.py:176-178, 214` |
| **Суть** | Сессия создаётся внутри `async with session_maker() as session:` и закрывается при выходе из блока. Ссылка на закрытую сессию сохраняется в `app.state.db_session` и `bot_app.bot_data["db_session"]`. |
| **Влияние** | Все хендлеры бота и API-эндпоинты получают закрытую сессию. Любая операция с БД валится с `sqlalchemy.exc.InvalidRequestError`. |
| **Исправление** | Создавать новую сессию на каждый запрос через `session_maker()`. Хранить в `app.state` только `session_maker`. |
| **Метрика** | 1 источник → 8 файлов-потребителей |

### #2 — Ключ и сообщение HMAC перепутаны в `validate_init_data`

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/security.py:34-36` |
| **Суть** | Аргументы `hmac.new()` перепутаны: `b"WebAppData"` передан как ключ, а `bot_token` — как сообщение. По спецификации Telegram: `HMAC_SHA256(bot_token, "WebAppData")`. |
| **Влияние** | Валидация initData Web App **всегда падает**. Пользователи не могут забронировать слот через Web App. |
| **Исправление** | `hmac.new(bot_token.encode(), b"WebAppData", hashlib.sha256)` |
| **Метрика** | 1 строка → блокировка всего Web App |

### #3 — Нет проверки `auth_date` в initData

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/security.py:27-49` |
| **Суть** | Функция `validate_init_data` не проверяет поле `auth_date` (Unix timestamp). Telegram рекомендует отклонять initData старше 24 часов. |
| **Влияние** | Перехваченный initData можно воспроизводить бесконечно. **Replay-атака** на все API-эндпоинты Web App. |
| **Исправление** | После HMAC-проверки: `if int(parsed.get("auth_date", 0)) < time.time() - 86400: return None` |
| **Метрика** | 4 эндпоинта без защиты от replay |

### #4 — PRAGMA foreign_keys не применяется к сессиям

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/database.py:35-38` |
| **Суть** | `PRAGMA foreign_keys=ON` и `busy_timeout=5000` устанавливаются только на соединении для инициализации (`engine.connect()`). Каждая новая сессия создаёт новое соединение (по умолчанию SQLite `foreign_keys=OFF`). |
| **Влияние** | Все `ForeignKey`, `ondelete="CASCADE"`, `ondelete="SET NULL"` — **не работают**. При конкурентной записи — `SQLITE_BUSY`. |
| **Исправление** | Добавить `PoolEvents.connect` или передавать PRAGMA через `connect_args` / `sqlite_foreign_keys=True` в URL. |
| **Метрика** | 7 моделей × FK-поля без защиты |

### #5 — Race condition: два пользователя могут забронировать один слот

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/booking_service.py:85-88` |
| **Суть** | Проверка "слот свободен" и создание брони — не атомарны. Два concurrent-запроса могут пройти проверку до коммита. `select_for_update()` не используется. |
| **Влияние** | **Двойная бронь одного слота** разными пользователями. |
| **Исправление** | `select_for_update()` внутри транзакции, или уникальный индекс на `slot_id` (одна бронь на слот). |
| **Метрика** | 3 места без `select_for_update` (create_booking, cancel_booking, change_booking) |

### #6 — Нет проверки `update.effective_user` и `update.message` на None

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/auth.py:79, 84-86, 124, 129-131, 142-144` |
| **Суть** | `update.effective_user` может быть None (channel post, poll), `update.message` может быть None (callback query, inline). Декораторы `check_admin` и `check_role` падают с `AttributeError`. |
| **Влияние** | **Любая callback-кнопка роняет бота.** Любой channel post — падение. |
| **Исправление** | `if not update.effective_user: return`, `if not update.message: await update.effective_chat.send_message(...)` или `return` |
| **Метрика** | 2 декоратора × 3 точки отказа = 6 мест |

### #7 — Heartbeat-страховка не работает

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/notification_service.py:95` (не вызывается), `src/tbot_sheduler/bot/scheduler.py:12-31` (только COUNT) |
| **Суть** | `check_pending_notifications()` определена, но **никем не вызывается**. `check_pending()` только считает количество, но не отправляет. JobQueue callback не ставит `sent=True`. |
| **Влияние** | При перезапуске бота все уведомления, не успевшие отправиться, **потеряны**. Нет страховочного механизма. |
| **Исправление** | Звать `check_pending_notifications()` при старте и на каждом апдейте. Добавить `sent = True` в JobQueue callback. |
| **Метрика** | 3 взаимосвязанных бага в одном механизме |

---

## 🟠 Высокие (8)

### #8 — ~~job_id никогда не сохраняется в Notification~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/booking_service.py:109-116`, `notification_service.py:62` |
| **Суть** | `schedule_notification()` возвращает `job.name`, но не сохраняет его. |
| **Исправление** | `schedule_notification()` принимает `db_session` и пишет `job_id` в Notification. |
| **Статус** | ✅ Исправлено — тесты `test_notification_service.py` |

### #9 — ~~change_booking() не атомарна (потеря брони)~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/booking_service.py:212, 220, 243` |
| **Суть** | `cancel_booking()` коммитит удаление старой брони. Если `create_booking()` нового слота падает, старый слот уже свободен. |
| **Влияние** | **Потеря брони при сбое изменения.** |
| **Исправление** | `change_booking()` переписан: вся логика (delete old + create new + audit) в одной транзакции, один `commit()`. При IntegrityError — rollback. Сохраняет `comment` из старой брони. |
| **Статус** | ✅ Исправлено — тест `test_change_booking_atomicity` |
| **Влияние на пользователя** | Потеря места |

### #10 — ~~Кеш ролей без инвалидации~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/auth.py:44-48` |
| **Суть** | `_role_cache` не очищался при изменении роли. |
| **Исправление** | Добавлена `invalidate_role_cache(user_id)` — вызывается из add/remove moderator/developer. |
| **Статус** | ✅ Исправлено |

### #11 — ~~Модератор не может использовать /slots и /broadcast~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/slot_handlers.py:79-82, 215-217` |
| **Суть** | Поиск канала только по `owner_id` — модераторы не находили канал. |
| **Исправление** | `_get_channel_for_admin()`: owner → `admin.id`, moderator → `admin.added_by`. |
| **Статус** | ✅ Исправлено |

### #12 — ~~AttributeError в added_by~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/admin_handlers.py:119-123` |
| **Суть** | `.id` на возможном `None` (если админ не найден в БД между проверкой `@check_role` и выполнением). |
| **Влияние** | Падение `/add_moderator` при редких state-условиях. |
| **Исправление** | Query вынесен в отдельную переменную, проверка `if acting_admin: .id else None`. |
| **Статус** | ✅ Исправлено |
| **Влияние на пользователя** | 500-ошибка, бот не отвечает |

### #13 — ~~Нет обработки Forbidden при отправке в ЛС~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/developer_handlers.py:80-88` |
| **Суть** | `/health` из группы не сообщал об ошибке при Forbidden. |
| **Исправление** | try/except TelegramForbidden → fallback с показом результата в группе. |
| **Статус** | ✅ Исправлено |

### #14 — ~~Утечка памяти в AntiFlood~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/security.py:77-86` |
| **Суть** | `cleanup()` никогда не вызывался. |
| **Исправление** | Автоочистка каждые 1000 вызовов `check()`. `_cleanup()` удаляет записи старше 1 часа. |
| **Статус** | ✅ Исправлено |

### #15 — ~~assert удаляется в python -O~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/core/rate_limiter.py:51, 73` |
| **Суть** | `assert self._lock is not None` — удаляется в `python -O`. |
| **Исправление** | Assert'ы убраны. `_ensure_lock()` уже гарантирует инициализацию lock'а. |
| **Статус** | ✅ Исправлено — тесты проходят с `python -O` |

---

## 🟡 Средние (10)

### #16 — ~~Единственная AsyncSession на все concurrent-запросы~~ ✅ Исправлено (Option E)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/app.py:176-178` |
| **Суть** | Одна `AsyncSession` хранится в `app.state` и используется всеми concurrent-запросами. |
| **Влияние** | Перекрёстное загрязнение identity map, состояние гонки на commit/rollback. |
| **Исправление** | Создавать сессию на каждый запрос из session_maker. |

### #17 — ~~N+1 запросы в booking_service~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/booking_service.py:31, 261` |
| **Суть** | `len(slot.bookings)` (lazy load) и `db_session.get(Slot, booking.slot_id)` в цикле. |
| **Влияние** | O(N+1) SQL-запросов вместо O(2). При 50 слотах → 51 запрос. |
| **Исправление** | `selectinload(Slot.bookings)` и `selectinload(Booking.slot)` или `joinedload`. |

### #18 — ~~change_booking() теряет comment~~ ✅ Исправлено (2026-06-29, вместе с #9)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/booking_service.py:220-226` |
| **Суть** | `create_booking()` вызывается без `comment`. `ChangeRequest` Pydantic-модель не имеет поля `comment`. |
| **Влияние** | Комментарий теряется при смене слота. |
| **Исправление** | Добавить `comment` в `ChangeRequest` и передавать в `change_booking()`. |

### #19 — ~~free_slot не уведомляет ожидающих~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/slot_handlers.py:167-177` |
| **Суть** | После освобождения слота не вызывается `notify_waiting_users()`. |
| **Влияние** | Ожидающие пользователи не получают уведомление о свободном слоте. |
| **Исправление** | Вызвать `waiting_service.notify_waiting_users()` после удаления брони. |

### #20 — ~~join_waiting не проверяет занятость слота~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/waiting_service.py:23-27` |
| **Суть** | Проверяется только существование слота, но не его занятость. |
| **Влияние** | Можно встать в очередь на свободный слот. |
| **Исправление** | Добавить проверку `select(Booking).where(Booking.slot_id == slot_id)`. |

### #21 — ~~Очистка списка ожидания при ошибках отправки~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/waiting_service.py:98-102` |
| **Суть** | Список очищается безусловно, даже если часть уведомлений не отправлена (Forbidden). |
| **Влияние** | Пользователь теряет место в очереди без уведомления. |
| **Исправление** | Очищать только успешно уведомлённых. |

### #22 — ~~Мёртвый код в forgotten_service.py~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/forgotten_service.py` (весь файл) |
| **Суть** | `check_inactive_bookings()`, `confirm_booking()` нигде не вызываются. |
| **Влияние** | Авто-отмена забытых броней не работает. |
| **Исправление** | Подключить вызов в heartbeat или JobQueue. |

### #23 — ~~export_service берёт произвольную бронь~~ ✅ Исправлено (защищено #5)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/export_service.py:47, 80` |
| **Суть** | `bookings[0]` при нескольких бронях на один слот (нет гарантии порядка). |
| **Влияние** | Экспорт показывает только одну бронь из нескольких. |
| **Исправление** | Выводить все бронирования или агрегировать. |

### #24 — ~~Доступ к внутреннему API APScheduler~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/api/booking.py:178` |
| **Суть** | `job_queue.scheduler.remove_job()` — непубличный атрибут. |
| **Влияние** | Поломка при обновлении APScheduler. |
| **Исправление** | Использовать public API JobQueue, либо корректно сохранять job_id. |

### #25 — ~~Наивные datetime без timezone~~ ✅ Исправлено (2026-06-29)

| Аспект | Детали |
|--------|--------|
| **Файл** | `src/tbot_sheduler/bot/notification_service.py:107, 110-111` |
| **Суть** | `datetime.combine(date, time)` даёт naive datetime. SQLite `datetime('now')` — UTC. |
| **Влияние** | Уведомления могут срабатывать не вовремя, если сервер не в UTC. |
| **Исправление** | Использовать `datetime.now(timezone.utc)` и сохранять timezone-aware значения. |

---

## 🔵 Низкие (10)

| # | Файл | Строки | Ошибка | Исправление |
|---|------|--------|--------|-------------|
| 26 | Все `models/*.py` | — | `datetime.utcnow` deprecated в 3.12+ | `datetime.now(datetime.UTC)` |
| 27 | `app.py:18, 47` | 18, 47 | Неиспользуемые импорты `PicklePersistence`, `Base` | Удалить |
| 28 | `app.py:58, 61-64` | 58, 61-64 | `_shutdown_event` — мёртвый код, никто не await'ит | Удалить или реализовать graceful shutdown |
| 29 | `app.py:63` | 63 | `logger.info()` в signal handler (небезопасно) | Только `_shutdown_event.set()` |
| 30 | `app.py:152` | 152 | `asyncio.get_event_loop()` deprecated | `asyncio.get_running_loop()` |
| 31 | `app.py:82` | 82 | `_on_error` теряет stacktrace | `logger.exception(...)` |
| 32 | `app.py:228` | 228 | Нет проверки `bot_app.updater is None` | `if bot_app.updater: await bot_app.updater.stop()` |
| 33 | `models/audit_log.py` | 18-19 | `slot_id`, `booking_id` без ForeignKey | Добавить `ForeignKey("slot.id")`, `ForeignKey("booking.id")` |
| 34 | `models/slot.py` | 19-28 | Нет relationships `channel` и `created_by_admin` | Добавить `relationship("Channel", back_populates="slots")` и аналогично |
| 35 | `models/channel.py` | 18-19 | Нет relationships вообще | Добавить `owner`, `slots` relationships |

---

## 🔗 Взаимосвязи ошибок

```
#1 (сессия закрыта) ──┬──► все хендлеры бота (6 файлов)
                      └──► #16 (concurrent-сессия) ──► #5 (race condition)
                      
#2 (HMAC) ──► #3 (auth_date) ──► блокировка Web App (api/booking.py)
  
#4 (foreign_keys) ──► все модели без referential integrity

#7 (heartbeat dead) ──► #8 (job_id не сохранён) ──► уведомления не работают
                      └──► #22 (forgotten dead)
                      └──► #19 (waiting dead)

#6 (None в auth) ──► падение бота на callback-запросах

#9 (change не атомарна) ──► #18 (теряет comment)
```

---

## 📋 Приоритет исправлений

| Приоритет | Баги | Обоснование | Статус |
|-----------|------|-------------|--------|
| **P0** | #1, #2, #4 | Без них приложение не работает вообще | ✅ Все исправлены |
| **P1** | #5, #6, #7, #8, #10, #11, #13, #14, #15 | Потеря данных, падение бота, молчаливые сбои | ✅ Все исправлены |
| **P2** | #9, #12 | Потеря брони, AttributeError | ✅ Исправлены |
| **P3** | #16–#25 | Утечки, N+1, deprecated API | ✅ Все исправлены |
| **P4** | #26–#35 | Косметика, мёртвый код, нейминг | 🔵 |

---

*Сгенерировано Claude Code. Актуально на 2026-06-27.*
