# bot/services/db/user_repository.py
"""Репозиторий для работы с пользователями."""

import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from .base import BaseRepository, db_retry
import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class User:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: str
    last_activity: Optional[str]
    total_exchanges: int
    total_volume: float
    is_banned: bool
    ban_reason: Optional[str]
    ban_date: Optional[str]
    banned_by: Optional[int]
    referral_code: Optional[str]
    referred_by: Optional[int]
    bonus_balance: float
    language: str
    notifications_enabled: bool
    fake_total_exchanges: int = 0


class UserRepository(BaseRepository):

    @db_retry()
    async def add_or_update_user(self, user_id: int, username: str = None,
                                  first_name: str = None, last_name: str = None) -> bool:
        logger.info(f"[{user_id}] Добавление/обновление пользователя")
        async with self.lock:
            referral_code = f"REF{user_id}"
            await self.conn.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, referral_code, last_activity)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    last_activity = CURRENT_TIMESTAMP
            """, (user_id, username, first_name, last_name, referral_code))
            await self.conn.commit()
            return True

    @db_retry()
    async def set_referrer(self, user_id: int, referrer_id: int) -> bool:
        logger.info(f"[{user_id}] Установка реферера {referrer_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL
            """, (referrer_id, user_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def get_user(self, user_id: int) -> Optional[User]:
        logger.debug(f"Запрос пользователя {user_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return User(**dict(row))
            return None

    @db_retry()
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Поиск пользователя по username (без @, регистронезависимо)."""
        clean = (username or "").lstrip("@").lower()
        if not clean:
            return None
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = ?", (clean,)
            )
            row = await cursor.fetchone()
            if row:
                return User(**dict(row))
            return None

    @db_retry()
    async def get_user_by_referral_code(self, code: str) -> Optional[User]:
        """Поиск пользователя по реферальному коду (точное совпадение)."""
        if not code:
            return None
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM users WHERE referral_code = ?", (code,)
            )
            row = await cursor.fetchone()
            if row:
                return User(**dict(row))
            return None

    @db_retry()
    async def set_user_referral_code(self, user_id: int, code: str) -> bool:
        """Устанавливает реферальный код пользователя."""
        logger.info(f"Установка реф. кода '{code}' для пользователя {user_id}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET referral_code = ? WHERE user_id = ?",
                (code, user_id),
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def get_all_users(self) -> List[User]:
        logger.debug("Запрос всех пользователей")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("SELECT * FROM users ORDER BY user_id")
            rows = await cursor.fetchall()
            return [User(**dict(row)) for row in rows]

    @db_retry()
    async def ban_user(self, user_id: int, reason: str, banned_by: int) -> bool:
        logger.info(f"Бан пользователя {user_id} администратором {banned_by}, причина: {reason}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE users SET 
                    is_banned = 1, 
                    ban_reason = ?, 
                    ban_date = CURRENT_TIMESTAMP,
                    banned_by = ?
                WHERE user_id = ?
            """, (reason, banned_by, user_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def unban_user(self, user_id: int) -> bool:
        logger.info(f"Снятие бана с пользователя {user_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE users SET 
                    is_banned = 0, 
                    ban_reason = NULL, 
                    ban_date = NULL,
                    banned_by = NULL
                WHERE user_id = ?
            """, (user_id,))
            await self.conn.commit()
            return True

    @db_retry()
    async def is_user_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        user = await self.get_user(user_id)
        if user and user.is_banned:
            return True, user.ban_reason
        return False, None

    @db_retry()
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        logger.debug(f"Запрос статистики для пользователя {user_id}")
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE user_id = ?", (user_id,)
            )
            total_orders = (await cursor.fetchone())[0]

            cursor = await self.conn.execute(
                "SELECT SUM(amount_rub) FROM exchange_orders WHERE user_id = ? AND status = 'completed'",
                (user_id,)
            )
            total_volume = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute(
                "SELECT SUM(amount_rub * discount_percent / 100) FROM exchange_orders WHERE user_id = ? AND status = 'completed'",
                (user_id,)
            )
            total_saved = (await cursor.fetchone())[0] or 0

            cursor = await self.conn.execute(
                "SELECT fake_total_exchanges FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            fake_total = row[0] if row else 0

            return {
                'total_orders': total_orders,
                'total_volume': total_volume,
                'total_saved': total_saved,
                'fake_total_exchanges': fake_total,
            }

    @db_retry()
    async def set_user_notifications(self, user_id: int, enabled: bool) -> bool:
        logger.info(f"[{user_id}] Установка уведомлений: {enabled}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
                (enabled, user_id)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def add_referral_earning(self, referrer_id: int, referred_id: int,
                                    order_id: int, amount: float, percent: float) -> int:
        logger.info(f"Добавление реферального заработка: реферер {referrer_id}, реферал {referred_id}, заказ {order_id}, сумма {amount}, процент {percent}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO referral_earnings (referrer_id, referred_id, order_id, amount, percent)
                VALUES (?, ?, ?, ?, ?)
            """, (referrer_id, referred_id, order_id, amount, percent))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_referral_earnings(self, user_id: int) -> List[Dict]:
        logger.debug(f"Запрос реферальных начислений для пользователя {user_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT re.*, o.amount_rub, o.created_at as order_date
                FROM referral_earnings re
                JOIN exchange_orders o ON re.order_id = o.id
                WHERE re.referrer_id = ?
                ORDER BY re.created_at DESC
            """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @db_retry()
    async def set_fake_total_exchanges(self, user_id: int, fake_count: int) -> bool:
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET fake_total_exchanges = ? WHERE user_id = ?",
                (fake_count, user_id)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def get_fake_total_exchanges(self, user_id: int) -> int:
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT fake_total_exchanges FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return row[0]
            stats = await self.get_user_stats(user_id)
            return stats['total_orders']

    @db_retry()
    async def create_session(self, user_id: int) -> int:
        logger.debug(f"Создание сессии для пользователя {user_id}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO user_sessions (user_id, started_at, last_activity)
                VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id,))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def update_session_activity(self, session_id: int) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE user_sessions 
                SET last_activity = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (session_id,))
            await self.conn.commit()
            return True

    @db_retry()
    async def get_online_users(self, minutes: int = 5) -> int:
        async with self.lock:
            cursor = await self.conn.execute("""
                SELECT COUNT(DISTINCT user_id) FROM user_sessions 
                WHERE last_activity >= DATETIME('now', '-{} minutes')
                AND is_active = 1
            """.format(minutes))
            return (await cursor.fetchone())[0]

    @db_retry()
    async def update_last_activity(self, user_id: int) -> bool:
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            await self.conn.commit()
            return True