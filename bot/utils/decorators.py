# bot/utils/decorators.py
"""
Декораторы и rate limiter для бота.
Содержит класс RateLimiter для ограничения частоты запросов,
декоратор db_retry для повторных попыток при ошибках базы данных.
"""

from datetime import datetime
from functools import wraps
import asyncio
import logging
import sqlite3

logger = logging.getLogger(__name__)

# Ошибки, которые бессмысленно ретраить — это фатальные/логические сбои.
# IntegrityError = нарушение FK/UNIQUE/NOT NULL.
# ValueError/TypeError/KeyError = ошибки в данных или коде.
_NON_RETRYABLE = (
    sqlite3.IntegrityError,
    ValueError,
    TypeError,
    KeyError,
)


class RateLimiter:
    """
    Ограничитель частоты запросов от пользователя.
    Позволяет задать максимальное количество запросов в заданном временном окне.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        :param max_requests: максимальное количество запросов
        :param window_seconds: размер временного окна в секундах
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # user_id -> список временных меток
        logger.debug(f"RateLimiter инициализирован: max={max_requests}, window={window_seconds}с")

    def is_allowed(self, user_id: int) -> bool:
        """
        Проверяет, может ли пользователь выполнить запрос сейчас.
        Если да, добавляет текущий запрос в историю.
        """
        now = datetime.now()
        if user_id not in self.requests:
            self.requests[user_id] = []
            logger.debug(f"Первый запрос от пользователя {user_id}")

        # Очищаем старые запросы
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if (now - req_time).seconds < self.window_seconds
        ]
        logger.debug(f"Пользователь {user_id}: {len(self.requests[user_id])} запросов в окне")

        if len(self.requests[user_id]) >= self.max_requests:
            logger.warning(f"Пользователь {user_id} превысил лимит запросов")
            return False

        self.requests[user_id].append(now)
        logger.debug(f"Запрос пользователя {user_id} разрешён")
        return True

    def get_remaining(self, user_id: int) -> int:
        """
        Возвращает количество оставшихся разрешённых запросов для пользователя.
        """
        if user_id not in self.requests:
            return self.max_requests
        now = datetime.now()
        recent_requests = [
            req_time for req_time in self.requests[user_id]
            if (now - req_time).seconds < self.window_seconds
        ]
        remaining = max(0, self.max_requests - len(recent_requests))
        logger.debug(f"Пользователь {user_id}: осталось {remaining} запросов")
        return remaining


# Глобальный экземпляр rate limiter для использования в хендлерах
rate_limiter = RateLimiter(max_requests=20, window_seconds=60)


def db_retry(max_retries=3):
    """
    Декоратор для повторных попыток при ошибках базы данных.
    При возникновении исключения делает до max_retries попыток с экспоненциальной задержкой.

    Не ретраит фатальные/логические ошибки (IntegrityError, ValueError и т.п.),
    потому что повторение тех же данных даст ту же ошибку — это лишние
    сайд-эффекты вроде повторных инкрементов счётчиков.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(self, *args, **kwargs)
                except _NON_RETRYABLE as e:
                    logger.error(
                        "Фатальная ошибка в %s (без повтора): %s: %s",
                        func.__name__, type(e).__name__, e,
                    )
                    raise
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(
                            "Все %s попыток не удались в %s: %s",
                            max_retries, func.__name__, e, exc_info=True,
                        )
                        raise
                    wait = 0.1 * (attempt + 1)
                    logger.warning(
                        "Ошибка в %s (попытка %s/%s): %s. Повтор через %.2fс",
                        func.__name__, attempt + 1, max_retries, e, wait,
                    )
                    await asyncio.sleep(wait)
            return None
        return wrapper
    return decorator