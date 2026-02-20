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


class UserRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей users.
    Содержит методы для добавления/обновления пользователей, бана,
    статистики, сессий и реферальных начислений.
    """

    @db_retry()
    async def add_or_update_user(self, user_id: int, username: str = None,
                                  first_name: str = None, last_name: str = None) -> bool:
        """
        Добавляет нового пользователя или обновляет данные существующего.
        Автоматически обновляет last_activity.
        """
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
            logger.debug(f"[{user_id}] Данные пользователя сохранены")
            return True

    @db_retry()
    async def set_referrer(self, user_id: int, referrer_id: int) -> bool:
        """Устанавливает реферера для пользователя (если ещё не установлен)."""
        logger.info(f"[{user_id}] Установка реферера {referrer_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL
            """, (referrer_id, user_id))
            await self.conn.commit()
            logger.debug(f"[{user_id}] Реферер {referrer_id} установлен")
            return True

    @db_retry()
    async def get_user(self, user_id: int) -> Optional[User]:
        """Получает пользователя по ID."""
        logger.debug(f"Запрос пользователя {user_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Пользователь {user_id} найден")
                return User(**dict(row))
            logger.debug(f"Пользователь {user_id} не найден")
            return None

    @db_retry()
    async def get_all_users(self) -> List[User]:
        """Возвращает список всех пользователей."""
        logger.debug("Запрос всех пользователей")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("SELECT * FROM users ORDER BY user_id")
            rows = await cursor.fetchall()
            users = [User(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(users)} пользователей")
            return users

    @db_retry()
    async def ban_user(self, user_id: int, reason: str, banned_by: int) -> bool:
        """Банит пользователя с указанием причины и ID администратора."""
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
            logger.info(f"Пользователь {user_id} забанен")
            return True

    @db_retry()
    async def unban_user(self, user_id: int) -> bool:
        """Снимает бан с пользователя."""
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
            logger.info(f"Пользователь {user_id} разбанен")
            return True

    @db_retry()
    async def is_user_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, забанен ли пользователь, и возвращает причину."""
        user = await self.get_user(user_id)
        if user and user.is_banned:
            logger.debug(f"Пользователь {user_id} забанен: {user.ban_reason}")
            return True, user.ban_reason
        logger.debug(f"Пользователь {user_id} не забанен")
        return False, None

    @db_retry()
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Возвращает статистику пользователя: количество заявок, общий объём, сэкономлено."""
        logger.debug(f"Запрос статистики для пользователя {user_id}")
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE user_id = ?",
                (user_id,)
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

            logger.debug(f"Статистика пользователя {user_id}: заявок={total_orders}, объём={total_volume}, сэкономлено={total_saved}")
            return {
                'total_orders': total_orders,
                'total_volume': total_volume,
                'total_saved': total_saved
            }

    @db_retry()
    async def set_user_notifications(self, user_id: int, enabled: bool) -> bool:
        """Включает или отключает уведомления для пользователя."""
        logger.info(f"[{user_id}] Установка уведомлений: {enabled}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
                (enabled, user_id)
            )
            await self.conn.commit()
            logger.debug(f"[{user_id}] Уведомления установлены")
            return True

    @db_retry()
    async def add_referral_earning(self, referrer_id: int, referred_id: int,
                                    order_id: int, amount: float, percent: float) -> int:
        """
        Добавляет запись о реферальном заработке.
        Возвращает ID созданной записи.
        """
        logger.info(f"Добавление реферального заработка: реферер {referrer_id}, реферал {referred_id}, заказ {order_id}, сумма {amount}, процент {percent}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO referral_earnings (referrer_id, referred_id, order_id, amount, percent)
                VALUES (?, ?, ?, ?, ?)
            """, (referrer_id, referred_id, order_id, amount, percent))
            await self.conn.commit()
            record_id = cursor.lastrowid
            logger.info(f"Реферальный заработок добавлен, ID записи: {record_id}")
            return record_id

    @db_retry()
    async def get_referral_earnings(self, user_id: int) -> List[Dict]:
        """
        Возвращает список реферальных начислений для пользователя с информацией о заказах.
        """
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
            earnings = [dict(row) for row in rows]
            logger.debug(f"Найдено {len(earnings)} записей")
            return earnings

    # ==================== СЕССИИ ПОЛЬЗОВАТЕЛЕЙ ====================

    @db_retry()
    async def create_session(self, user_id: int) -> int:
        """Создаёт новую сессию пользователя."""
        logger.debug(f"Создание сессии для пользователя {user_id}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO user_sessions (user_id, started_at, last_activity)
                VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id,))
            await self.conn.commit()
            session_id = cursor.lastrowid
            logger.debug(f"Сессия {session_id} создана")
            return session_id

    @db_retry()
    async def update_session_activity(self, session_id: int) -> bool:
        """Обновляет время последней активности сессии."""
        logger.debug(f"Обновление активности сессии {session_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE user_sessions 
                SET last_activity = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (session_id,))
            await self.conn.commit()
            logger.debug(f"Активность сессии {session_id} обновлена")
            return True

    @db_retry()
    async def get_online_users(self, minutes: int = 5) -> int:
        """Возвращает количество уникальных пользователей, активных за последние minutes минут."""
        logger.debug(f"Запрос количества онлайн пользователей за {minutes} мин")
        async with self.lock:
            cursor = await self.conn.execute("""
                SELECT COUNT(DISTINCT user_id) FROM user_sessions 
                WHERE last_activity >= DATETIME('now', '-{} minutes')
                AND is_active = 1
            """.format(minutes))
            count = (await cursor.fetchone())[0]
            logger.debug(f"Онлайн пользователей: {count}")
            return count

    @db_retry()
    async def update_last_activity(self, user_id: int) -> bool:
        """Обновляет поле last_activity у пользователя (без создания сессии)."""
        logger.debug(f"Обновление last_activity для пользователя {user_id}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            await self.conn.commit()
            logger.debug(f"last_activity обновлён")
            return True