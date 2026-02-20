# bot/services/admin_user_service.py
"""
Сервис для админ-операций с пользователями.
Предоставляет методы для получения информации о пользователях, бана/разбана,
поиска и пагинации.
"""

import logging
from typing import List, Optional, Dict, Any

from bot.services.db import Database

logger = logging.getLogger(__name__)


class AdminUserService:
    """
    Сервис для административных операций с пользователями:
    - получение полной информации о пользователе
    - бан и разбан
    - пагинированные списки всех пользователей и забаненных
    - поиск по username
    """

    def __init__(self, db: Database):
        self.db = db

    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить полную информацию о пользователе вместе со статистикой.
        :param user_id: ID пользователя
        :return: словарь с ключами 'user' (объект User) и 'stats' (статистика)
                 или None, если пользователь не найден
        """
        logger.info(f"Запрос информации о пользователе {user_id}")
        try:
            user = await self.db.get_user(user_id)
            if not user:
                logger.info(f"Пользователь {user_id} не найден")
                return None
            stats = await self.db.get_user_stats(user_id)
            logger.debug(f"Информация о пользователе {user_id} получена")
            return {
                'user': user,
                'stats': stats
            }
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пользователе {user_id}: {e}", exc_info=True)
            return None

    async def ban_user(self, user_id: int, reason: str, admin_id: int) -> bool:
        """
        Забанить пользователя.
        :param user_id: ID пользователя
        :param reason: причина бана
        :param admin_id: ID администратора, выполняющего бан
        :return: True если успешно
        """
        logger.info(f"[ADMIN {admin_id}] Бан пользователя {user_id}, причина: {reason}")
        try:
            result = await self.db.ban_user(user_id, reason, admin_id)
            if result:
                logger.info(f"[ADMIN {admin_id}] Пользователь {user_id} забанен")
            else:
                logger.warning(f"[ADMIN {admin_id}] Не удалось забанить пользователя {user_id}")
            return result
        except Exception as e:
            logger.error(f"[ADMIN {admin_id}] Ошибка при бане пользователя {user_id}: {e}", exc_info=True)
            return False

    async def unban_user(self, user_id: int) -> bool:
        """
        Разбанить пользователя.
        :param user_id: ID пользователя
        :return: True если успешно
        """
        logger.info(f"Разбан пользователя {user_id}")
        try:
            result = await self.db.unban_user(user_id)
            if result:
                logger.info(f"Пользователь {user_id} разбанен")
            else:
                logger.warning(f"Не удалось разбанить пользователя {user_id}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при разбане пользователя {user_id}: {e}", exc_info=True)
            return False

    async def get_all_users_paginated(self, offset: int = 0, limit: int = 5) -> Dict[str, Any]:
        """
        Получить список всех пользователей с пагинацией.
        :param offset: смещение
        :param limit: количество записей на странице
        :return: словарь с ключами 'users' (список), 'total', 'offset', 'limit'
        """
        logger.info(f"Запрос списка всех пользователей (offset={offset}, limit={limit})")
        try:
            users = await self.db.get_all_users()
            total = len(users)
            paginated = users[offset:offset+limit]
            logger.debug(f"Получено {len(paginated)} пользователей из {total}")
            return {
                'users': paginated,
                'total': total,
                'offset': offset,
                'limit': limit
            }
        except Exception as e:
            logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
            return {'users': [], 'total': 0, 'offset': offset, 'limit': limit}

    async def get_banned_users_paginated(self, offset: int = 0, limit: int = 5) -> Dict[str, Any]:
        """
        Получить список забаненных пользователей с пагинацией.
        :param offset: смещение
        :param limit: количество записей на странице
        :return: словарь с ключами 'users' (список), 'total', 'offset', 'limit'
        """
        logger.info(f"Запрос списка забаненных пользователей (offset={offset}, limit={limit})")
        try:
            users = await self.db.get_all_users()
            banned = [u for u in users if u.is_banned]
            total = len(banned)
            paginated = banned[offset:offset+limit]
            logger.debug(f"Получено {len(paginated)} забаненных из {total}")
            return {
                'users': paginated,
                'total': total,
                'offset': offset,
                'limit': limit
            }
        except Exception as e:
            logger.error(f"Ошибка при получении списка забаненных: {e}", exc_info=True)
            return {'users': [], 'total': 0, 'offset': offset, 'limit': limit}

    async def find_user_by_username(self, username: str) -> Optional[Any]:
        """
        Поиск пользователя по username (без символа @).
        :param username: username (например, 'durov')
        :return: объект User или None
        """
        logger.info(f"Поиск пользователя по username: {username}")
        try:
            users = await self.db.get_all_users()
            for user in users:
                if user.username and user.username.lower() == username.lower():
                    logger.debug(f"Пользователь с username {username} найден: ID {user.user_id}")
                    return user
            logger.info(f"Пользователь с username {username} не найден")
            return None
        except Exception as e:
            logger.error(f"Ошибка при поиске пользователя по username {username}: {e}", exc_info=True)
            return None