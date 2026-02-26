# bot/admin/tickets.py
"""Админ-панель для управления тикетами с возможностью запроса файлов."""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.ticket_service import ticket_service
from bot.admin.main import is_admin, notify_admins
from bot.config.settings import config
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


class AdminTicketStates(StatesGroup):
    replying_to_ticket = State()      # ответ администратора
    requesting_file = State()          # запрос файла у пользователя (ожидание сообщения с запросом)


def admin_tickets_keyboard(tickets: list, page: int = 0, per_page: int = 5):
    kb = InlineKeyboardBuilder()
    start = page * per_page
    for ticket in tickets[start:start+per_page]:
        status_emoji = "🟢" if ticket.status == 'open' else "🔴"
        kb.button(
            text=f"{status_emoji} #{ticket.id} {ticket.subject or 'Без темы'}",
            callback_data=f"admin_ticket_view_{ticket.id}"
        )
    if page > 0:
        kb.button(text="◀️ Назад", callback_data=f"admin_tickets_page_{page-1}")
    if start + per_page < len(tickets):
        kb.button(text="Вперёд ▶️", callback_data=f"admin_tickets_page_{page+1}")
    kb.button(text="🔙 В админку", callback_data="admin_back_main")
    kb.adjust(1)
    return kb.as_markup()


def admin_ticket_control_keyboard(ticket_id: int) -> InlineKeyboardBuilder:
    """Клавиатура для управления тикетом (админ)."""
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Ответить", callback_data=f"admin_ticket_reply_{ticket_id}")
    kb.button(text="📎 Запросить файл", callback_data=f"admin_ticket_request_file_{ticket_id}")
    kb.button(text="🔒 Закрыть", callback_data=f"admin_ticket_close_{ticket_id}")
    kb.button(text="🔙 Назад", callback_data="admin_tickets_menu")
    kb.adjust(1)
    return kb.as_markup()


# Главное меню тикетов для админа
@router.callback_query(F.data == "admin_tickets_menu")
async def admin_tickets_menu(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    tickets = await ticket_service.get_open_tickets()
    text = f"📋 <b>Открытые тикеты</b> (всего: {len(tickets)})\n\n"
    kb = admin_tickets_keyboard(tickets)
    await safe_edit_message(callback.message, text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# Пагинация
@router.callback_query(F.data.startswith("admin_tickets_page_"))
async def admin_tickets_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[3])
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    tickets = await ticket_service.get_open_tickets()
    text = f"📋 <b>Открытые тикеты</b> (всего: {len(tickets)})\n\n"
    kb = admin_tickets_keyboard(tickets, page)
    await safe_edit_message(callback.message, text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# Просмотр конкретного тикета (админ)
@router.callback_query(F.data.startswith("admin_ticket_view_"))
async def admin_ticket_view(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[3])
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("❌ Тикет не найден", show_alert=True)
        return

    messages = await ticket_service.get_messages(ticket_id)
    text = f"📋 <b>Тикет #{ticket_id}</b> ({'🟢 открыт' if ticket.status == 'open' else '🔴 закрыт'})\n\n"
    if ticket.subject:
        text += f"Тема: {escape_html(ticket.subject)}\n\n"

    for msg in messages:
        sender = "👤 Пользователь" if not msg.is_admin else "🛠 Вы (админ)"
        time_str = msg.created_at[:16] if msg.created_at else ""
        file_info = " 📎 (файл)" if msg.file_path else ""
        text += f"{sender} [{time_str}]:{file_info}\n{escape_html(msg.message)}\n\n"

    kb = admin_ticket_control_keyboard(ticket_id) if ticket.status == 'open' else None
    await safe_edit_message(callback.message, text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# Ответ админа
@router.callback_query(F.data.startswith("admin_ticket_reply_"))
async def admin_ticket_reply_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[3])
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.status != 'open':
        await callback.answer("❌ Тикет закрыт или не найден", show_alert=True)
        return

    await state.set_state(AdminTicketStates.replying_to_ticket)
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.answer("✏️ Введите ваш ответ:")
    await callback.answer()


@router.message(AdminTicketStates.replying_to_ticket)
async def admin_ticket_reply_message(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data.get('reply_ticket_id')
    admin_id = message.from_user.id

    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ Тикет не найден.")
        await state.clear()
        return

    # Сохраняем сообщение
    await ticket_service.add_message(ticket_id, admin_id, True, message.text)

    # Уведомляем пользователя с кнопкой ответа
    try:
        user_kb = InlineKeyboardBuilder()
        user_kb.button(text="💬 Ответить", callback_data=f"ticket_reply_{ticket_id}")
        await bot.send_message(
            ticket.user_id,
            f"💬 <b>Новый ответ от администратора по тикету #{ticket_id}</b>\n\n{escape_html(message.text)}",
            reply_markup=user_kb.as_markup(),
            parse_mode="HTML"
        )
        logger.info(f"Уведомление пользователю {ticket.user_id} о новом ответе в тикете #{ticket_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {ticket.user_id}: {e}")

    await message.answer("✅ Ответ отправлен пользователю.")
    await state.clear()


# Запрос файла у пользователя
@router.callback_query(F.data.startswith("admin_ticket_request_file_"))
async def admin_ticket_request_file_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[4])
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.status != 'open':
        await callback.answer("❌ Тикет закрыт или не найден", show_alert=True)
        return

    await state.set_state(AdminTicketStates.requesting_file)
    await state.update_data(request_ticket_id=ticket_id)
    await callback.message.answer(
        "📎 Введите сообщение для пользователя с просьбой прислать файл (PDF или скриншот):"
    )
    await callback.answer()


@router.message(AdminTicketStates.requesting_file)
async def admin_ticket_request_file_message(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ticket_id = data.get('request_ticket_id')
    admin_id = message.from_user.id
    request_text = message.text

    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ Тикет не найден.")
        await state.clear()
        return

    # Сохраняем запрос как обычное сообщение от админа
    await ticket_service.add_message(ticket_id, admin_id, True, request_text)

    # Уведомляем пользователя с кнопкой для отправки файла
    try:
        user_kb = InlineKeyboardBuilder()
        user_kb.button(text="📎 Отправить файл", callback_data=f"ticket_reply_{ticket_id}")
        await bot.send_message(
            ticket.user_id,
            f"📎 <b>Запрос файла от администратора по тикету #{ticket_id}</b>\n\n{escape_html(request_text)}\n\nНажмите кнопку ниже, чтобы ответить и прикрепить файл.",
            reply_markup=user_kb.as_markup(),
            parse_mode="HTML"
        )
        logger.info(f"Запрос файла отправлен пользователю {ticket.user_id} по тикету #{ticket_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {ticket.user_id}: {e}")

    await message.answer("✅ Запрос файла отправлен пользователю.")
    await state.clear()


# Закрытие тикета админом
@router.callback_query(F.data.startswith("admin_ticket_close_"))
async def admin_ticket_close(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[3])
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        await callback.answer("❌ Тикет не найден", show_alert=True)
        return

    await ticket_service.close_ticket(ticket_id, admin_id)

    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            ticket.user_id,
            f"🔒 Ваш тикет #{ticket_id} закрыт администратором. Спасибо за обращение!",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {ticket.user_id}: {e}")

    await callback.answer("✅ Тикет закрыт.")
    await admin_tickets_menu(callback)