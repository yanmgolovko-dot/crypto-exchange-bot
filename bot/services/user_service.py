"""Сервис для работы с пользователями: регистрация, бан, рефералы"""

import logging
from typing import Optional, Tuple, Dict, Any

from bot.services.db import Database

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: Database):
        self.db = db

    async def register_or_update(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        referred_by: Optional[int] = None
    ) -> bool:
        """Регистрирует или обновляет пользователя, обрабатывает реферала"""
        await self.db.add_or_update_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        if referred_by and referred_by != user_id:
            await self.db.set_referrer(user_id, referred_by)
        return True

    async def ban_user(self, user_id: int, reason: str, admin_id: int) -> bool:
        """Банит пользователя"""
        return await self.db.ban_user(user_id, reason, admin_id)

    async def unban_user(self, user_id: int) -> bool:
        """Разбанивает пользователя"""
        return await self.db.unban_user(user_id)

    async def is_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, забанен ли пользователь"""
        return await self.db.is_user_banned(user_id)

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Возвращает статистику пользователя"""
        return await self.db.get_user_stats(user_id)

    async def get_user_info(self, user_id: int):
        """Возвращает объект пользователя"""
        return await self.db.get_user(user_id)

    async def add_referral_earning(
        self,
        referrer_id: int,
        referred_id: int,
        order_id: int,
        amount: float,
        percent: float
    ) -> int:
        return await self.db.add_referral_earning(referrer_id, referred_id, order_id, amount, percent)

    async def get_referral_earnings(self, user_id: int) -> list:
        return await self.db.get_referral_earnings(user_id)