# bot/services/db/admins_repository.py
import logging
from typing import Optional, List
from dataclasses import dataclass
import aiosqlite
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class Admin:
    user_id: int
    added_by: Optional[int]
    created_at: str


class AdminsRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей admins.
    Позволяет добавлять, удалять и получать администраторов из БД.
    """

    @db_retry()
    async def add_admin(self, user_id: int, added_by: int) -> bool:
        """Добавляет пользователя в администраторы."""
        logger.info(f"Добавление администратора {user_id} пользователем {added_by}")
        async with self.lock:
            await self.conn.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def remove_admin(self, user_id: int) -> bool:
        """Удаляет пользователя из администраторов."""
        logger.info(f"Удаление администратора {user_id}")
        async with self.lock:
            await self.conn.execute(
                "DELETE FROM admins WHERE user_id = ?", (user_id,)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def get_admin(self, user_id: int) -> Optional[Admin]:
        """Проверяет, является ли пользователь администратором (только из БД)."""
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM admins WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Admin(**dict(row))
            return None

    @db_retry()
    async def get_all_admins(self) -> List[Admin]:
        """Возвращает список всех администраторов из БД."""
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM admins ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [Admin(**dict(row)) for row in rows]

    @db_retry()
    async def is_admin(self, user_id: int) -> bool:
        """Быстрая проверка наличия пользователя в таблице admins."""
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
            )
            result = await cursor.fetchone()
            return result is not None