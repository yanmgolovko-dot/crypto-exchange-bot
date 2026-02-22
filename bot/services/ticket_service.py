# bot/services/ticket_service.py
"""Сервис для работы с тикетами (обращениями в поддержку)."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from bot.services.db import db
from bot.services.db.unit_of_work import UnitOfWork
from bot.services.db.ticket_repository import Ticket, TicketMessage

logger = logging.getLogger(__name__)


class TicketService:
    """Бизнес-логика для тикетов."""

    async def create_ticket(self, user_id: int, subject: Optional[str] = None) -> int:
        """
        Создаёт новый тикет с темой (опционально).
        Возвращает ID созданного тикета.
        """
        logger.info(f"Создание тикета для пользователя {user_id}")
        async with db.uow() as uow:
            ticket_id = await uow.tickets.create_ticket(user_id, subject)
            await uow.commit()
            logger.info(f"Тикет #{ticket_id} создан")
            return ticket_id

    async def add_message(
        self,
        ticket_id: int,
        sender_id: int,
        is_admin: bool,
        message: str,
        file_path: Optional[str] = None
    ) -> int:
        """
        Добавляет сообщение в тикет.
        Если сообщение от администратора, уведомляет пользователя (это будет в хендлере).
        """
        logger.info(f"Добавление сообщения в тикет #{ticket_id} от {'админа' if is_admin else 'пользователя'}")
        async with db.uow() as uow:
            msg_id = await uow.tickets.add_message(ticket_id, sender_id, is_admin, message, file_path)
            await uow.commit()
            return msg_id

    async def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        """Получает тикет по ID."""
        return await db.tickets.get_ticket(ticket_id)

    async def get_user_tickets(self, user_id: int) -> List[Ticket]:
        """Получает все тикеты пользователя."""
        return await db.tickets.get_user_tickets(user_id)

    async def get_open_tickets(self) -> List[Ticket]:
        """Получает все открытые тикеты (для админов)."""
        return await db.tickets.get_open_tickets()

    async def get_messages(self, ticket_id: int) -> List[TicketMessage]:
        """Получает все сообщения тикета."""
        return await db.tickets.get_messages(ticket_id)

    async def close_ticket(self, ticket_id: int, closed_by: int) -> bool:
        """Закрывает тикет."""
        logger.info(f"Закрытие тикета #{ticket_id} пользователем {closed_by}")
        async with db.uow() as uow:
            await uow.tickets.close_ticket(ticket_id, closed_by)
            await uow.commit()
            return True

    async def is_ticket_open(self, ticket_id: int) -> bool:
        """Проверяет, открыт ли тикет."""
        ticket = await self.get_ticket(ticket_id)
        return ticket is not None and ticket.status == 'open'


# Глобальный экземпляр
ticket_service = TicketService()