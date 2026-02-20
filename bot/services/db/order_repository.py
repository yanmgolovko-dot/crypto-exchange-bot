"""Репозиторий для работы с заявками"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .base import BaseRepository, db_retry
import aiosqlite


@dataclass
class Order:
    id: int
    user_id: int
    username: Optional[str]
    crypto_type: str
    amount_rub: float
    amount_crypto: float
    rate: float
    fee_percent: float
    status: str
    bank_receipt: Optional[str]
    crypto_address: str
    created_at: str
    paid_at: Optional[str]
    completed_at: Optional[str]
    admin_comment: Optional[str]
    promo_code: Optional[str]
    discount_percent: float
    admin_checked_by: Optional[int]
    admin_checked_at: Optional[str]
    manual_payment_details: Optional[str] = None
    tx_hash: Optional[str] = None
    reminder_count: int = 0
    last_reminder_at: Optional[str] = None


class OrderRepository(BaseRepository):

    @db_retry()
    async def create_order(self, user_id: int, username: str, crypto_type: str,
                          amount_rub: float, amount_crypto: float, rate: float,
                          fee_percent: float, crypto_address: str,
                          promo_code: str = None, discount_percent: float = 0) -> int:
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO exchange_orders 
                (user_id, username, crypto_type, amount_rub, amount_crypto, rate, 
                 fee_percent, crypto_address, status, promo_code, discount_percent, reminder_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0)
            """, (user_id, username, crypto_type, amount_rub, amount_crypto, 
                  rate, fee_percent, crypto_address, promo_code, discount_percent))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_order(self, order_id: int) -> Optional[Order]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM exchange_orders WHERE id = ?", (order_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Order(**dict(row))
            return None

    @db_retry()
    async def update_order_status(self, order_id: int, status: str, 
                                   admin_comment: str = None,
                                   admin_id: int = None) -> bool:
        async with self.lock:
            if status == 'paid':
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, paid_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, admin_comment, order_id))
            elif status == 'completed':
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, completed_at = CURRENT_TIMESTAMP,
                        admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, admin_comment, admin_id, order_id))
            else:
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?
                    WHERE id = ?
                """, (status, admin_comment, order_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def update_order_tx_hash(self, order_id: int, tx_hash: str, admin_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders 
                SET tx_hash = ?, admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (tx_hash, admin_id, order_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def add_bank_receipt(self, order_id: int, receipt_path: str) -> bool:
        async with self.lock:
            await self.conn.execute(
                "UPDATE exchange_orders SET bank_receipt = ? WHERE id = ?",
                (receipt_path, order_id)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def get_user_orders(self, user_id: int, limit: int = 10) -> List[Order]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            rows = await cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

    @db_retry()
    async def get_pending_orders(self) -> List[Order]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                WHERE status IN ('pending', 'paid') 
                ORDER BY created_at DESC
            """)
            rows = await cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

    @db_retry()
    async def get_all_orders(self, limit: int = 50, offset: int = 0) -> List[Order]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = await cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

    @db_retry()
    async def set_order_manual_payment_details(self, order_id: int, details: str) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders 
                SET manual_payment_details = ? 
                WHERE id = ?
            """, (details, order_id))
            await self.conn.commit()
            return True

    # ==================== МЕТОДЫ ДЛЯ НАПОМИНАНИЙ ====================

    @db_retry()
    async def get_pending_orders_for_reminder(self, minutes: int = 5, max_reminders: int = 3) -> List[Order]:
        """Возвращает заявки со статусом 'pending', созданные более minutes минут назад,
        у которых количество напоминаний меньше max_reminders."""
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders
                WHERE status = 'pending'
                AND (julianday('now') - julianday(created_at)) * 24 * 60 >= ?
                AND reminder_count < ?
            """, (minutes, max_reminders))
            rows = await cursor.fetchall()
            return [Order(**dict(row)) for row in rows]

    @db_retry()
    async def increment_reminder_count(self, order_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders
                SET reminder_count = reminder_count + 1,
                    last_reminder_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (order_id,))
            await self.conn.commit()
            return True