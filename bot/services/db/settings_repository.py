"""Репозиторий для работы с системными настройками"""

from typing import Optional

from .base import BaseRepository, db_retry
from bot.config.settings import config


class SettingsRepository(BaseRepository):

    @db_retry()
    async def get_setting(self, key: str, default: str = None) -> str:
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT value FROM system_settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else default

    @db_retry()
    async def set_setting(self, key: str, value: str, updated_by: int = None) -> bool:
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
            return True

    @db_retry()
    async def get_exchange_fee(self) -> float:
        fee = await self.get_setting('exchange_fee', str(config.EXCHANGE_FEE))
        return float(fee)

    @db_retry()
    async def set_exchange_fee(self, fee: float, updated_by: int = None) -> bool:
        return await self.set_setting('exchange_fee', str(fee), updated_by)

    @db_retry()
    async def get_payment_mode(self) -> str:
        mode = await self.get_setting('payment_mode', 'auto')
        return mode

    @db_retry()
    async def set_payment_mode(self, mode: str, updated_by: int = None) -> bool:
        if mode not in ('auto', 'manual'):
            return False
        return await self.set_setting('payment_mode', mode, updated_by)

    @db_retry()
    async def get_bot_version(self) -> str:
        return await self.get_setting('bot_version', config.BOT_VERSION)

    @db_retry()
    async def increment_bot_version(self) -> str:
        current = await self.get_bot_version()
        try:
            num = float(current)
            new_num = num + 0.001
            new_version = f"{new_num:.3f}"
        except ValueError:
            new_version = "0.001"
        await self.set_setting('bot_version', new_version)
        return new_version

    @db_retry()
    async def get_manual_payment_source(self) -> str:
        return await self.get_setting('manual_payment_source', 'manual')

    @db_retry()
    async def set_manual_payment_source(self, source: str, updated_by: int = None) -> bool:
        if source not in ('auto', 'manual'):
            return False
        return await self.set_setting('manual_payment_source', source, updated_by)