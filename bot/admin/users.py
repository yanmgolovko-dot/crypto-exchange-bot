"""Обработчики админ-панели для управления пользователями"""

import logging
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.admin_user_service import AdminUserService
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👥 Все пользователи", callback_data="admin_users_all_0")
    keyboard.button(text="🔍 Найти пользователя", callback_data="admin_user_search")
    keyboard.button(text="🚫 Забанить по ID", callback_data="admin_user_ban")
    keyboard.button(text="✅ Разбанить по ID", callback_data="admin_user_unban")
    keyboard.button(text="📋 Список забаненных", callback_data="admin_user_banned_list_0")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>\n\nВыберите действие:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_all"))
async def admin_users_all(callback: CallbackQuery, admin_user_service: AdminUserService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    offset = int(parts[-1]) if parts[-1].isdigit() else 0
    limit = 5

    result = await admin_user_service.get_all_users_paginated(offset, limit)
    users = result['users']
    total = result['total']

    if not users:
        await callback.message.edit_text(
            "📭 Список пользователей пуст.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_users_menu").as_markup()
        )
        await callback.answer()
        return

    text = "👥 <b>Все пользователи:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for user in users:
        stats = await admin_user_service.db.get_user_stats(user.user_id)
        spent = stats['total_volume']
        status = "🚫" if user.is_banned else "✅"
        safe_name = html.escape(user.username or user.first_name or str(user.user_id))
        if len(safe_name) > 20:
            safe_name = safe_name[:17] + "..."

        text += f"{status} <b>{safe_name}</b> (ID: {user.user_id}) – {spent:,.0f} ₽\n"

        if user.is_banned:
            keyboard.button(text=f"✅ Разбанить {user.user_id}", callback_data=f"admin_unban_from_list_{user.user_id}")
        else:
            keyboard.button(text=f"🚫 Забанить {user.user_id}", callback_data=f"admin_ban_from_list_{user.user_id}")

    # Пагинация
    if offset > 0:
        keyboard.button(text="◀️ Назад", callback_data=f"admin_users_all_{offset-limit}")
    if offset + limit < total:
        keyboard.button(text="Вперёд ▶️", callback_data=f"admin_users_all_{offset+limit}")

    keyboard.button(text="🔙 Назад", callback_data="admin_users_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_user_search")
async def admin_user_search_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.searching_user)
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID пользователя или @username:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.searching_user)
async def admin_user_search_result(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    user_input = message.text.strip()

    if user_input.startswith("@"):
        username = user_input[1:]
        user = await admin_user_service.find_user_by_username(username)
        if not user:
            await message.answer("❌ Пользователь с таким username не найден.")
            await state.clear()
            return
    else:
        try:
            user_id = int(user_input)
        except ValueError:
            await message.answer("❌ Введите корректный числовой ID.")
            return
        user_info = await admin_user_service.get_user_info(user_id)
        if not user_info:
            await message.answer("❌ Пользователь с таким ID не найден.")
            await state.clear()
            return
        user = user_info['user']
        stats = user_info['stats']

    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"ID: <code>{user.user_id}</code>\n"
        f"Username: @{html.escape(user.username) if user.username else 'Нет'}\n"
        f"Имя: {html.escape(user.first_name or 'Нет')}\n"
        f"Фамилия: {html.escape(user.last_name or 'Нет')}\n"
        f"Дата регистрации: {user.created_at[:10]}\n"
        f"Всего обменов: {stats['total_orders']}\n"
        f"Общий объём: {stats['total_volume']:,.0f} ₽\n"
        f"Статус: {'🚫 Забанен' if user.is_banned else '✅ Активен'}\n"
    )
    if user.is_banned and user.ban_reason:
        text += f"Причина бана: {html.escape(user.ban_reason)}\n"

    keyboard = InlineKeyboardBuilder()
    if user.is_banned:
        keyboard.button(text="✅ Разбанить", callback_data=f"admin_unban_from_list_{user.user_id}")
    else:
        keyboard.button(text="🚫 Забанить", callback_data=f"admin_ban_from_list_{user.user_id}")
    keyboard.button(text="🔙 К управлению", callback_data="admin_users_menu")
    keyboard.adjust(1)

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("admin_ban_from_list_"))
async def admin_ban_from_list(callback: CallbackQuery, state: FSMContext, admin_user_service: AdminUserService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[4])
    user_info = await admin_user_service.get_user_info(user_id)
    if not user_info:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    user = user_info['user']

    if user.is_banned:
        await callback.answer("❌ Пользователь уже забанен", show_alert=True)
        return

    await state.update_data(ban_user_id=user_id)
    await state.set_state(AdminStates.banning_reason)

    await callback.message.answer(
        f"🚫 Введите причину бана для пользователя {user_id}:"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_user_ban")
async def admin_user_ban_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.banning_user)
    await callback.message.edit_text(
        "🚫 <b>Бан пользователя</b>\n\n"
        "Введите ID пользователя или @username:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.banning_user)
async def admin_user_ban_reason(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    user_input = message.text.strip()

    if user_input.startswith("@"):
        username = user_input[1:]
        user = await admin_user_service.find_user_by_username(username)
        if not user:
            await message.answer("❌ Пользователь с таким username не найден.")
            return
        user_id = user.user_id
    else:
        try:
            user_id = int(user_input)
        except ValueError:
            await message.answer("❌ Введите корректный числовой ID.")
            return

    user_info = await admin_user_service.get_user_info(user_id)
    if not user_info:
        await message.answer("❌ Пользователь с таким ID не найден.")
        return
    if user_info['user'].is_banned:
        await message.answer("❌ Пользователь уже забанен.")
        return

    await state.update_data(ban_user_id=user_id)
    await state.set_state(AdminStates.banning_reason)
    await message.answer("Введите причину бана:")


@router.message(AdminStates.banning_reason)
async def admin_user_ban_finish(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    data = await state.get_data()
    user_id = data.get('ban_user_id')
    reason = message.text

    await admin_user_service.ban_user(user_id, reason, message.from_user.id)
    safe_reason = html.escape(reason)
    await message.answer(
        f"✅ Пользователь {user_id} забанен.\nПричина: {safe_reason}",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К пользователям", callback_data="admin_users_menu").as_markup()
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_unban_from_list_"))
async def admin_unban_from_list(callback: CallbackQuery, admin_user_service: AdminUserService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[4])
    user_info = await admin_user_service.get_user_info(user_id)
    if not user_info:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    if not user_info['user'].is_banned:
        await callback.answer("❌ Пользователь не забанен", show_alert=True)
        return

    await admin_user_service.unban_user(user_id)
    await callback.answer(f"✅ Пользователь {user_id} разбанен", show_alert=True)
    await admin_users_all(callback)


@router.callback_query(F.data == "admin_user_unban")
async def admin_user_unban_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.unbanning_user)
    await callback.message.edit_text(
        "✅ <b>Разбан пользователя</b>\n\n"
        "Введите ID пользователя:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.unbanning_user)
async def admin_user_unban_execute(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    try:
        user_id = int(message.text.strip())
        user_info = await admin_user_service.get_user_info(user_id)
        if not user_info:
            await message.answer("❌ Пользователь не найден.")
        elif not user_info['user'].is_banned:
            await message.answer("❌ Пользователь не забанен.")
        else:
            await admin_user_service.unban_user(user_id)
            await message.answer(
                f"✅ Пользователь {user_id} разбанен.",
                reply_markup=InlineKeyboardBuilder().button(text="🔙 К пользователям", callback_data="admin_users_menu").as_markup()
            )
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
    await state.clear()


@router.callback_query(F.data.startswith("admin_user_banned_list"))
async def admin_user_banned_list(callback: CallbackQuery, admin_user_service: AdminUserService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    offset = int(parts[-1]) if parts[-1].isdigit() else 0
    limit = 5

    result = await admin_user_service.get_banned_users_paginated(offset, limit)
    users = result['users']
    total = result['total']

    if not users:
        await callback.message.edit_text(
            "📭 Нет забаненных пользователей.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_users_menu").as_markup()
        )
        await callback.answer()
        return

    text = "🚫 <b>Забаненные пользователи:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for user in users:
        safe_name = html.escape(user.username or user.first_name or str(user.user_id))
        safe_reason = html.escape(user.ban_reason) if user.ban_reason else 'Без причины'
        text += f"• {safe_name} (ID: {user.user_id}) – {safe_reason}\n"

    # Пагинация
    if offset > 0:
        keyboard.button(text="◀️ Назад", callback_data=f"admin_user_banned_list_{offset-limit}")
    if offset + limit < total:
        keyboard.button(text="Вперёд ▶️", callback_data=f"admin_user_banned_list_{offset+limit}")

    keyboard.button(text="🔙 Назад", callback_data="admin_users_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()