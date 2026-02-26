# bot/admin/admins.py
"""Управление администраторами: добавление и удаление."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()


class AdminManagementStates(StatesGroup):
    waiting_for_user_id_to_add = State()
    waiting_for_user_id_to_remove = State()


async def get_all_admins():
    """Возвращает список всех администраторов (из БД и из .env)."""
    env_admins = set(config.ADMIN_IDS)
    db_admins = set()
    async with db._connection.conn.execute("SELECT user_id FROM admins") as cursor:
        rows = await cursor.fetchall()
        for row in rows:
            db_admins.add(row[0])
    return {
        'env': sorted(env_admins),
        'db': sorted(db_admins),
        'all': sorted(env_admins | db_admins)
    }


def admins_keyboard(admins_list: list, action: str = "remove") -> InlineKeyboardBuilder:
    """Создаёт клавиатуру со списком админов для удаления."""
    kb = InlineKeyboardBuilder()
    for uid in admins_list:
        # Пытаемся получить username
        async def get_username():
            user = await db.get_user(uid)
            return f"@{user.username}" if user and user.username else str(uid)
        # Но для простоты покажем просто ID
        kb.button(text=f"❌ {uid}", callback_data=f"admin_remove_{uid}")
    kb.button(text="🔙 Назад", callback_data="admin_manage_admins")
    kb.adjust(1)
    return kb


@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins_menu(callback: CallbackQuery):
    """Главное меню управления администраторами."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    admins = await get_all_admins()
    text = (
        f"👑 <b>Управление администраторами</b>\n\n"
        f"🔹 Суперадмины (из .env):\n"
    )
    for uid in admins['env']:
        text += f"   • {uid}\n"
    text += f"\n🔸 Админы (из БД):\n"
    for uid in admins['db']:
        text += f"   • {uid}\n"
    text += f"\nВсего администраторов: {len(admins['all'])}"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Добавить администратора", callback_data="admin_add_admin")
    if admins['db']:
        keyboard.button(text="❌ Удалить администратора", callback_data="admin_remove_admin")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления администратора (запрос ID)."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminManagementStates.waiting_for_user_id_to_add)
    await callback.message.edit_text(
        "➕ <b>Добавление администратора</b>\n\n"
        "Введите ID пользователя (целое число), которого хотите назначить администратором:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminManagementStates.waiting_for_user_id_to_add)
async def admin_add_admin_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await is_admin(admin_id):
        await message.answer("⛔ Нет доступа.")
        await state.clear()
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
        return

    # Проверяем, существует ли пользователь в таблице users
    user = await db.get_user(target_id)
    if not user:
        await message.answer("❌ Пользователь с таким ID не найден в базе данных.")
        return

    # Проверяем, не является ли он уже админом (в БД или .env)
    if target_id in config.ADMIN_IDS:
        await message.answer("❌ Этот пользователь уже является суперадмином (указан в .env).")
        return

    async with db._connection.conn.execute(
        "SELECT 1 FROM admins WHERE user_id = ?", (target_id,)
    ) as cursor:
        if await cursor.fetchone():
            await message.answer("❌ Этот пользователь уже является администратором в БД.")
            return

    # Добавляем в таблицу admins
    await db._connection.conn.execute(
        "INSERT INTO admins (user_id, added_by) VALUES (?, ?)",
        (target_id, admin_id)
    )
    await db._connection.conn.commit()

    # Уведомляем нового админа (если бот может ему написать)
    try:
        await message.bot.send_message(
            target_id,
            f"✅ Вы были назначены администратором бота пользователем {admin_id}.\n"
            f"Теперь у вас есть доступ к админ-панели по команде /admin."
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить нового админа {target_id}: {e}")

    await message.answer(f"✅ Пользователь {target_id} успешно назначен администратором.")
    await state.clear()
    # Возвращаемся в меню управления админами
    await admin_manage_admins_menu(await simulate_callback(message.from_user.id, message.bot))


@router.callback_query(F.data == "admin_remove_admin")
async def admin_remove_admin_start(callback: CallbackQuery):
    """Показывает список администраторов из БД для удаления."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    admins = await get_all_admins()
    if not admins['db']:
        await callback.answer("Нет администраторов в БД для удаления.", show_alert=True)
        return

    text = "❌ <b>Выберите администратора для удаления:</b>\n\n"
    kb = InlineKeyboardBuilder()
    for uid in admins['db']:
        # Можно показать username, но для простоты ID
        kb.button(text=f"❌ {uid}", callback_data=f"admin_remove_{uid}")
    kb.button(text="🔙 Назад", callback_data="admin_manage_admins")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_remove_"))
async def admin_remove_admin_execute(callback: CallbackQuery):
    """Удаляет администратора из БД."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        target_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка формата данных.", show_alert=True)
        return

    # Нельзя удалить самого себя?
    if target_id == callback.from_user.id:
        await callback.answer("❌ Вы не можете удалить самого себя.", show_alert=True)
        return

    # Удаляем из таблицы admins
    await db._connection.conn.execute(
        "DELETE FROM admins WHERE user_id = ?", (target_id,)
    )
    await db._connection.conn.commit()

    await callback.answer(f"✅ Администратор {target_id} удалён.", show_alert=True)
    # Возвращаемся в меню управления
    await admin_manage_admins_menu(callback)


# Вспомогательная функция для имитации callback (используется выше)
async def simulate_callback(user_id, bot):
    from aiogram.types import CallbackQuery, User, Message
    user = User(id=user_id, is_bot=False, first_name="Admin")
    msg = Message(message_id=0, date=None, chat=None, from_user=user)
    return CallbackQuery(id="0", from_user=user, message=msg, data="admin_manage_admins", chat_instance="0")