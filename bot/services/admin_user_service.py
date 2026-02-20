"""Сервис для админ-операций с пользователями"""

import logging
from typing import List, Optional, Dict, Any

from bot.services.db import Database

logger = logging.getLogger(__name__)


class AdminUserService:
    def __init__(self, db: Database):
        self.db = db

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить полную информацию о пользователе"""
        user = await self.db.get_user(user_id)
        if not user:
            return None
        stats = await self.db.get_user_stats(user_id)
        return {
            'user': user,
            'stats': stats
        }

    async def ban_user(self, user_id: int, reason: str, admin_id: int) -> bool:
        """Забанить пользователя"""
        return await self.db.ban_user(user_id, reason, admin_id)

    async def unban_user(self, user_id: int) -> bool:
        """Разбанить пользователя"""
        return await self.db.unban_user(user_id)

    async def get_all_users_paginated(self, offset: int = 0, limit: int = 5) -> Dict[str, Any]:
        """Получить пользователей с пагинацией"""
        users = await self.db.get_all_users()
        total = len(users)
        paginated = users[offset:offset+limit]
        return {
            'users': paginated,
            'total': total,
            'offset': offset,
            'limit': limit
        }

    async def get_banned_users_paginated(self, offset: int = 0, limit: int = 5) -> Dict[str, Any]:
        """Получить забаненных пользователей с пагинацией"""
        users = await self.db.get_all_users()
        banned = [u for u in users if u.is_banned]
        total = len(banned)
        paginated = banned[offset:offset+limit]
        return {
            'users': paginated,
            'total': total,
            'offset': offset,
            'limit': limit
        }

    async def find_user_by_username(self, username: str) -> Optional[Any]:
        """Поиск пользователя по username (без @)"""
        users = await self.db.get_all_users()
        for user in users:
            if user.username and user.username.lower() == username.lower():
                return user
        return None