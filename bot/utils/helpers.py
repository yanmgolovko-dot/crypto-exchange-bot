# bot/utils/helpers.py
"""Вспомогательные функции для бота."""

import html
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


async def safe_edit_message(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: str = None,
    disable_web_page_preview: bool = None
) -> bool:
    """
    Безопасно редактирует сообщение, проверяя, изменилось ли оно.
    Возвращает True, если сообщение было изменено, иначе False.
    """
    try:
        # Проверяем, нужно ли редактировать
        if message.text != text or message.reply_markup != reply_markup:
            await message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return True
        return False
    except TelegramBadRequest as e:
        # Игнорируем ошибку "message is not modified", остальные пробрасываем
        if "message is not modified" not in str(e):
            raise
        return False


def escape_html(text: str) -> str:
    """Экранирует специальные символы HTML."""
    return html.escape(text)