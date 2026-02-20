# bot/services/db/settings_repository.py
"""Репозиторий для работы с системными настройками"""

import logging
from typing import Optional

from .base import BaseRepository, db_retry
from bot.config.settings import config

logger = logging.getLogger(__name__)


class SettingsRepository(BaseRepository):

    @db_retry()
    async def get_setting(self, key: str, default: str = None) -> str:
        """
        Получить значение настройки по ключу.
        Если ключ не найден, возвращается default.
        """
        logger.debug(f"Запрос настройки {key} (default={default})")
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT value FROM system_settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            value = row[0] if row else default
            logger.debug(f"Настройка {key} = {value}")
            return value

    @db_retry()
    async def set_setting(self, key: str, value: str, updated_by: int = None) -> bool:
        """
        Установить значение настройки.
        """
        logger.info(f"Установка настройки {key} = {value} (админ {updated_by})")
        async with self.lock:
            await self.conn.execute("""
                INSERT INTO system_settings (key, value, updated_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_by = excluded.updated_by,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value, updated_by))
            await self.conn.commit()
            logger.debug(f"Настройка {key} сохранена")
            return True

    @db_retry()
    async def get_exchange_fee(self) -> float:
        """Получить текущую комиссию обмена."""
        fee = await self.get_setting('exchange_fee', str(config.EXCHANGE_FEE))
        return float(fee)

    @db_retry()
    async def set_exchange_fee(self, fee: float, updated_by: int = None) -> bool:
        """Установить комиссию обмена."""
        return await self.set_setting('exchange_fee', str(fee), updated_by)

    @db_retry()
    async def get_payment_mode(self) -> str:
        """Получить режим оплаты (auto/manual)."""
        mode = await self.get_setting('payment_mode', 'auto')
        return mode

    @db_retry()
    async def set_payment_mode(self, mode: str, updated_by: int = None) -> bool:
        """Установить режим оплаты."""
        if mode not in ('auto', 'manual'):
            logger.warning(f"Попытка установить неверный режим оплаты: {mode}")
            return False
        return await self.set_setting('payment_mode', mode, updated_by)

    @db_retry()
    async def get_bot_version(self) -> str:
        """Получить версию бота."""
        return await self.get_setting('bot_version', config.BOT_VERSION)

    @db_retry()
    async def increment_bot_version(self) -> str:
        """Увеличить версию бота (вызывается при запуске)."""
        current = await self.get_bot_version()
        try:
            num = float(current)
            new_num = num + 0.001
            new_version = f"{new_num:.3f}"
        except ValueError:
            new_version = "0.001"
        await self.set_setting('bot_version', new_version)
        logger.info(f"Версия бота обновлена: {new_version}")
        return new_version

    @db_retry()
    async def get_manual_payment_source(self) -> str:
        """Получить источник реквизитов в ручном режиме (auto/manual)."""
        return await self.get_setting('manual_payment_source', 'manual')

    @db_retry()
    async def set_manual_payment_source(self, source: str, updated_by: int = None) -> bool:
        """Установить источник реквизитов в ручном режиме."""
        if source not in ('auto', 'manual'):
            logger.warning(f"Попытка установить неверный источник: {source}")
            return False
        return await self.set_setting('manual_payment_source', source, updated_by)

    # ========== НОВЫЕ МЕТОДЫ ДЛЯ УРОВНЯ ЛОГИРОВАНИЯ ==========
    @db_retry()
    async def get_log_level(self) -> str:
        """
        Получить текущий уровень логирования из БД.
        По умолчанию 'INFO'.
        """
        level = await self.get_setting('log_level', 'INFO')
        logger.debug(f"Текущий уровень логирования из БД: {level}")
        return level

    @db_retry()
    async def set_log_level(self, level: str, updated_by: int = None) -> bool:
        """
        Установить уровень логирования.
        Допустимые значения: DEBUG, INFO, WARNING, ERROR, CRITICAL.
        """
        level_upper = level.upper()
        allowed = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        if level_upper not in allowed:
            logger.warning(f"Попытка установить недопустимый уровень логирования: {level}")
            return False
        logger.info(f"Изменение уровня логирования на {level_upper} (админ {updated_by})")
        return await self.set_setting('log_level', level_upper, updated_by)