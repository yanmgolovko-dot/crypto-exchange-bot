# bot/admin/broadcast.py
"""Массовая рассылка сообщений всем пользователям бота."""

import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin, notify_admins
from bot.utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)
router = Router()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()


def broadcast_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="broadcast_confirm")
    kb.button(text="❌ Отмена", callback_data="broadcast_cancel")
    kb.adjust(2)
    return kb.as_markup()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(BroadcastStates.waiting_for_message)
    await safe_edit_message(
        callback.message,
        "📢 <b>Массовая рассылка</b>\n\n"
        "Введите текст сообщения для рассылки всем пользователям.\n"
        "Вы можете использовать HTML-разметку (жирный, курсив, ссылки).",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(BroadcastStates.waiting_for_message)
async def broadcast_message_received(message: Message, state: FSMContext):
    # Сохраняем текст
    await state.update_data(text=message.text, html=message.html_text)
    # Получаем количество пользователей
    users = await db.get_all_users()
    total = len(users)
    await state.update_data(total_users=total)
    # Показываем предпросмотр
    text = (
        f"📢 <b>Предпросмотр рассылки</b>\n\n"
        f"{message.html_text}\n\n"
        f"Будет отправлено <b>{total}</b> пользователям.\n\n"
        f"Подтвердите отправку:"
    )
    await message.answer(text, reply_markup=broadcast_keyboard(), parse_mode="HTML")
    await state.set_state(BroadcastStates.waiting_for_confirmation)


@router.callback_query(BroadcastStates.waiting_for_confirmation, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    admin_id = callback.from_user.id
    data = await state.get_data()
    text = data['text']
    html_text = data['html']
    total = data['total_users']

    await safe_edit_message(callback.message, "🔄 Начинаю рассылку...")
    await callback.answer()

    users = await db.get_all_users()
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user.user_id, html_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # небольшая задержка, чтобы не флудить
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {user.user_id}: {e}")
            failed += 1

    result_text = (
        f"📊 <b>Рассылка завершена</b>\n\n"
        f"✅ Успешно: {sent}\n"
        f"❌ Ошибок: {failed}\n"
        f"Всего: {total}"
    )
    await safe_edit_message(callback.message, result_text, parse_mode="HTML")

    # Уведомляем админов
    await notify_admins(
        bot,
        f"🔔 Администратор {admin_id} провёл рассылку.\n"
        f"Отправлено: {sent}, ошибок: {failed}."
    )
    await state.clear()


@router.callback_query(BroadcastStates.waiting_for_confirmation, F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await safe_edit_message(callback.message, "❌ Рассылка отменена.")
    await callback.answer()
    await state.clear()