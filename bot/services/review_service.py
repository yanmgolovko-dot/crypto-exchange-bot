# bot/services/review_service.py
"""Сервис для работы с отзывами."""

import logging
from typing import Optional, List, Dict, Any

from bot.services.db import db
from bot.services.db.review_repository import Review

logger = logging.getLogger(__name__)


class ReviewService:
    """Бизнес-логика для отзывов."""

    async def create_review(self, user_id: int, order_id: int, rating: int, comment: Optional[str] = None) -> int:
        """
        Создаёт новый отзыв. Отзыв создаётся со статусом is_approved = False (ожидает модерации).
        """
        logger.info(f"Создание отзыва для заказа #{order_id} от пользователя {user_id}")
        async with db.uow() as uow:
            review_id = await uow.reviews.create_review(user_id, order_id, rating, comment)
            await uow.commit()
            logger.info(f"Отзыв #{review_id} создан, ожидает модерации")
            return review_id

    async def get_review(self, review_id: int) -> Optional[Review]:
        """Получает отзыв по ID."""
        return await db.reviews.get_review(review_id)

    async def get_approved_reviews(self, limit: int = 20) -> List[Review]:
        """Получает последние одобренные отзывы (для публичного показа)."""
        return await db.reviews.get_approved_reviews(limit)

    async def get_user_reviews(self, user_id: int) -> List[Review]:
        """Получает все отзывы пользователя (для личного кабинета)."""
        return await db.reviews.get_reviews_by_user(user_id)

    async def get_pending_reviews(self) -> List[Review]:
        """Получает все отзывы, ожидающие модерации (для админа)."""
        return await db.reviews.get_pending_reviews()

    async def approve_review(self, review_id: int) -> bool:
        """Одобряет отзыв (делает публичным)."""
        logger.info(f"Одобрение отзыва #{review_id}")
        async with db.uow() as uow:
            await uow.reviews.approve_review(review_id)
            await uow.commit()
            return True

    async def add_admin_reply(self, review_id: int, reply: str) -> bool:
        """Добавляет ответ администратора на отзыв."""
        logger.info(f"Добавление ответа админа на отзыв #{review_id}")
        async with db.uow() as uow:
            await uow.reviews.add_admin_reply(review_id, reply)
            await uow.commit()
            return True

    async def delete_review(self, review_id: int) -> bool:
        """Удаляет отзыв (только для админа)."""
        logger.info(f"Удаление отзыва #{review_id}")
        async with db.uow() as uow:
            await uow._connection.conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
            await uow.commit()
            return True


# Глобальный экземпляр
review_service = ReviewService()