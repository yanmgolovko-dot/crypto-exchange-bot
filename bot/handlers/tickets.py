# bot/handlers/tickets.py
"""Обработчики для работы с тикетами (поддержка) с непрерывным диалогом и файлами."""

import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.ticket_service import ticket_service
from bot.keyboards import main_menu_keyboard
from bot.admin.main import notify_admins, is_admin
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()


# Состояния FSM
class TicketStates(StatesGroup):
    waiting_for_subject = State()      # ожидание темы при создании
    waiting_for_first_message = State() # ожидание первого сообщения
    in_dialog = State()                 # активный диалог (пользователь в тикете)


# Вспомогательные клавиатуры
def ticket_user_keyboard(ticket_id: int, in_dialog: bool = False) -> InlineKeyboardBuilder:
    """Клавиатура для просмотра тикета. Если in_dialog=True, показываем кнопку выхода."""
    kb = InlineKeyboardBuilder()
    if not in_dialog:
        kb.button(text="💬 Ответить", callback_data=f"ticket_reply_{ticket_id}")
    else:
        kb.button(text="❌ Завершить диалог", callback_data=f"ticket_exit_dialog_{ticket_id}")
    kb.button(text="🔒 Закрыть тикет", callback_data=f"ticket_close_{ticket_id}")
    kb.button(text="🔙 Назад к списку", callback_data="ticket_list")
    kb.adjust(1)
    return kb.as_markup()


def tickets_list_keyboard(tickets: list, page: int = 0, per_page: int = 5) -> InlineKeyboardBuilder:
    """Клавиатура для списка тикетов пользователя."""
    kb = InlineKeyboardBuilder()
    start = page * per_page
    for ticket in tickets[start:start+per_page]:
        status_emoji = "🟢" if ticket.status == 'open' else "🔴"
        kb.button(
            text=f"{status_emoji} #{ticket.id} {ticket.subject or 'Без темы'}",
            callback_data=f"ticket_view_{ticket.id}"
        )
    # Пагинация
    if page > 0:
        kb.button(text="◀️ Назад", callback_data=f"ticket_page_{page-1}")
    if start + per_page < len(tickets):
        kb.button(text="Вперёд ▶️", callback_data=f"ticket_page_{page+1}")
    kb.button(text="➕ Новый тикет", callback_data="ticket_new")
    kb.button(text="🔙 В меню поддержки", callback_data="support_entry")
    kb.adjust(1)
    return kb.as_markup()


# ========== ГЛАВНОЕ МЕНЮ ПОДДЕРЖКИ ==========
@router.message(F.text == "💬 Поддержка")
async def support_entry(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Вход в раздел поддержки")

    # Проверяем, не находится ли пользователь уже в диалоге
    current_state = await state.get_state()
    if current_state == TicketStates.in_dialog.state:
        data = await state.get_data()
        ticket_id = data.get('active_ticket_id')
        if ticket_id:
            # Предложим перейти в текущий диалог
            kb = InlineKeyboardBuilder()
            kb.button(text="💬 Продолжить диалог", callback_data=f"ticket_view_{ticket_id}")
            kb.button(text="📋 Все обращения", callback_data="ticket_list")
            kb.button(text="❌ Завершить диалог", callback_data=f"ticket_exit_dialog_{ticket_id}")
            kb.button(text="🔙 В меню поддержки", callback_data="support_entry")
            kb.adjust(1)
            await message.answer(
                "У вас есть открытый диалог. Что хотите сделать?",
                reply_markup=kb.as_markup()
            )
            return

    # Основное меню поддержки
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Создать новый тикет", callback_data="ticket_new")
    kb.button(text="📋 Мои обращения", callback_data="ticket_list")
    kb.button(text="❓ Часто задаваемые вопросы", callback_data="ticket_faq")
    kb.button(text="🔙 Главное меню", callback_data="ticket_back_main")
    kb.adjust(1)

    await message.answer(
        "💬 <b>Поддержка</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "support_entry")
async def support_entry_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню поддержки (из других разделов)."""
    await callback.message.delete()
    await support_entry(callback.message, state)
    await callback.answer()


# ========== ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ ==========
@router.callback_query(F.data == "ticket_faq")
async def ticket_faq(callback: CallbackQuery):
    text = (
        "❓ <b>Часто задаваемые вопросы</b>\n\n"
        "• <b>Как создать обращение?</b>\n"
        "  Нажмите «Создать новый тикет» и следуйте инструкциям.\n\n"
        "• <b>Как прикрепить файл?</b>\n"
        "  Во время диалога просто отправьте файл (PDF, изображение).\n\n"
        "• <b>Как закрыть тикет?</b>\n"
        "  В просмотре тикета есть кнопка «Закрыть тикет».\n\n"
        "• <b>Как посмотреть историю обращений?</b>\n"
        "  В меню поддержки выберите «Мои обращения».\n\n"
        "• <b>Как продолжить диалог?</b>\n"
        "  Если у вас есть открытый тикет, при входе в поддержку появится предложение продолжить."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="support_entry")
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ========== СОЗДАНИЕ НОВОГО ТИКЕТА ==========
@router.callback_query(F.data == "ticket_new")
async def ticket_new_from_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TicketStates.waiting_for_subject)
    await callback.message.edit_text(
        "💬 Опишите кратко ваш вопрос (тему) или отправьте /skip, чтобы пропустить:"
    )
    await callback.answer()


@router.message(TicketStates.waiting_for_subject)
async def ticket_subject_received(message: Message, state: FSMContext):
    user_id = message.from_user.id
    subject = message.text.strip() if message.text != "/skip" else None
    await state.update_data(subject=subject)
    await state.set_state(TicketStates.waiting_for_first_message)
    await message.answer(
        "✏️ Теперь напишите ваше сообщение подробно. Администратор ответит вам в ближайшее время."
    )


@router.message(TicketStates.waiting_for_first_message)
async def ticket_first_message(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    data = await state.get_data()
    subject = data.get('subject')
    first_msg = message.text

    # Создаём тикет
    ticket_id = await ticket_service.create_ticket(user_id, subject)
    # Добавляем первое сообщение
    await ticket_service.add_message(ticket_id, user_id, False, first_msg)

    # Устанавливаем состояние диалога
    await state.set_state(TicketStates.in_dialog)
    await state.update_data(active_ticket_id=ticket_id)

    await message.answer(
        f"✅ Ваше обращение #{ticket_id} создано. Теперь вы можете просто писать сообщения, они будут отправляться в этот тикет.\n"
        f"Для выхода из диалога используйте /cancel или кнопку «❌ Завершить диалог».",
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Завершить диалог", callback_data=f"ticket_exit_dialog_{ticket_id}"
        ).as_markup()
    )

    # Уведомляем всех админов
    admin_text = (
        f"🆕 <b>Новое обращение #{ticket_id}</b>\n"
        f"Пользователь: @{message.from_user.username or 'N/A'} (ID: {user_id})\n"
        f"Тема: {subject or 'Без темы'}\n\n"
        f"{first_msg}"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Ответить", callback_data=f"admin_ticket_view_{ticket_id}")
    await notify_admins(message.bot, admin_text, reply_markup=kb.as_markup())


# ========== СПИСОК ТИКЕТОВ ==========
@router.callback_query(F.data == "ticket_list")
async def ticket_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    tickets = await ticket_service.get_user_tickets(user_id)
    if not tickets:
        await callback.message.edit_text(
            "📋 У вас пока нет обращений.\n\nХотите создать новое?",
            reply_markup=InlineKeyboardBuilder().button(text="📝 Создать тикет", callback_data="ticket_new").as_markup()
        )
        await callback.answer()
        return
    text = "📋 <b>Ваши обращения в поддержку:</b>\n\n"
    kb = tickets_list_keyboard(tickets)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ========== ПРОСМОТР ТИКЕТА ==========
@router.callback_query(F.data.startswith("ticket_view_"))
async def ticket_view_callback(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[2])
    await show_ticket(callback.message, ticket_id, state, edit=True)
    await callback.answer()


async def show_ticket(message: Message, ticket_id: int, state: FSMContext, edit: bool = False):
    """Отображает содержимое тикета и автоматически переводит пользователя в режим диалога."""
    user_id = message.from_user.id if isinstance(message, Message) else message.chat.id
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.user_id != user_id:
        await message.answer("❌ Тикет не найден или доступ запрещён.")
        return

    # Если тикет открыт, устанавливаем активный диалог
    if ticket.status == 'open':
        await state.set_state(TicketStates.in_dialog)
        await state.update_data(active_ticket_id=ticket_id)
        in_dialog = True
    else:
        in_dialog = False

    messages = await ticket_service.get_messages(ticket_id)
    text = f"📋 <b>Тикет #{ticket_id}</b> ({'🟢 открыт' if ticket.status == 'open' else '🔴 закрыт'})\n\n"
    if ticket.subject:
        text += f"Тема: {ticket.subject}\n\n"

    for msg in messages:
        sender = "👤 Вы" if not msg.is_admin else "🛠 Админ"
        time_str = msg.created_at[:16] if msg.created_at else ""
        file_info = " 📎 (файл)" if msg.file_path else ""
        text += f"{sender} [{time_str}]:{file_info}\n{msg.message}\n\n"

    if edit:
        await message.edit_text(
            text,
            reply_markup=ticket_user_keyboard(ticket_id, in_dialog) if ticket.status == 'open' else None,
            parse_mode="HTML"
        )
    else:
        await message.answer(
            text,
            reply_markup=ticket_user_keyboard(ticket_id, in_dialog) if ticket.status == 'open' else None,
            parse_mode="HTML"
        )


# ========== ВХОД В ДИАЛОГ ПО КНОПКЕ "ОТВЕТИТЬ" (альтернатива) ==========
@router.callback_query(F.data.startswith("ticket_reply_"))
async def ticket_reply_start(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.user_id != user_id:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    if ticket.status != 'open':
        await callback.answer("❌ Тикет уже закрыт", show_alert=True)
        return

    # Устанавливаем состояние диалога
    await state.set_state(TicketStates.in_dialog)
    await state.update_data(active_ticket_id=ticket_id)

    await callback.message.edit_text(
        f"💬 Вы вошли в диалог по тикету #{ticket_id}. Все ваши сообщения будут отправляться сюда.\n"
        "Для выхода используйте /cancel или кнопку ниже.",
        reply_markup=InlineKeyboardBuilder().button(
            text="❌ Завершить диалог", callback_data=f"ticket_exit_dialog_{ticket_id}"
        ).as_markup()
    )
    await callback.answer()


# ========== ВЫХОД ИЗ ДИАЛОГА ==========
@router.callback_query(F.data.startswith("ticket_exit_dialog_"))
async def ticket_exit_dialog(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[3])
    await state.clear()
    await callback.message.edit_text(
        f"✅ Вы вышли из диалога по тикету #{ticket_id}. Чтобы продолжить общение, откройте тикет.",
        reply_markup=InlineKeyboardBuilder().button(
            text="📋 К тикету", callback_data=f"ticket_view_{ticket_id}"
        ).as_markup()
    )
    await callback.answer()


# ========== ОБРАБОТКА СООБЩЕНИЙ В ДИАЛОГЕ ==========
@router.message(TicketStates.in_dialog)
async def handle_dialog_message(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    data = await state.get_data()
    ticket_id = data.get('active_ticket_id')
    if not ticket_id:
        await state.clear()
        await message.answer("❌ Ошибка: не найден активный тикет. Попробуйте начать заново.")
        return

    # Проверяем, что тикет ещё открыт
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.status != 'open':
        await state.clear()
        await message.answer("❌ Тикет уже закрыт. Создайте новое обращение, если нужно.")
        return

    # Определяем, файл или текст
    file_path = None
    content = ""

    if message.document:
        document = message.document
        file = await bot.get_file(document.file_id)
        tickets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticket_files")
        os.makedirs(tickets_dir, exist_ok=True)
        file_path = os.path.join(tickets_dir, f"ticket_{ticket_id}_{document.file_id}_{document.file_name}")
        await bot.download_file(file.file_path, file_path)
        content = f"📎 Отправлен файл: {document.file_name}"
        logger.info(f"Файл сохранён: {file_path}")

    elif message.photo:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        tickets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ticket_files")
        os.makedirs(tickets_dir, exist_ok=True)
        file_path = os.path.join(tickets_dir, f"ticket_{ticket_id}_{photo.file_id}.jpg")
        await bot.download_file(file.file_path, file_path)
        content = "📸 Отправлен скриншот"
        logger.info(f"Фото сохранено: {file_path}")

    elif message.text:
        content = message.text
    else:
        await message.answer("❌ Пожалуйста, отправьте текст, документ (PDF) или изображение.")
        return

    # Сохраняем сообщение
    await ticket_service.add_message(ticket_id, user_id, False, content, file_path)

    # Уведомляем админов
    admin_text = (
        f"💬 <b>Новый ответ пользователя в тикете #{ticket_id}</b>\n\n"
        f"{content}"
    )
    if file_path:
        admin_text += "\n\n(Файл прикреплён)"

    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Ответить", callback_data=f"admin_ticket_view_{ticket_id}")
    await notify_admins(message.bot, admin_text, reply_markup=kb.as_markup())

    # Очищаем состояние после отправки сообщения, чтобы пользователь вышел из диалога
    await state.clear()

    # Отправляем подтверждение пользователю с кнопкой для возврата, если нужно
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="📋 Вернуться к тикету", callback_data=f"ticket_view_{ticket_id}")
    await message.answer(
        "✅ Сообщение отправлено. Вы вышли из режима диалога. Чтобы продолжить, нажмите кнопку ниже.",
        reply_markup=back_kb.as_markup()
    )


# ========== ЗАКРЫТИЕ ТИКЕТА ==========
@router.callback_query(F.data.startswith("ticket_close_"))
async def ticket_close(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket or ticket.user_id != user_id:
        await callback.answer("❌ Доступ запрещён", show_alert=True)
        return
    if ticket.status != 'open':
        await callback.answer("❌ Тикет уже закрыт", show_alert=True)
        return

    await ticket_service.close_ticket(ticket_id, user_id)
    await state.clear()  # выходим из диалога, если были в нём

    await callback.answer("✅ Тикет закрыт.")
    await show_ticket(callback.message, ticket_id, state, edit=True)


# ========== ПАГИНАЦИЯ ==========
@router.callback_query(F.data.startswith("ticket_page_"))
async def ticket_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    tickets = await ticket_service.get_user_tickets(user_id)
    text = "📋 <b>Ваши обращения в поддержку:</b>\n\n"
    kb = tickets_list_keyboard(tickets, page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ========== ВОЗВРАТ В ГЛАВНОЕ МЕНЮ ==========
@router.callback_query(F.data == "ticket_back_main")
async def ticket_back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ========== КОМАНДА /cancel ==========
@router.message(Command("cancel"), StateFilter(TicketStates.in_dialog))
async def cancel_dialog(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get('active_ticket_id')
    await state.clear()
    if ticket_id:
        await message.answer(
            f"✅ Вы вышли из диалога по тикету #{ticket_id}. Чтобы продолжить, откройте тикет.",
            reply_markup=InlineKeyboardBuilder().button(
                text="📋 К тикету", callback_data=f"ticket_view_{ticket_id}"
            ).as_markup()
        )
    else:
        await message.answer("✅ Диалог завершён.")