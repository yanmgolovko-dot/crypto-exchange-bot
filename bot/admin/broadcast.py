# bot/admin/broadcast.py
"""Рассылка сообщений всем пользователям."""

import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin

logger = logging.getLogger(__name__)
router = Router()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()   # ожидание текста рассылки
    confirming = State()              # подтверждение


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщения</b>\n\n"
        "Введите текст сообщения, которое будет отправлено всем пользователям.\n"
        "Поддерживается HTML-разметка.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(BroadcastStates.waiting_for_message)
async def broadcast_message_received(message: Message, state: FSMContext):
    text = message.text
    await state.update_data(broadcast_text=text)
    await state.set_state(BroadcastStates.confirming)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="broadcast_confirm")
    kb.button(text="❌ Отмена", callback_data="broadcast_cancel")
    kb.adjust(2)

    await message.answer(
        f"📢 Проверьте текст рассылки:\n\n{text}\n\nОтправляем?",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "broadcast_confirm", BroadcastStates.confirming)
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    admin_id = callback.from_user.id
    data = await state.get_data()
    text = data.get('broadcast_text')

    await callback.message.edit_text("⏳ Начинаю рассылку...")

    # Получаем всех пользователей (кроме забаненных, если нужно)
    users = await db.get_all_users()
    # Можно исключить забаненных:
    # users = [u for u in users if not u.is_banned]
    total = len(users)
    success = 0
    failed = 0

    for user in users:
        try:
            await bot.send_message(user.user_id, text, parse_mode="HTML")
            success += 1
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user.user_id}: {e}")
            failed += 1
        await asyncio.sleep(0.05)  # небольшая задержка, чтобы не флудить

    await callback.message.edit_text(
        f"✅ Рассылка завершена.\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}\n"
        f"Всего: {total}"
    )
    await state.clear()


@router.callback_query(F.data == "broadcast_cancel", BroadcastStates.confirming)
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()