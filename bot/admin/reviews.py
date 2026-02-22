# bot/admin/reviews.py
"""Админ-панель для модерации отзывов."""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.review_service import review_service
from bot.admin.main import is_admin

logger = logging.getLogger(__name__)
router = Router()


class AdminReviewStates(StatesGroup):
    replying_to_review = State()      # ответ на отзыв


async def admin_reviews_keyboard(reviews: list, page: int = 0, per_page: int = 5):
    """Асинхронно строит клавиатуру со списком отзывов и именами пользователей."""
    kb = InlineKeyboardBuilder()
    start = page * per_page
    for rev in reviews[start:start+per_page]:
        # Получаем пользователя асинхронно
        user = await db.get_user(rev.user_id)
        username = user.username if user and user.username else f"ID {rev.user_id}"
        kb.button(
            text=f"{rev.rating}⭐ {username} - {rev.created_at[:10]}",
            callback_data=f"admin_review_view_{rev.id}"
        )
    if page > 0:
        kb.button(text="◀️ Назад", callback_data=f"admin_reviews_page_{page-1}")
    if start + per_page < len(reviews):
        kb.button(text="Вперёд ▶️", callback_data=f"admin_reviews_page_{page+1}")
    kb.button(text="🔙 В админку", callback_data="admin_back_main")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "admin_reviews_menu")
async def admin_reviews_menu(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    pending = await review_service.get_pending_reviews()
    text = f"📝 <b>Отзывы, ожидающие модерации</b> (всего: {len(pending)})\n\n"
    if not pending:
        text += "Новых отзывов нет."
        kb = InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_back_main").as_markup()
    else:
        kb = await admin_reviews_keyboard(pending)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reviews_page_"))
async def admin_reviews_page(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    page = int(callback.data.split("_")[3])
    pending = await review_service.get_pending_reviews()
    text = f"📝 <b>Отзывы, ожидающие модерации</b> (всего: {len(pending)})\n\n"
    kb = await admin_reviews_keyboard(pending, page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_review_view_"))
async def admin_review_view(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    review_id = int(callback.data.split("_")[3])
    review = await review_service.get_review(review_id)
    if not review:
        await callback.answer("❌ Отзыв не найден", show_alert=True)
        return

    user = await db.get_user(review.user_id)
    username = f"@{user.username}" if user and user.username else f"ID {review.user_id}"
    rating_stars = "⭐" * review.rating + "☆" * (5 - review.rating)

    text = (
        f"📝 <b>Отзыв #{review.id}</b>\n\n"
        f"Пользователь: {username}\n"
        f"Заявка: #{review.order_id}\n"
        f"Оценка: {rating_stars}\n"
        f"Комментарий: {review.comment or '—'}\n"
        f"Дата: {review.created_at[:16]}\n"
        f"Статус: {'✅ Опубликован' if review.is_approved else '⏳ На модерации'}\n"
    )
    if review.admin_reply:
        text += f"Ответ администратора: {review.admin_reply}\n"

    kb = InlineKeyboardBuilder()
    if not review.is_approved:
        kb.button(text="✅ Одобрить", callback_data=f"admin_review_approve_{review.id}")
    kb.button(text="✏️ Ответить", callback_data=f"admin_review_reply_{review.id}")
    kb.button(text="🗑 Удалить", callback_data=f"admin_review_delete_{review.id}")
    kb.button(text="🔙 Назад", callback_data="admin_reviews_menu")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_review_approve_"))
async def admin_review_approve(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    review_id = int(callback.data.split("_")[3])
    await review_service.approve_review(review_id)
    await callback.answer("✅ Отзыв одобрен", show_alert=True)
    await admin_review_view(callback)


@router.callback_query(F.data.startswith("admin_review_reply_"))
async def admin_review_reply_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    review_id = int(callback.data.split("_")[3])
    await state.set_state(AdminReviewStates.replying_to_review)
    await state.update_data(reply_review_id=review_id)
    await callback.message.answer("✏️ Введите ваш ответ на отзыв:")
    await callback.answer()


@router.message(AdminReviewStates.replying_to_review)
async def admin_review_reply_message(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    data = await state.get_data()
    review_id = data.get('reply_review_id')
    reply_text = message.text

    await review_service.add_admin_reply(review_id, reply_text)
    await message.answer("✅ Ответ добавлен к отзыву.")
    await state.clear()


@router.callback_query(F.data.startswith("admin_review_delete_"))
async def admin_review_delete(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    review_id = int(callback.data.split("_")[3])
    await review_service.delete_review(review_id)
    await callback.answer("🗑 Отзыв удалён", show_alert=True)
    await admin_reviews_menu(callback)