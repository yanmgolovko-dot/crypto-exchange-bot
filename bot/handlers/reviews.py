# bot/handlers/reviews.py
"""Обработчики для отзывов: публичный просмотр и создание после заявки."""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.review_service import review_service
from bot.keyboards import main_menu_keyboard
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


class ReviewStates(StatesGroup):
    waiting_for_rating = State()      # ожидание оценки (1-5)
    waiting_for_comment = State()      # ожидание комментария (опционально)


# ========== ПУБЛИЧНЫЙ РАЗДЕЛ ОТЗЫВОВ ==========
@router.message(F.text == "📝 Отзывы")
async def reviews_public(message: Message):
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Запрос публичных отзывов")

    try:
        reviews = await review_service.get_approved_reviews(limit=10)
        if not reviews:
            text = "📝 Пока нет ни одного отзыва. Будьте первым!"
        else:
            text = "📝 <b>Отзывы наших клиентов</b>\n\n"
            for rev in reviews:
                # Определяем отображаемое имя
                if rev.username:
                    display_name = rev.username
                elif rev.user_id:
                    user = await db.get_user(rev.user_id)
                    if user and user.username:
                        display_name = f"@{user.username}"
                    elif user and user.first_name:
                        display_name = user.first_name
                    else:
                        display_name = f"ID {rev.user_id}"
                else:
                    display_name = "Аноним"

                # Определяем количество сделок
                if getattr(rev, 'fake_exchanges', None) is not None:
                    exchanges = rev.fake_exchanges
                elif rev.user_id:
                    try:
                        stats = await db.get_user_stats(rev.user_id)
                        exchanges = stats.get('total_orders', 0)
                    except Exception:
                        exchanges = 0
                else:
                    exchanges = 0

                rating_stars = "⭐" * rev.rating + "☆" * (5 - rev.rating)

                text += f"<b>{escape_html(display_name)}</b>  {rating_stars}  (<i>{exchanges} обменов</i>)\n"
                text += f"{escape_html(rev.comment) if rev.comment else '<i>Без комментария</i>'}\n"
                if rev.admin_reply:
                    text += f"<i>Ответ администратора: {escape_html(rev.admin_reply)}</i>\n"
                date_str = str(rev.created_at)[:10] if rev.created_at else ""
                text += f"—— {date_str}\n\n"

        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Главное меню", callback_data="reviews_back_main")
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка при загрузке отзывов: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке отзывов. Попробуйте позже.")


@router.callback_query(F.data == "reviews_back_main")
async def reviews_back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ========== ПРЕДЛОЖЕНИЕ ОСТАВИТЬ ОТЗЫВ ПОСЛЕ ЗАЯВКИ ==========
@router.callback_query(F.data.startswith("review_rate_"))
async def review_rate_callback(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    order_id = int(parts[2])
    rating = int(parts[3])

    await state.update_data(review_order_id=order_id, review_rating=rating)
    await state.set_state(ReviewStates.waiting_for_comment)

    await safe_edit_message(
        callback.message,
        f"Вы поставили {rating} ⭐. Напишите, пожалуйста, комментарий (или отправьте /skip, чтобы пропустить):"
    )
    await callback.answer()


@router.message(ReviewStates.waiting_for_comment)
async def review_comment_received(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('review_order_id')
    rating = data.get('review_rating')
    comment = None if message.text == "/skip" else message.text

    user_id = message.from_user.id

    try:
        review_id = await review_service.create_review(user_id, order_id, rating, comment)
        await message.answer(
            "✅ Спасибо за ваш отзыв! Он будет опубликован после проверки администратором."
        )
        logger.info(f"Отзыв #{review_id} создан пользователем {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при создании отзыва: {e}")
        await message.answer("❌ Произошла ошибка при сохранении отзыва. Попробуйте позже.")

    await state.clear()