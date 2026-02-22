# bot/services/db/review_repository.py
import logging
from typing import Optional, List
from dataclasses import dataclass
import aiosqlite
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class Review:
    id: int
    user_id: int
    order_id: int
    rating: int
    comment: Optional[str]
    created_at: str
    is_approved: bool
    admin_reply: Optional[str]
    replied_at: Optional[str]


class ReviewRepository(BaseRepository):

    @db_retry()
    async def create_review(self, user_id: int, order_id: int, rating: int, comment: Optional[str] = None) -> int:
        logger.info(f"Создание отзыва для заказа #{order_id} от пользователя {user_id}, оценка {rating}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO reviews (user_id, order_id, rating, comment)
                VALUES (?, ?, ?, ?)
            """, (user_id, order_id, rating, comment))
            await self.conn.commit()
            review_id = cursor.lastrowid
            logger.info(f"Отзыв #{review_id} создан")
            return review_id

    @db_retry()
    async def get_review(self, review_id: int) -> Optional[Review]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM reviews WHERE id = ?", (review_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Review(**dict(row))
            return None

    @db_retry()
    async def get_reviews_by_user(self, user_id: int) -> List[Review]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM reviews WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [Review(**dict(row)) for row in rows]

    @db_retry()
    async def get_approved_reviews(self, limit: int = 20) -> List[Review]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM reviews WHERE is_approved = 1
                ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            return [Review(**dict(row)) for row in rows]

    @db_retry()
    async def get_pending_reviews(self) -> List[Review]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM reviews WHERE is_approved = 0 ORDER BY created_at ASC"
            )
            rows = await cursor.fetchall()
            return [Review(**dict(row)) for row in rows]

    @db_retry()
    async def approve_review(self, review_id: int) -> bool:
        logger.info(f"Одобрение отзыва #{review_id}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE reviews SET is_approved = 1 WHERE id = ?",
                (review_id,)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def add_admin_reply(self, review_id: int, reply: str) -> bool:
        logger.info(f"Добавление ответа админа на отзыв #{review_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE reviews SET admin_reply = ?, replied_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (reply, review_id))
            await self.conn.commit()
            return True