# bot/services/db/ticket_repository.py
import logging
from typing import Optional, List
from dataclasses import dataclass
import aiosqlite
from .base import BaseRepository, db_retry

logger = logging.getLogger(__name__)


@dataclass
class Ticket:
    id: int
    user_id: int
    status: str
    subject: Optional[str]
    created_at: str
    updated_at: str
    closed_by: Optional[int]
    closed_at: Optional[str]


@dataclass
class TicketMessage:
    id: int
    ticket_id: int
    sender_id: int
    is_admin: bool
    message: str
    file_path: Optional[str]
    created_at: str


class TicketRepository(BaseRepository):

    @db_retry()
    async def create_ticket(self, user_id: int, subject: Optional[str] = None) -> int:
        logger.info(f"Создание тикета для пользователя {user_id}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO tickets (user_id, subject)
                VALUES (?, ?)
            """, (user_id, subject))
            await self.conn.commit()
            ticket_id = cursor.lastrowid
            logger.info(f"Тикет #{ticket_id} создан")
            return ticket_id

    @db_retry()
    async def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
            )
            row = await cursor.fetchone()
            if row:
                return Ticket(**dict(row))
            return None

    @db_retry()
    async def get_user_tickets(self, user_id: int) -> List[Ticket]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM tickets WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [Ticket(**dict(row)) for row in rows]

    @db_retry()
    async def get_open_tickets(self) -> List[Ticket]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM tickets WHERE status = 'open' ORDER BY updated_at DESC"
            )
            rows = await cursor.fetchall()
            return [Ticket(**dict(row)) for row in rows]

    @db_retry()
    async def close_ticket(self, ticket_id: int, closed_by: int) -> bool:
        logger.info(f"Закрытие тикета #{ticket_id} пользователем {closed_by}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE tickets SET status = 'closed', updated_at = CURRENT_TIMESTAMP,
                                    closed_by = ?, closed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (closed_by, ticket_id))
            await self.conn.commit()
            logger.debug(f"Тикет #{ticket_id} закрыт")
            return True

    @db_retry()
    async def add_message(self, ticket_id: int, sender_id: int, is_admin: bool,
                          message: str, file_path: Optional[str] = None) -> int:
        logger.info(f"Добавление сообщения в тикет #{ticket_id} от {'админа' if is_admin else 'пользователя'}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO ticket_messages (ticket_id, sender_id, is_admin, message, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (ticket_id, sender_id, is_admin, message, file_path))
            await self.conn.execute("""
                UPDATE tickets SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (ticket_id,))
            await self.conn.commit()
            msg_id = cursor.lastrowid
            logger.debug(f"Сообщение #{msg_id} добавлено")
            return msg_id

    @db_retry()
    async def get_messages(self, ticket_id: int) -> List[TicketMessage]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC",
                (ticket_id,)
            )
            rows = await cursor.fetchall()
            return [TicketMessage(**dict(row)) for row in rows]