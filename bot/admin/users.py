# bot/admin/users.py
"""
Обработчики админ-панели для управления пользователями.
Позволяют просматривать список пользователей, искать, банить и разбанивать.
"""

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
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_users_menu")
async def admin_users_menu(callback: CallbackQuery):
    """Главное меню управления пользователями."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа к меню пользователей без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Открыто меню управления пользователями")
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👥 Все пользователи", callback_data="admin_users_all_0")
    keyboard.button(text="🔍 Найти пользователя", callback_data="admin_user_search")
    keyboard.button(text="🚫 Забанить по ID", callback_data="admin_user_ban")
    keyboard.button(text="✅ Разбанить по ID", callback_data="admin_user_unban")
    keyboard.button(text="📋 Список забаненных", callback_data="admin_user_banned_list_0")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    text = "👥 <b>Управление пользователями</b>\n\nВыберите действие:"
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_all"))
async def admin_users_all(callback: CallbackQuery, admin_user_service: AdminUserService):
    """Показывает список всех пользователей с пагинацией."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    offset = int(parts[-1]) if parts[-1].isdigit() else 0
    limit = 5
    logger.info(f"[ADMIN {admin_id}] Запрос списка пользователей (offset={offset}, limit={limit})")

    try:
        result = await admin_user_service.get_all_users_paginated(offset, limit)
        users = result['users']
        total = result['total']
        logger.debug(f"[ADMIN {admin_id}] Получено {len(users)} пользователей, всего {total}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка пользователей: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not users:
        text = "📭 Список пользователей пуст."
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔙 Назад", callback_data="admin_users_menu")
        await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup())
        await callback.answer()
        return

    text = "👥 <b>Все пользователи:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for user in users:
        stats = await admin_user_service.db.get_user_stats(user.user_id)
        spent = stats['total_volume']
        status = "🚫" if user.is_banned else "✅"
        safe_name = escape_html(user.username or user.first_name or str(user.user_id))
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

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_user_search")
async def admin_user_search_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска пользователя по ID или username."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос поиска пользователя")
    await state.set_state(AdminStates.searching_user)
    text = "🔍 <b>Поиск пользователя</b>\n\nВведите ID пользователя или @username:"
    await safe_edit_message(callback.message, text, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.searching_user)
async def admin_user_search_result(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    """Обработка введённого ID или username и отображение результата."""
    admin_id = message.from_user.id
    user_input = message.text.strip()
    logger.info(f"[ADMIN {admin_id}] Поиск пользователя: {user_input}")

    try:
        if user_input.startswith("@"):
            username = user_input[1:]
            user = await admin_user_service.find_user_by_username(username)
            if not user:
                logger.info(f"[ADMIN {admin_id}] Пользователь с username {username} не найден")
                await message.answer("❌ Пользователь с таким username не найден.")
                await state.clear()
                return
            user_id = user.user_id
        else:
            try:
                user_id = int(user_input)
            except ValueError:
                logger.warning(f"[ADMIN {admin_id}] Некорректный ввод ID: {user_input}")
                await message.answer("❌ Введите корректный числовой ID.")
                return
            user_info = await admin_user_service.get_user_info(user_id)
            if not user_info:
                logger.info(f"[ADMIN {admin_id}] Пользователь с ID {user_id} не найден")
                await message.answer("❌ Пользователь с таким ID не найден.")
                await state.clear()
                return
            user = user_info['user']
            stats = user_info['stats']

        text = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"ID: <code>{user.user_id}</code>\n"
            f"Username: @{escape_html(user.username) if user.username else 'Нет'}\n"
            f"Имя: {escape_html(user.first_name or 'Нет')}\n"
            f"Фамилия: {escape_html(user.last_name or 'Нет')}\n"
            f"Дата регистрации: {user.created_at[:10]}\n"
            f"Всего обменов: {stats['total_orders']}\n"
            f"Общий объём: {stats['total_volume']:,.0f} ₽\n"
            f"Статус: {'🚫 Забанен' if user.is_banned else '✅ Активен'}\n"
        )
        if user.is_banned and user.ban_reason:
            text += f"Причина бана: {escape_html(user.ban_reason)}\n"

        keyboard = InlineKeyboardBuilder()
        if user.is_banned:
            keyboard.button(text="✅ Разбанить", callback_data=f"admin_unban_from_list_{user.user_id}")
        else:
            keyboard.button(text="🚫 Забанить", callback_data=f"admin_ban_from_list_{user.user_id}")
        keyboard.button(text="🔙 К управлению", callback_data="admin_users_menu")
        keyboard.adjust(1)

        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
        logger.info(f"[ADMIN {admin_id}] Информация о пользователе {user_id} отправлена")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при поиске пользователя: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при поиске.")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("admin_ban_from_list_"))
async def admin_ban_from_list(callback: CallbackQuery, state: FSMContext, admin_user_service: AdminUserService):
    """Обработка нажатия на кнопку "Забанить" в списке пользователей."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[4])
    logger.info(f"[ADMIN {admin_id}] Запрос на бан пользователя {user_id} из списка")

    user_info = await admin_user_service.get_user_info(user_id)
    if not user_info:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    if user_info['user'].is_banned:
        await callback.answer("❌ Пользователь уже забанен", show_alert=True)
        return

    await state.update_data(ban_user_id=user_id)
    await state.set_state(AdminStates.banning_reason)
    await callback.message.answer(f"🚫 Введите причину бана для пользователя {user_id}:")
    await callback.answer()


@router.callback_query(F.data == "admin_user_ban")
async def admin_user_ban_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса бана по ID (ручной ввод)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос на бан пользователя (ручной ввод)")
    await state.set_state(AdminStates.banning_user)
    text = "🚫 <b>Бан пользователя</b>\n\nВведите ID пользователя или @username:"
    await safe_edit_message(callback.message, text, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.banning_user)
async def admin_user_ban_reason(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    """Обработка введённого ID/username для бана. Переход к вводу причины."""
    admin_id = message.from_user.id
    user_input = message.text.strip()
    logger.info(f"[ADMIN {admin_id}] Бан пользователя: {user_input}")

    try:
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
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при бане: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка.")


@router.message(AdminStates.banning_reason)
async def admin_user_ban_finish(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    """Финализация бана: сохранение причины и выполнение бана."""
    admin_id = message.from_user.id
    data = await state.get_data()
    user_id = data.get('ban_user_id')
    reason = message.text

    logger.info(f"[ADMIN {admin_id}] Бан пользователя {user_id} с причиной: {reason}")

    try:
        await admin_user_service.ban_user(user_id, reason, admin_id)
        safe_reason = escape_html(reason)
        text = f"✅ Пользователь {user_id} забанен.\nПричина: {safe_reason}"
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔙 К пользователям", callback_data="admin_users_menu")
        await message.answer(text, reply_markup=keyboard.as_markup())
        logger.info(f"[ADMIN {admin_id}] Пользователь {user_id} успешно забанен")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при бане пользователя {user_id}: {e}", exc_info=True)
        await message.answer("❌ Не удалось забанить пользователя.")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("admin_unban_from_list_"))
async def admin_unban_from_list(callback: CallbackQuery, admin_user_service: AdminUserService):
    """Разбан пользователя по кнопке из списка."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    user_id = int(callback.data.split("_")[4])
    logger.info(f"[ADMIN {admin_id}] Запрос на разбан пользователя {user_id}")

    try:
        user_info = await admin_user_service.get_user_info(user_id)
        if not user_info:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        if not user_info['user'].is_banned:
            await callback.answer("❌ Пользователь не забанен", show_alert=True)
            return

        await admin_user_service.unban_user(user_id)
        await callback.answer(f"✅ Пользователь {user_id} разбанен", show_alert=True)
        logger.info(f"[ADMIN {admin_id}] Пользователь {user_id} разбанен")
        # Возвращаемся к списку (обновляем)
        await admin_users_all(callback, admin_user_service)
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при разбане пользователя {user_id}: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при разбане", show_alert=True)


@router.callback_query(F.data == "admin_user_unban")
async def admin_user_unban_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса разбана по ID (ручной ввод)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос на разбан пользователя (ручной ввод)")
    await state.set_state(AdminStates.unbanning_user)
    text = "✅ <b>Разбан пользователя</b>\n\nВведите ID пользователя:"
    await safe_edit_message(callback.message, text, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.unbanning_user)
async def admin_user_unban_execute(message: Message, state: FSMContext, admin_user_service: AdminUserService):
    """Выполнение разбана по введённому ID."""
    admin_id = message.from_user.id
    try:
        user_id = int(message.text.strip())
        logger.info(f"[ADMIN {admin_id}] Разбан пользователя {user_id}")

        user_info = await admin_user_service.get_user_info(user_id)
        if not user_info:
            await message.answer("❌ Пользователь не найден.")
        elif not user_info['user'].is_banned:
            await message.answer("❌ Пользователь не забанен.")
        else:
            await admin_user_service.unban_user(user_id)
            text = f"✅ Пользователь {user_id} разбанен."
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="🔙 К пользователям", callback_data="admin_users_menu")
            await message.answer(text, reply_markup=keyboard.as_markup())
            logger.info(f"[ADMIN {admin_id}] Пользователь {user_id} разбанен")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод ID: {message.text}")
        await message.answer("❌ Введите корректный числовой ID.")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при разбане: {e}", exc_info=True)
        await message.answer("❌ Ошибка при разбане.")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("admin_user_banned_list"))
async def admin_user_banned_list(callback: CallbackQuery, admin_user_service: AdminUserService):
    """Показывает список забаненных пользователей с пагинацией."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    offset = int(parts[-1]) if parts[-1].isdigit() else 0
    limit = 5
    logger.info(f"[ADMIN {admin_id}] Запрос списка забаненных (offset={offset}, limit={limit})")

    try:
        result = await admin_user_service.get_banned_users_paginated(offset, limit)
        users = result['users']
        total = result['total']
        logger.debug(f"[ADMIN {admin_id}] Получено {len(users)} забаненных, всего {total}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка забаненных: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not users:
        text = "📭 Нет забаненных пользователей."
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔙 Назад", callback_data="admin_users_menu")
        await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup())
        await callback.answer()
        return

    text = "🚫 <b>Забаненные пользователи:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for user in users:
        safe_name = escape_html(user.username or user.first_name or str(user.user_id))
        safe_reason = escape_html(user.ban_reason) if user.ban_reason else 'Без причины'
        text += f"• {safe_name} (ID: {user.user_id}) – {safe_reason}\n"

    # Пагинация
    if offset > 0:
        keyboard.button(text="◀️ Назад", callback_data=f"admin_user_banned_list_{offset-limit}")
    if offset + limit < total:
        keyboard.button(text="Вперёд ▶️", callback_data=f"admin_user_banned_list_{offset+limit}")

    keyboard.button(text="🔙 Назад", callback_data="admin_users_menu")
    keyboard.adjust(1)

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()