# bot/services/db/activity_award_repository.py
import logging
from typing import Optional
from dataclasses import dataclass
import aiosqlite
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class ActivityAward:
    id: int
    user_id: int
    award_type: str
    threshold: int
    awarded_at: str
    coupon_id: Optional[int]


class ActivityAwardRepository(BaseRepository):

    @db_retry()
    async def add_award(self, user_id: int, award_type: str, threshold: int, coupon_id: Optional[int] = None) -> int:
        logger.info(f"Добавление награды пользователю {user_id}: {award_type} (порог {threshold})")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO activity_awards (user_id, award_type, threshold, coupon_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, award_type, threshold, coupon_id))
            await self.conn.commit()
            award_id = cursor.lastrowid
            logger.debug(f"Награда добавлена, ID: {award_id}")
            return award_id

    @db_retry()
    async def get_award(self, user_id: int, award_type: str) -> Optional[ActivityAward]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM activity_awards WHERE user_id = ? AND award_type = ?",
                (user_id, award_type)
            )
            row = await cursor.fetchone()
            if row:
                return ActivityAward(**dict(row))
            return None