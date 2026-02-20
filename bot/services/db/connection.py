"""Управление подключением к базе данных"""

import aiosqlite
import os
import asyncio
import logging
from typing import Optional

from bot.config.settings import config

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Класс для управления подключением к SQLite"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Создание соединения (вызывается при старте)"""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    async def close(self):
        """Закрытие соединения"""
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock