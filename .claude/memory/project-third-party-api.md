---
name: third-party-api
description: Архитектура внешнего API — REST, вебхуки, iCal, календари
metadata:
  type: project
---

# Внешнее API для сторонних сервисов

**Решение:** Добавить возможность принимать запросы от сторонних API после завершения всех 5 основных милстоунов.

## Состав

1. **REST API** (`/api/v1/*`) — полный CRUD для слотов, броней, каналов
2. **Исходящие вебхуки** — POST на URL при событиях (booking.created и т.д.) с HMAC-подписью и retry
3. **iCal импорт/экспорт** — `GET /api/v1/schedule.ics` / `POST /api/v1/schedule.ics`
4. **Календарная интеграция** — фундамент для Google Calendar / Outlook

## Аутентификация (отложено)

Основной кандидат: API Key (`X-API-Key: sk_live_xxx`, SHA-256 в БД).  
Опционально: HMAC-режим для повышенной безопасности (подпись тела запроса).  
JWT — если появятся пользовательские логины.

## Новые модели

- **ApiClient** — ключи доступа с permissions (JSON), rate_limit, expires_at
- **Webhook** — URL + events (JSON) + secret + retry config
- **WebhookDeliveryLog** — журнал доставки с retry scheduling
- **Integration** — настройки календарной интеграции (type, credentials encrypted, sync_direction)

## Rate Limiting

In-memory sliding window (asyncio.Lock + deque). Без Redis.  
Дефолт: 60 req/min на ключ.

## Интеграция с милстоунами

Внешнее API накладывается поверх каждого milestone после его завершения:
- M1 → модели + rate limiter + зависимости (httpx, icalendar, cryptography)
- M2 → Telegram команды управления API/вебхуками + scaffold роутера
- M3 → endpoints слотов/броней + webhook dispatch
- M4 → endpoints отмены + retry-механизм
- M5 → iCal + интеграции + docs

**Подробный план:** [[spicy-growing-hejlsberg]]

**Why:** Расширяет систему за пределы Telegram, позволяет интеграцию с CRM, календарями, внешними сервисами бронирования.
**How to apply:** Реализовывать порциями после каждого milestone, начиная с M1 (модели + rate limiter).
