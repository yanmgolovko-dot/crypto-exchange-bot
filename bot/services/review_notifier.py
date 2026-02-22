# bot/services/review_notifier.py
import logging
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

async def ask_for_review(bot: Bot, user_id: int, order_id: int):
    """Отправляет пользователю предложение оценить заявку."""
    try:
        kb = InlineKeyboardBuilder()
        for i in range(1, 6):
            kb.button(text=f"{i} ⭐", callback_data=f"review_rate_{order_id}_{i}")
        kb.adjust(5)
        await bot.send_message(
            user_id,
            f"✨ Спасибо за использование нашего сервиса!\n"
            f"Оцените, пожалуйста, вашу заявку #{order_id} от 1 до 5 звёзд:",
            reply_markup=kb.as_markup()
        )
        logger.info(f"Запрос отзыва отправлен пользователю {user_id} по заявке #{order_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить запрос отзыва пользователю {user_id}: {e}")