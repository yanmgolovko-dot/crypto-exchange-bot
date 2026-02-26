# bot/admin/fake.py
"""Управление фейковыми данными: отзывы, сделки, пользователи."""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.main import is_admin
from bot.utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_fake_menu")
async def admin_fake_menu(callback: CallbackQuery):
    """Главное меню управления фейками."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📝 Создать фейк-отзыв", callback_data="admin_review_create_fake")
    keyboard.button(text="🔢 Установить фейк-сделки пользователю", callback_data="admin_fake_exchanges")
    keyboard.button(text="📋 Изменить номер заявки", callback_data="admin_set_next_order_number")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await safe_edit_message(
        callback.message,
        "🪄 <b>Управление фейковыми данными</b>\n\n"
        "Вы можете создавать искусственные отзывы, "
        "изменять количество сделок пользователей и номера заявок.",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()