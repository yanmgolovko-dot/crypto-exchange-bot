"""Базовый класс для всех репозиториев"""

import asyncio
from functools import wraps
import logging
import sqlite3
from typing import Optional
from .connection import DatabaseConnection

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


def db_retry(max_retries=3):
    """Декоратор для повторных попыток при ошибках БД.

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


class BaseRepository:
    """Базовый репозиторий, содержит общие методы и доступ к соединению"""

    def __init__(self, connection: DatabaseConnection):
        self._connection = connection

    @property
    def conn(self):
        return self._connection.conn

    @property
    def lock(self):
        return self._connection.lock