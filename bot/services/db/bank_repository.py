"""Репозиторий для работы с банковскими реквизитами"""

from typing import Optional, List
from dataclasses import dataclass

from .base import BaseRepository, db_retry
import aiosqlite


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

    @db_retry()
    async def add_bank_details(self, card_number: str, bank_name: str, 
                               holder_name: str, daily_limit: float = 1000000,
                               added_by: int = None) -> int:
        async with self.lock:
            cursor = await self.conn.execute("SELECT COUNT(*) FROM bank_details")
            count = (await cursor.fetchone())[0]
            is_default = count == 0

            cursor = await self.conn.execute("""
                INSERT INTO bank_details 
                (card_number, bank_name, holder_name, daily_limit, is_default, added_by)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (card_number, bank_name, holder_name, daily_limit, is_default, added_by))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_bank_details(self, details_id: int = None) -> Optional[BankDetails]:
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
                return BankDetails(**dict(row))
            return None

    @db_retry()
    async def get_all_bank_details(self) -> List[BankDetails]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM bank_details ORDER BY is_default DESC, created_at DESC"
            )
            rows = await cursor.fetchall()
            return [BankDetails(**dict(row)) for row in rows]

    @db_retry()
    async def update_bank_details(self, details_id: int, **kwargs) -> bool:
        allowed_fields = ['card_number', 'bank_name', 'holder_name', 
                          'is_active', 'is_default', 'daily_limit']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [details_id]
        async with self.lock:
            await self.conn.execute(
                f"UPDATE bank_details SET {set_clause} WHERE id = ?",
                values
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def delete_bank_details(self, details_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("DELETE FROM bank_details WHERE id = ?", (details_id,))
            await self.conn.commit()
            return True

    @db_retry()
    async def set_default_bank_details(self, details_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("UPDATE bank_details SET is_default = 0")
            await self.conn.execute(
                "UPDATE bank_details SET is_default = 1 WHERE id = ?",
                (details_id,)
            )
            await self.conn.commit()
            return True