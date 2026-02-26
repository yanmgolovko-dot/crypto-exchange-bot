# bot/handlers/common.py
"""
Общий хендлер для отлова всех неперехваченных сообщений.
Используется для диагностики: логирует любое сообщение и отвечает администраторам.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message

from bot.config.settings import config
from bot.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def catch_all_messages(message: Message):
    """
    Перехватывает все сообщения, которые не обработаны другими хендлерами.
    Логирует сообщение и, если отправитель – администратор, отправляет ему уведомление.
    """
    user_id = message.from_user.id
    text = message.text or "[не текст]"
    logger.info(f"🔍 Поймано сообщение от {user_id}: {text}")

    # Отвечаем только администраторам, чтобы не спамить обычным пользователям
    if user_id in config.ADMIN_IDS:
        await message.answer(
            f"📨 Получено сообщение:\n{escape_html(text)}\n\n"
            f"(Это сообщение не было обработано ни одним хендлером.)"
        )