"""Developer Telegram command handlers (/health, /logs, /version)."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from tbot_sheduler.api.health import EMOJI_MAP, HealthStatus, run_healthcheck
from tbot_sheduler.core.auth import check_admin, check_role
from tbot_sheduler.core.config import BOT_VERSION

logger = logging.getLogger(__name__)


def format_uptime(seconds: int) -> str:
    """Format uptime seconds into human-readable string."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)


def format_health_message(health_data: dict) -> str:
    """Format healthcheck result for Telegram message."""
    overall = health_data["status"]
    overall_emoji = {
        "ok": "✅", "degraded": "⚠️", "down": "❌",
    }.get(overall, "❓")

    name_labels = {
        "database": "🗄️ БД",
        "bot": "🤖 Бот",
        "telegram_api": "📡 Telegram API",
        "disk": "💾 Диск",
        "memory": "🧠 Память",
        "scheduler": "⏰ Планировщик",
    }

    lines = [
        f"<b>🏥 Healthcheck</b>\n",
        f"<b>Статус:</b> {overall_emoji} {overall.upper()}",
        f"<b>Версия:</b> {health_data.get('version', BOT_VERSION)}",
        f"<b>Uptime:</b> {format_uptime(health_data.get('uptime_seconds', 0))}",
        f"<b>Время ответа:</b> {health_data.get('response_time_ms', 0)} мс\n",
        "<b>Проверки:</b>",
    ]

    for name, check in health_data.get("checks", {}).items():
        emoji = EMOJI_MAP.get(check.get("status", HealthStatus.DOWN), "❓")
        label = name_labels.get(name, name)
        lines.append(f"{emoji} <b>{label}</b>: {check.get('detail', '—')}")

    return "\n".join(lines)


@check_role("developer", "owner")
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /health — send formatted healthcheck."""
    user_id = update.effective_user.id

    # Run healthcheck
    health_data = await run_healthcheck(context.application)
    message = format_health_message(health_data)

    # Send to PM if command is from group/channel
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📋 Результат отправлен в личные сообщения."
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(message, parse_mode="HTML")


@check_role("developer", "owner")
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /logs <lines> — show last N lines of log."""
    from tbot_sheduler.core.config import LOG_DIR

    # Parse line count
    lines_count = 20
    if context.args:
        try:
            lines_count = min(max(1, int(context.args[0])), 100)
        except ValueError:
            await update.message.reply_text(
                "ℹ️ Использование: /logs <число строк> (макс 100)"
            )
            return

    log_file = LOG_DIR / "app.log"
    if not log_file.exists():
        await update.message.reply_text("📋 Лог-файл не найден.")
        return

    try:
        # Read last N lines
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        last_lines = all_lines[-lines_count:]

        text = f"📋 <b>Последние {len(last_lines)} строк лога:</b>\n<pre>"
        text += "".join(last_lines)
        text += "</pre>"

        # Telegram has 4096 char limit for messages
        if len(text) > 4000:
            text = text[:3990] + "\n...</pre>"

        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error("Error reading log file: %s", e)
        await update.message.reply_text("⚠️ Ошибка при чтении лог-файла.")


@check_role("developer", "owner")
async def version_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /version — show bot version and uptime."""
    started_at = getattr(context.application, "_start_time", time.monotonic())
    uptime = int(time.monotonic() - started_at)
    start_time_str = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC",
        time.gmtime(time.time() - uptime),
    )

    await update.message.reply_text(
        f"<b>ℹ️ Информация о боте</b>\n\n"
        f"<b>Версия:</b> {BOT_VERSION}\n"
        f"<b>Uptime:</b> {format_uptime(uptime)}\n"
        f"<b>Запущен:</b> {start_time_str}\n"
        f"<b>Команды:</b> Доступны /health, /logs",
        parse_mode="HTML",
    )
