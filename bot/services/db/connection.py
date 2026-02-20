# bot/services/db/connection.py
"""Управление подключением к базе данных."""

import aiosqlite
import os
import asyncio
import logging
from typing import Optional

from bot.config.settings import config

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Класс для управления подключением к SQLite.
    Обеспечивает единое соединение с БД и потокобезопасность через asyncio.Lock.
    """

    def __init__(self, db_path: str = None):
        """
        :param db_path: путь к файлу базы данных (если None, берётся из config.DB_PATH)
        """
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        logger.info(f"Инициализация DatabaseConnection, путь БД: {self.db_path}")
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Создание соединения с БД (вызывается при старте)."""
        logger.info("Попытка подключения к базе данных")
        if self._conn is None:
            try:
                self._conn = await aiosqlite.connect(self.db_path)
                await self._conn.execute("PRAGMA foreign_keys = ON")
                logger.info("Подключение к базе данных успешно установлено")
            except Exception as e:
                logger.error(f"Ошибка подключения к базе данных: {e}", exc_info=True)
                raise
        else:
            logger.debug("Соединение уже существует")
        return self._conn

    async def close(self):
        """Закрытие соединения."""
        logger.info("Закрытие соединения с базой данных")
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Соединение закрыто")
        else:
            logger.debug("Соединение уже было закрыто или не открывалось")

    @property
    def conn(self) -> aiosqlite.Connection:
        """Возвращает объект соединения, проверяя, что оно существует."""
        if self._conn is None:
            logger.error("Попытка получить соединение, но оно не открыто")
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    @property
    def lock(self) -> asyncio.Lock:
        """Возвращает блокировку для синхронизации доступа к БД."""
        return self._lock