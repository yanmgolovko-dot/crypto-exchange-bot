"""Репозиторий для работы с промокодами"""

from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import BaseRepository, db_retry
import aiosqlite


@dataclass
class PromoCode:
    id: int
    code: str
    discount_percent: float
    max_uses: int
    used_count: int
    valid_from: str
    valid_to: str
    is_active: bool
    created_by: int
    description: Optional[str]


class PromoRepository(BaseRepository):

    @db_retry()
    async def create_promo_code(self, code: str, discount_percent: float,
                                 max_uses: int = 100, valid_days: int = 30,
                                 created_by: int = None, description: str = None) -> int:
        async with self.lock:
            valid_to = (datetime.now() + timedelta(days=valid_days)).isoformat()
            cursor = await self.conn.execute("""
                INSERT INTO promo_codes 
                (code, discount_percent, max_uses, valid_to, created_by, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (code.upper(), discount_percent, max_uses, valid_to, created_by, description))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_promo_code(self, code: str) -> Optional[PromoCode]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM promo_codes WHERE code = ?", (code.upper(),)
            )
            row = await cursor.fetchone()
            if row:
                return PromoCode(**dict(row))
            return None

    @db_retry()
    async def validate_promo_code(self, code: str, user_id: int) -> Tuple[bool, str, float]:
        promo = await self.get_promo_code(code)
        if not promo:
            return False, "Промокод не найден", 0
        if not promo.is_active:
            return False, "Промокод деактивирован", 0
        if promo.used_count >= promo.max_uses:
            return False, "Лимит использований исчерпан", 0
        if datetime.now().isoformat() > promo.valid_to:
            return False, "Срок действия промокода истек", 0

        used_ids = await self.get_user_used_promo_ids(user_id)
        if promo.id in used_ids:
            return False, "Вы уже использовали этот промокод", 0

        return True, "Промокод применен", promo.discount_percent

    @db_retry()
    async def use_promo_code(self, promo_id: int, user_id: int, order_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("""
                INSERT INTO promo_usage (promo_id, user_id, order_id)
                VALUES (?, ?, ?)
            """, (promo_id, user_id, order_id))
            await self.conn.execute("""
                UPDATE promo_codes SET used_count = used_count + 1 WHERE id = ?
            """, (promo_id,))
            await self.conn.commit()
            return True

    @db_retry()
    async def get_all_promo_codes(self) -> List[PromoCode]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM promo_codes ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [PromoCode(**dict(row)) for row in rows]

    @db_retry()
    async def toggle_promo_code(self, promo_id: int, is_active: bool) -> bool:
        async with self.lock:
            await self.conn.execute(
                "UPDATE promo_codes SET is_active = ? WHERE id = ?",
                (is_active, promo_id)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def get_user_used_promo_ids(self, user_id: int) -> List[int]:
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT promo_id FROM promo_usage WHERE user_id = ?",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]