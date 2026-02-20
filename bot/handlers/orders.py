"""Просмотр заявок пользователем"""

from aiogram import Router, F
from aiogram.types import Message

from bot.services.db import db

router = Router()

@router.message(F.text == "📋 Мои заявки")
async def my_orders(message: Message):
    orders = await db.get_user_orders(message.from_user.id, limit=10)

    if not orders:
        await message.answer("📋 У вас пока нет заявок.\n\nНажмите «💰 Купить криптовалюту» чтобы создать первую заявку.")
        return

    text = "📋 <b>Ваши последние заявки:</b>\n\n"

    for order in orders:
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

        text += (
            f"{status_emoji} <b>Заявка #{order.id}</b>\n"
            f"   Крипта: {order.crypto_type}\n"
            f"   К оплате: {order.amount_rub:,.0f} ₽ → получите {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Статус: {status_text}\n"
            f"   Дата: {order.created_at[:16] if order.created_at else 'N/A'}\n\n"
        )

    await message.answer(text, parse_mode="HTML")