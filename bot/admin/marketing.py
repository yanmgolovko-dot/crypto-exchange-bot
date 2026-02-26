# bot/admin/marketing.py
"""Подменю маркетинга: купоны, промокоды, отзывы, партнёры."""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.main import is_admin
from bot.admin.coupons import router as coupons_router
from bot.admin.promocodes import router as promocodes_router
from bot.admin.reviews import router as reviews_router
from bot.admin.partners import router as partners_router
from bot.utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router()

# Включаем дочерние роутеры
router.include_router(coupons_router)
router.include_router(promocodes_router)
router.include_router(reviews_router)
router.include_router(partners_router)


@router.callback_query(F.data == "admin_marketing_menu")
async def admin_marketing_menu(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎫 Купоны", callback_data="admin_coupons_menu")
    keyboard.button(text="🎁 Промокоды", callback_data="admin_promo_menu")
    keyboard.button(text="📝 Отзывы", callback_data="admin_reviews_menu")
    keyboard.button(text="🤝 Партнёры", callback_data="admin_partners_menu")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await safe_edit_message(
        callback.message,
        "🎯 <b>Маркетинговые инструменты</b>\n\nВыберите раздел:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()