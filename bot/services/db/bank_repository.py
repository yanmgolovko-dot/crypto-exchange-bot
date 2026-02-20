# bot/services/db/bank_repository.py
"""Репозиторий для работы с банковскими реквизитами."""

import logging
from typing import Optional, List
from dataclasses import dataclass

from .base import BaseRepository, db_retry
import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class BankDetails:
    id: int
    card_number: str
    bank_name: str
    holder_name: str
    is_active: bool
    is_default: bool
    daily_limit: float
    daily_used: float
    last_reset_date: str
    created_at: str
    added_by: Optional[int]


class BankRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей bank_details.
    Предоставляет методы для добавления, получения, обновления и удаления банковских карт.
    """

    @db_retry()
    async def add_bank_details(self, card_number: str, bank_name: str,
                                holder_name: str, daily_limit: float = 1000000,
                                added_by: int = None) -> int:
        """
        Добавляет новые банковские реквизиты.
        Если это первая запись, автоматически делает её is_default = True.
        """
        logger.info(f"Добавление банковских реквизитов: банк {bank_name}, карта {card_number[:4]}...")
        async with self.lock:
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bank_details")
            count = (await cursor.fetchone())[0]
            is_default = count == 0
            logger.debug(f"Это первая запись? {is_default}")

            cursor = await self.conn.execute("""
                INSERT INTO bank_details 
                (card_number, bank_name, holder_name, daily_limit, is_default, added_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (card_number, bank_name, holder_name, daily_limit, is_default, added_by))
            await self.conn.commit()
            new_id = cursor.lastrowid
            logger.info(f"Банковские реквизиты добавлены, ID: {new_id}")
            return new_id

    @db_retry()
    async def get_bank_details(self, details_id: int = None) -> Optional[BankDetails]:
        """
        Получает банковские реквизиты по ID или возвращает активные по умолчанию (is_default=1).
        """
        logger.debug(f"Запрос банковских реквизитов, details_id={details_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            if details_id:
                cursor = await self.conn.execute(
                    "SELECT * FROM bank_details WHERE id = ?", (details_id,)
                )
            else:
                cursor = await self.conn.execute(
                    "SELECT * FROM bank_details WHERE is_default = 1 AND is_active = 1"
                )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Банковские реквизиты найдены: ID {row['id']}")
                return BankDetails(**dict(row))
            logger.debug("Банковские реквизиты не найдены")
            return None

    @db_retry()
    async def get_all_bank_details(self) -> List[BankDetails]:
        """Возвращает список всех банковских реквизитов."""
        logger.debug("Запрос всех банковских реквизитов")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM bank_details ORDER BY is_default DESC, created_at DESC"
            )
            rows = await cursor.fetchall()
            details = [BankDetails(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(details)} записей")
            return details

    @db_retry()
    async def update_bank_details(self, details_id: int, **kwargs) -> bool:
        """
        Обновляет поля банковских реквизитов.
        Допустимые поля: card_number, bank_name, holder_name, is_active, is_default, daily_limit.
        """
        allowed_fields = ['card_number', 'bank_name', 'holder_name',
                          'is_active', 'is_default', 'daily_limit']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            logger.warning(f"Нет допустимых полей для обновления ID {details_id}")
            return False

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [details_id]
        logger.info(f"Обновление банковских реквизитов ID {details_id}: {updates}")
        async with self.lock:
            await self.conn.execute(
                f"UPDATE bank_details SET {set_clause} WHERE id = ?",
                values
            )
            await self.conn.commit()
            logger.info(f"Банковские реквизиты ID {details_id} обновлены")
            return True

    @db_retry()
    async def delete_bank_details(self, details_id: int) -> bool:
        """Удаляет банковские реквизиты по ID."""
        logger.info(f"Удаление банковских реквизитов ID {details_id}")
        async with self.lock:
            await self.conn.execute("DELETE FROM bank_details WHERE id = ?", (details_id,))
            await self.conn.commit()
            logger.info(f"Банковские реквизиты ID {details_id} удалены")
            return True

    @db_retry()
    async def set_default_bank_details(self, details_id: int) -> bool:
        """Устанавливает указанные реквизиты как используемые по умолчанию."""
        logger.info(f"Установка банковских реквизитов ID {details_id} по умолчанию")
        async with self.lock:
            # Сначала сбрасываем is_default у всех
            await self.conn.execute("UPDATE bank_details SET is_default = 0")
            # Устанавливаем is_default для выбранной записи
            await self.conn.execute(
                "UPDATE bank_details SET is_default = 1 WHERE id = ?",
                (details_id,)
            )
            await self.conn.commit()
            logger.info(f"Банковские реквизиты ID {details_id} теперь по умолчанию")
            return True