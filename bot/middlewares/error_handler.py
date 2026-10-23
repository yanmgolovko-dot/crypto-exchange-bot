# bot/middlewares/error_handler.py
"""
Глобальный обработчик ошибок aiogram.
Регистрируется через dp.errors.register(global_error_handler).
Отправляет админам sanitized-traceback с дедупликацией по сигнатуре ошибки.
"""

import html
import logging
import re
import traceback
from datetime import datetime, timedelta
from typing import Dict

from aiogram import Bot
from aiogram.types import ErrorEvent

from bot.config.settings import config

logger = logging.getLogger(__name__)

# Маскировка токена бота в URL Telegram API (/bot123:AA.../method)
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}")
# Маскировка чувствительных значений в тексте исключений
_SECRETS_RE = re.compile(
    r"(ENCRYPTION_KEY|BOT_TOKEN|BLOCKCYPHER_TOKEN|LTC_RPC_URL)=([^\s&\"']+)"
)


def _sanitize(text: str) -> str:
    """
    Убирает секреты и экранирует спецсимволы HTML.
    Результат безопасен для вставки в <pre>...</pre> и другие HTML-теги.
    """
    if not text:
        return ""
    text = _TOKEN_RE.sub("bot<TOKEN>", text)
    text = _SECRETS_RE.sub(lambda m: f"{m.group(1)}=<HIDDEN>", text)
    text = html.escape(text, quote=False)
    return text


class ErrorNotifier:
    """Формирует сообщение об ошибке и рассылает админам с дедупликацией."""

    def __init__(self, cooldown_seconds: int = 60, max_len: int = 3500):
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.max_len = max_len
        self._last_sent: Dict[str, datetime] = {}
        self._admin_ids = list(config.ADMIN_IDS or [])

    def _signature(self, exc: BaseException) -> str:
        tb = exc.__traceback__
        last_frame = ""
        while tb is not None:
            last_frame = f"{tb.tb_frame.f_code.co_filename}:{tb.tb_lineno}"
            tb = tb.tb_next
        return f"{type(exc).__name__}:{last_frame}"

    def _should_send(self, exc: BaseException) -> bool:
        sig = self._signature(exc)
        now = datetime.now()
        last = self._last_sent.get(sig)
        if last is not None and (now - last) < self.cooldown:
            return False
        self._last_sent[sig] = now
        if len(self._last_sent) > 500:
            cutoff = now - self.cooldown
            self._last_sent = {k: v for k, v in self._last_sent.items() if v >= cutoff}
        return True

    def build_message(self, event: ErrorEvent) -> str:
        exc = event.exception
        tb_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        tb_text = _sanitize(tb_text)

        update = event.update
        user_id = None
        username = None
        action = None

        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
            username = update.message.from_user.username
            text = update.message.text or "<non-text>"
            action = f"msg: {text[:80]}"
        elif update.callback_query and update.callback_query.from_user:
            cq = update.callback_query
            user_id = cq.from_user.id
            username = cq.from_user.username
            action = f"cb: {(cq.data or '<none>')[:80]}"

        parts = [
            "🚨 <b>Ошибка в боте</b>",
            f"<b>Тип:</b> <code>{html.escape(type(exc).__name__)}</code>",
            f"<b>Сообщение:</b> {_sanitize(str(exc))[:500]}",
        ]
        if user_id:
            tail = f" (@{html.escape(username)})" if username else ""
            parts.append(f"<b>User:</b> <code>{user_id}</code>{tail}")
        if action:
            parts.append(f"<b>Действие:</b> <code>{_sanitize(action)}</code>")
        parts.append(f"<b>Update:</b> <code>{update.update_id}</code>")
        parts.append("")
        parts.append(f"<b>Traceback:</b>\n<pre>{tb_text}</pre>")

        msg = "\n".join(parts)
        if len(msg) > self.max_len:
            msg = msg[: self.max_len] + "\n... (обрезано)"
        return msg

    async def notify(self, bot: Bot, event: ErrorEvent) -> None:
        if not self._admin_ids:
            return
        if not self._should_send(event.exception):
            logger.debug("Ошибка задедуплицирована, уведомление пропущено")
            return
        msg = self.build_message(event)
        for admin_id in self._admin_ids:
            try:
                await bot.send_message(admin_id, msg, parse_mode="HTML")
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Не удалось отправить error-уведомление админу %s: %s",
                    admin_id, exc,
                )


_notifier = ErrorNotifier()


async def global_error_handler(event: ErrorEvent, bot: Bot) -> None:
    """Глобальный обработчик ошибок. Регистрируется через dp.errors.register."""
    logger.error(
        "Необработанное исключение (update_id=%s): %s: %s",
        event.update.update_id,
        type(event.exception).__name__,
        event.exception,
        exc_info=event.exception,
    )
    await _notifier.notify(bot, event)