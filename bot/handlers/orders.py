# bot/handlers/orders.py
"""
Обработчики для просмотра пользователем своих заявок.
Позволяет пользователю увидеть список последних заявок с их статусами.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message

from bot.services.db import db

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📋 Мои заявки")
async def my_orders(message: Message):
    """
    Обработчик кнопки «📋 Мои заявки».
    Запрашивает из БД последние 10 заявок пользователя и отображает их.
    """
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Запрос списка своих заявок")

    try:
        # Получаем последние 10 заявок пользователя
        orders = await db.get_user_orders(user_id, limit=10)
        logger.debug(f"[{user_id}] Получено {len(orders)} заявок из БД")
    except Exception as e:
        logger.error(f"[{user_id}] Ошибка при получении заявок из БД: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при загрузке заявок. Попробуйте позже.")
        return

    if not orders:
        logger.info(f"[{user_id}] У пользователя нет заявок")
        await message.answer(
            "📋 У вас пока нет заявок.\n\n"
            "Нажмите «💰 Купить криптовалюту» чтобы создать первую заявку."
        )
        return

    # Формируем текст со списком заявок
    text = "📋 <b>Ваши последние заявки:</b>\n\n"

    for order in orders:
        # Определяем эмодзи и текст статуса
        status_emoji = {
            "pending": "⏳",
            "paid": "💳",
            "completed": "✅",
            "cancelled": "❌"
        }.get(order.status, "❓")

        status_text = {
            "pending": "Ожидает оплаты",
            "paid": "На проверке",
            "completed": "Выполнена",
            "cancelled": "Отменена"
        }.get(order.status, "Неизвестно")

        # Добавляем информацию о заявке
        text += (
            f"{status_emoji} <b>Заявка #{order.id}</b>\n"
            f"   Крипта: {order.crypto_type}\n"
            f"   К оплате: {order.amount_rub:,.0f} ₽ → получите {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Статус: {status_text}\n"
            f"   Дата: {order.created_at[:16] if order.created_at else 'N/A'}\n\n"
        )

    logger.info(f"[{user_id}] Отправлен список из {len(orders)} заявок")
    await message.answer(text, parse_mode="HTML")