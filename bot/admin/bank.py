# bot/admin/bank.py
"""Обработчики админ-панели для управления банковскими реквизитами."""

import logging
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_bank_menu")
async def admin_bank_menu(callback: CallbackQuery):
    """Меню управления банковскими реквизитами."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа к меню банковских реквизитов без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Открыто меню банковских реквизитов")
    details = await db.get_all_bank_details()

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Добавить карту", callback_data="admin_bank_add")
    keyboard.button(text="📋 Список карт", callback_data="admin_bank_list_0")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    active_count = sum(1 for d in details if d.is_active)
    logger.debug(f"Всего карт: {len(details)}, активных: {active_count}")

    await callback.message.edit_text(
        f"💳 <b>Управление реквизитами</b>\n\n"
        f"Всего карт: {len(details)}\n"
        f"Активных: {active_count}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_bank_add")
async def admin_bank_add_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления новой банковской карты."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Начало добавления банковской карты")
    await state.set_state(AdminStates.adding_bank_card)

    await callback.message.edit_text(
        "💳 <b>Добавление банковской карты</b>\n\n"
        "Введите номер карты:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.adding_bank_card)
async def admin_bank_name(message: Message, state: FSMContext):
    """Обработка введённого номера карты, запрос названия банка."""
    admin_id = message.from_user.id
    card_number = message.text.strip().replace(" ", "")

    logger.info(f"[ADMIN {admin_id}] Ввод номера карты: {card_number[:4]}...{card_number[-4:]}")
    if not card_number.isdigit() or len(card_number) < 16:
        logger.warning(f"[ADMIN {admin_id}] Некорректный номер карты: {card_number}")
        await message.answer("❌ Введите корректный номер карты (16 цифр):")
        return

    await state.update_data(bank_card=card_number)
    await state.set_state(AdminStates.adding_bank_name)
    await message.answer("Введите название банка (например: Сбербанк):")


@router.message(AdminStates.adding_bank_name)
async def admin_bank_holder(message: Message, state: FSMContext):
    """Обработка названия банка, запрос ФИО держателя."""
    admin_id = message.from_user.id
    bank_name = message.text.strip()

    logger.info(f"[ADMIN {admin_id}] Ввод названия банка: {bank_name}")
    await state.update_data(bank_name=bank_name)
    await state.set_state(AdminStates.adding_bank_holder)
    await message.answer("Введите ФИО держателя карты:")


@router.message(AdminStates.adding_bank_holder)
async def admin_bank_limit(message: Message, state: FSMContext):
    """Обработка ФИО, запрос дневного лимита."""
    admin_id = message.from_user.id
    holder_name = message.text.strip()

    logger.info(f"[ADMIN {admin_id}] Ввод ФИО держателя: {holder_name}")
    await state.update_data(bank_holder=holder_name)
    await state.set_state(AdminStates.adding_bank_limit)
    await message.answer("Введите дневной лимит в рублях (например: 1000000):")


@router.message(AdminStates.adding_bank_limit)
async def admin_bank_finish(message: Message, state: FSMContext):
    """Обработка дневного лимита и сохранение карты в БД."""
    admin_id = message.from_user.id
    try:
        limit = float(message.text.replace(" ", "").replace(",", "."))
        logger.info(f"[ADMIN {admin_id}] Ввод дневного лимита: {limit}")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод лимита: {message.text}")
        await message.answer("❌ Пожалуйста, введите корректное число:")
        return

    data = await state.get_data()
    logger.info(f"[ADMIN {admin_id}] Сохранение банковских реквизитов в БД")

    try:
        details_id = await db.add_bank_details(
            card_number=data['bank_card'],
            bank_name=data['bank_name'],
            holder_name=data['bank_holder'],
            daily_limit=limit,
            added_by=admin_id
        )
        logger.info(f"[ADMIN {admin_id}] Банковские реквизиты добавлены, ID: {details_id}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при добавлении банковских реквизитов: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении данных. Попробуйте позже.")
        await state.clear()
        return

    safe_card = html.escape(data['bank_card'])
    safe_holder = html.escape(data['bank_holder'])

    await message.answer(
        f"✅ Карта добавлена!\n\n"
        f"Банк: {data['bank_name']}\n"
        f"Карта: <code>{safe_card}</code>\n"
        f"Держатель: {safe_holder}\n"
        f"Лимит: {limit:,.0f} ₽/день",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К реквизитам", callback_data="admin_bank_menu").as_markup(),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data.startswith("admin_bank_list"))
async def admin_bank_list(callback: CallbackQuery):
    """Показывает список банковских карт с пагинацией."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split("_")
    offset = int(parts[-1]) if parts[-1].isdigit() else 0
    limit = 5
    logger.info(f"[ADMIN {admin_id}] Запрос списка банковских карт (offset={offset}, limit={limit})")

    try:
        details = await db.get_all_bank_details()
        total = len(details)
        paginated = details[offset:offset+limit]
        logger.debug(f"Всего карт: {total}, показано: {len(paginated)}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка банковских карт: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not paginated:
        await callback.message.edit_text(
            "📭 Список карт пуст.\n\nДобавьте карту через меню.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_bank_menu").as_markup()
        )
        await callback.answer()
        return

    text = "💳 <b>Список банковских карт:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for d in paginated:
        status = "✅" if d.is_active else "❌"
        default = " (по умолчанию)" if d.is_default else ""
        masked = f"{d.card_number[:4]} **** **** {d.card_number[-4:]}"
        safe_holder = html.escape(d.holder_name)
        text += (
            f"{status} <b>{d.bank_name}</b>{default}\n"
            f"   Карта: <code>{masked}</code>\n"
            f"   Держатель: {safe_holder}\n"
            f"   Лимит: {d.daily_limit:,.0f} ₽/день\n"
            f"   Использовано сегодня: {d.daily_used:,.0f} ₽\n"
            f"   Добавлена: {d.created_at[:10]}\n\n"
        )
        keyboard.button(text=f"❌ Удалить {d.bank_name}", callback_data=f"admin_bank_delete_{d.id}")

    # Кнопки пагинации
    if offset > 0:
        keyboard.button(text="◀️ Назад", callback_data=f"admin_bank_list_{offset-limit}")
    if offset + limit < total:
        keyboard.button(text="Вперёд ▶️", callback_data=f"admin_bank_list_{offset+limit}")

    keyboard.button(text="🔙 Назад", callback_data="admin_bank_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bank_delete_"))
async def admin_bank_delete_confirm(callback: CallbackQuery):
    """Подтверждение удаления карты."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        card_id = int(callback.data.split("_")[-1])
        logger.info(f"[ADMIN {admin_id}] Запрос на удаление карты ID {card_id}")
    except (IndexError, ValueError):
        logger.warning(f"[ADMIN {admin_id}] Некорректный формат данных для удаления: {callback.data}")
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    try:
        details = await db.get_all_bank_details()
        card = next((d for d in details if d.id == card_id), None)
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении данных карты: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not card:
        logger.warning(f"[ADMIN {admin_id}] Карта ID {card_id} не найдена")
        await callback.answer("❌ Карта не найдена", show_alert=True)
        return

    masked = f"{card.card_number[:4]} **** **** {card.card_number[-4:]}"
    safe_holder = html.escape(card.holder_name)
    text = (
        f"🗑 <b>Подтверждение удаления</b>\n\n"
        f"Вы действительно хотите удалить карту?\n"
        f"Банк: {card.bank_name}\n"
        f"Карта: {masked}\n"
        f"Держатель: {safe_holder}\n\n"
        f"Это действие нельзя отменить."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить", callback_data=f"admin_bank_delete_execute_{card.id}")
    keyboard.button(text="❌ Отмена", callback_data="admin_bank_menu")
    keyboard.adjust(2)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_bank_delete_execute_"))
async def admin_bank_delete_execute(callback: CallbackQuery):
    """Исполнение удаления карты."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        card_id = int(callback.data.split("_")[-1])
        logger.info(f"[ADMIN {admin_id}] Подтверждено удаление карты ID {card_id}")
    except (IndexError, ValueError):
        logger.warning(f"[ADMIN {admin_id}] Некорректный формат данных: {callback.data}")
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    try:
        success = await db.delete_bank_details(card_id)
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при удалении карты ID {card_id}: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при удалении", show_alert=True)
        return

    if success:
        logger.info(f"[ADMIN {admin_id}] Карта ID {card_id} успешно удалена")
        await callback.answer("✅ Карта удалена", show_alert=True)
        await admin_bank_list(callback)
    else:
        logger.warning(f"[ADMIN {admin_id}] Не удалось удалить карту ID {card_id}")
        await callback.answer("❌ Ошибка при удалении", show_alert=True)