# bot/services/user_service.py
"""Сервис для работы с пользователями: регистрация, бан, рефералы."""

import logging
from typing import Optional, Tuple, Dict, Any

from bot.services.db import Database

logger = logging.getLogger(__name__)


class UserService:
    """
    Сервис, инкапсулирующий бизнес-логику, связанную с пользователями:
    - регистрация и обновление данных
    - бан и разбан
    - реферальная система
    - получение статистики
    """

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
        """
        Регистрирует нового пользователя или обновляет данные существующего.
        Если передан referred_by, устанавливает реферера (только при первой регистрации).
        """
        logger.info(f"[{user_id}] Регистрация/обновление пользователя")
        try:
            await self.db.add_or_update_user(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            logger.debug(f"[{user_id}] Основные данные сохранены")

            if referred_by and referred_by != user_id:
                await self.db.set_referrer(user_id, referred_by)
                logger.info(f"[{user_id}] Установлен реферер {referred_by}")

            return True
        except Exception as e:
            logger.error(f"[{user_id}] Ошибка при регистрации пользователя: {e}", exc_info=True)
            return False

    async def ban_user(self, user_id: int, reason: str, admin_id: int) -> bool:
        """Банит пользователя с указанием причины и ID администратора."""
        logger.info(f"[ADMIN {admin_id}] Бан пользователя {user_id}, причина: {reason}")
        try:
            result = await self.db.ban_user(user_id, reason, admin_id)
            if result:
                logger.info(f"[ADMIN {admin_id}] Пользователь {user_id} успешно забанен")
            else:
                logger.warning(f"[ADMIN {admin_id}] Не удалось забанить пользователя {user_id} (возможно, не существует)")
            return result
        except Exception as e:
            logger.error(f"[ADMIN {admin_id}] Ошибка при бане пользователя {user_id}: {e}", exc_info=True)
            return False

    async def unban_user(self, user_id: int) -> bool:
        """Снимает бан с пользователя."""
        logger.info(f"Снятие бана с пользователя {user_id}")
        try:
            result = await self.db.unban_user(user_id)
            if result:
                logger.info(f"Пользователь {user_id} разбанен")
            else:
                logger.warning(f"Не удалось разбанить пользователя {user_id} (возможно, не существует или не был забанен)")
            return result
        except Exception as e:
            logger.error(f"Ошибка при снятии бана с пользователя {user_id}: {e}", exc_info=True)
            return False

    async def is_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Проверяет, забанен ли пользователь, и возвращает причину, если да."""
        logger.debug(f"Проверка бана для пользователя {user_id}")
        try:
            banned, reason = await self.db.is_user_banned(user_id)
            if banned:
                logger.debug(f"Пользователь {user_id} забанен: {reason}")
            else:
                logger.debug(f"Пользователь {user_id} не забанен")
            return banned, reason
        except Exception as e:
            logger.error(f"Ошибка при проверке бана пользователя {user_id}: {e}", exc_info=True)
            return False, None

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Возвращает статистику пользователя: количество заявок, объём, сэкономленные средства."""
        logger.info(f"Запрос статистики для пользователя {user_id}")
        try:
            stats = await self.db.get_user_stats(user_id)
            logger.debug(f"Статистика пользователя {user_id}: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Ошибка при получении статистики пользователя {user_id}: {e}", exc_info=True)
            return {'total_orders': 0, 'total_volume': 0.0, 'total_saved': 0.0}

    async def get_user_info(self, user_id: int):
        """Возвращает объект пользователя из БД."""
        logger.debug(f"Запрос информации о пользователе {user_id}")
        try:
            user = await self.db.get_user(user_id)
            if user:
                logger.debug(f"Пользователь {user_id} найден: {user}")
            else:
                logger.debug(f"Пользователь {user_id} не найден")
            return user
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пользователе {user_id}: {e}", exc_info=True)
            return None

    async def add_referral_earning(
        self,
        referrer_id: int,
        referred_id: int,
        order_id: int,
        amount: float,
        percent: float
    ) -> int:
        """
        Добавляет запись о реферальном заработке.
        Возвращает ID созданной записи или 0 при ошибке.
        """
        logger.info(f"Добавление реферального заработка: реферер {referrer_id}, реферал {referred_id}, заказ {order_id}")
        try:
            record_id = await self.db.add_referral_earning(referrer_id, referred_id, order_id, amount, percent)
            logger.info(f"Реферальный заработок добавлен, ID записи: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении реферального заработка: {e}", exc_info=True)
            return 0

    async def get_referral_earnings(self, user_id: int) -> list:
        """Возвращает список реферальных начислений для пользователя."""
        logger.info(f"Запрос реферальных начислений для пользователя {user_id}")
        try:
            earnings = await self.db.get_referral_earnings(user_id)
            logger.debug(f"Найдено {len(earnings)} записей для пользователя {user_id}")
            return earnings
        except Exception as e:
            logger.error(f"Ошибка при получении реферальных начислений для пользователя {user_id}: {e}", exc_info=True)
            return []