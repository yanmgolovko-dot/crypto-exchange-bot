"""Базовый класс для всех репозиториев"""

import asyncio
from functools import wraps
import logging
from typing import Optional
from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


def db_retry(max_retries=3):
    """Декоратор для повторных попыток при ошибках БД"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))
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