# bot/middlewares/rate_limit.py
"""
Rate limiting middleware для защиты от спама.

Использует существующий RateLimiter из bot.utils.decorators.
Администраторы (config.ADMIN_IDS) освобождены от ограничений.
При превышении лимита запрос не передаётся дальше — пользователь
получает короткое предупреждение не чаще раза в WARN_COOLDOWN секунд.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config.settings import config
from bot.utils.decorators import RateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Ограничивает частоту сообщений и callback-запросов от одного пользователя."""

    def __init__(
        self,
        max_requests: int = 20,
        window_seconds: int = 60,
        warn_cooldown_seconds: int = 30,
    ):
        super().__init__()
        self.limiter = RateLimiter(
            max_requests=max_requests, window_seconds=window_seconds
        )
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.warn_cooldown = timedelta(seconds=warn_cooldown_seconds)
        self._last_warn: Dict[int, datetime] = {}
        self._admin_ids = set(config.ADMIN_IDS or [])
        logger.info(
            "RateLimitMiddleware инициализирован: max=%s/%ss, админы=%s",
            max_requests, window_seconds, len(self._admin_ids),
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None:
            return await handler(event, data)

        # Админов не ограничиваем
        if user.id in self._admin_ids:
            return await handler(event, data)

        if not self.limiter.is_allowed(user.id):
            now = datetime.now()
            last = self._last_warn.get(user.id)
            if last is None or (now - last) >= self.warn_cooldown:
                self._last_warn[user.id] = now
                try:
                    if isinstance(event, CallbackQuery):
                        await event.answer(
                            "⏳ Слишком много запросов. Подождите немного.",
                            show_alert=False,
                        )
                    elif isinstance(event, Message):
                        await event.answer(
                            "⏳ Слишком много запросов. Подождите немного."
                        )
                except Exception as exc:  # noqa: BLE001 — не должно ронять middleware
                    logger.debug("Не удалось отправить предупреждение %s: %s", user.id, exc)

            logger.warning(
                "Rate limit превышен: user_id=%s, remaining=%s/%s",
                user.id,
                self.limiter.get_remaining(user.id),
                self.max_requests,
            )
            return None

        return await handler(event, data)