"""Репозиторий для работы с финансовыми записями и статистикой"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from .base import BaseRepository, db_retry
import aiosqlite


@dataclass
class FinancialRecord:
    id: int
    record_type: str
    category: str
    amount: float
    currency: str
    description: str
    order_id: Optional[int]
    created_at: str
    created_by: Optional[int]


class FinanceRepository(BaseRepository):

    @db_retry()
    async def add_financial_record(self, record_type: str, category: str,
                                    amount: float, currency: str = 'RUB',
                                    description: str = None, order_id: int = None,
                                    created_by: int = None) -> int:
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO financial_records 
                (record_type, category, amount, currency, description, order_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (record_type, category, amount, currency, description, order_id, created_by))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_financial_stats(self, days: int = 30) -> Dict[str, Any]:
        async with self.lock:
            date_from = (datetime.now() - timedelta(days=days)).isoformat()

            cursor = await self.conn.execute("""
                SELECT SUM(amount) FROM financial_records 
                WHERE record_type = 'income' AND category = 'exchange_fee'
                AND created_at >= ?
            """, (date_from,))
            revenue = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute("""
                SELECT SUM(amount) FROM financial_records 
                WHERE record_type = 'expense'
                AND created_at >= ?
            """, (date_from,))
            expenses = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute("""
                SELECT SUM(amount) FROM financial_records 
                WHERE record_type = 'profit'
                AND created_at >= ?
            """, (date_from,))
            profit = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute("""
                SELECT SUM(amount_rub) FROM exchange_orders 
                WHERE status = 'completed' AND completed_at >= ?
            """, (date_from,))
            trading_volume = (await cursor.fetchone())[0] or 0

            return {
                'revenue': revenue,
                'expenses': expenses,
                'profit': profit,
                'trading_volume': trading_volume,
                'period_days': days
            }

    @db_retry()
    async def get_recent_financial_records(self, limit: int = 20) -> List[FinancialRecord]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM financial_records 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            return [FinancialRecord(**dict(row)) for row in rows]

    @db_retry()
    async def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        async with self.lock:
            cursor = await self.conn.execute("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as orders_count,
                    SUM(amount_rub) as volume,
                    SUM(amount_rub * fee_percent / 100) as fee_earned
                FROM exchange_orders 
                WHERE status = 'completed' 
                AND created_at >= DATE('now', '-{} days')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """.format(days))
            rows = await cursor.fetchall()
            return [
                {
                    'date': row[0],
                    'orders_count': row[1],
                    'volume': row[2] or 0,
                    'fee_earned': row[3] or 0
                }
                for row in rows
            ]

    @db_retry()
    async def get_dashboard_stats(self) -> Dict[str, Any]:
        async with self.lock:
            stats = {}

            cursor = await self.conn.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute("""
                SELECT COUNT(*) FROM users 
                WHERE created_at >= DATETIME('now', '-1 day')
            """)
            stats['new_users_24h'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute("""
                SELECT COUNT(*) FROM users 
                WHERE last_activity >= DATETIME('now', '-1 day')
            """)
            stats['active_users_24h'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
            stats['banned_users'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute("SELECT COUNT(*) FROM exchange_orders")
            stats['total_orders'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE status = 'pending'"
            )
            stats['pending_orders'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE status = 'paid'"
            )
            stats['paid_orders'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE status = 'completed'"
            )
            stats['completed_orders'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute("""
                SELECT SUM(amount_rub) FROM exchange_orders WHERE status = 'completed'
            """)
            stats['total_volume'] = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute("""
                SELECT SUM(amount_rub) FROM exchange_orders 
                WHERE status = 'completed' AND completed_at >= DATETIME('now', '-1 day')
            """)
            stats['volume_24h'] = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute("""
                SELECT SUM(amount_rub * fee_percent / 100) FROM exchange_orders 
                WHERE status = 'completed'
            """)
            stats['total_fees'] = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM promo_codes WHERE is_active = 1"
            )
            stats['active_promos'] = (await cursor.fetchone())[0]

            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM bank_details WHERE is_active = 1"
            )
            stats['active_bank_details'] = (await cursor.fetchone())[0]

            return stats