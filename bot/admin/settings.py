# bot/admin/settings.py
"""
Обработчики админ-панели для управления настройками бота.
Позволяют изменять комиссию, лимиты, режим оплаты, источник реквизитов и уровень логирования.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.config.settings import config
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_settings_menu")
async def admin_settings_menu(callback: CallbackQuery):
    """
    Отображает главное меню настроек с текущими значениями.
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа к настройкам без прав")
        return

    # Получаем текущие настройки из БД
    fee = await db.get_exchange_fee()
    min_amount = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    max_amount = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    payment_mode = await db.get_payment_mode()
    mode_text = "Автоматический" if payment_mode == 'auto' else "Ручной"
    payment_source = await db.get_manual_payment_source()
    source_text = "Из БД" if payment_source == 'auto' else "Вручную"
    log_level = await db.get_log_level()  # новая настройка

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=f"💰 Комиссия ({fee}%)", callback_data="admin_set_fee")
    keyboard.button(text=f"📉 Мин. сумма ({min_amount} ₽)", callback_data="admin_set_min")
    keyboard.button(text=f"📈 Макс. сумма ({max_amount} ₽)", callback_data="admin_set_max")
    keyboard.button(text=f"🔄 Режим оплаты: {mode_text}", callback_data="admin_toggle_payment_mode")
    keyboard.button(text=f"💳 Ручной режим: реквизиты {source_text}", callback_data="admin_toggle_payment_source")
    keyboard.button(text=f"📋 Уровень логов: {log_level}", callback_data="admin_set_log_level")  # новая кнопка
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    text = (
        "⚙️ <b>Настройки обменника</b>\n\n"
        f"Текущая комиссия: {fee}%\n"
        f"Мин. сумма обмена: {min_amount} ₽\n"
        f"Макс. сумма обмена: {max_amount} ₽\n"
        f"Режим оплаты: {mode_text}\n"
        f"Ручной режим: реквизиты {'из БД' if payment_source == 'auto' else 'вводятся вручную'}\n"
        f"Уровень логирования: {log_level}\n\n"
        "Выберите настройку для изменения:"
    )

    logger.info(f"[ADMIN {admin_id}] Открыто меню настроек")
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== ИЗМЕНЕНИЕ КОМИССИИ ====================

@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения комиссии."""
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_fee = await db.get_exchange_fee()
    await state.set_state(AdminStates.changing_fee)

    logger.info(f"[ADMIN {admin_id}] Запрос на изменение комиссии (текущая {current_fee}%)")
    await callback.message.edit_text(
        f"💰 <b>Изменение комиссии</b>\n\n"
        f"Текущая комиссия: {current_fee}%\n\n"
        f"Введите новую комиссию в процентах (например: 2.5):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_fee)
async def admin_set_fee_finish(message: Message, state: FSMContext):
    """Установка новой комиссии."""
    admin_id = message.from_user.id
    try:
        new_fee = float(message.text.replace(",", "."))
        if new_fee < 0 or new_fee > 50:
            logger.warning(f"[ADMIN {admin_id}] Попытка установить некорректную комиссию: {new_fee}")
            await message.answer("❌ Комиссия должна быть от 0 до 50%")
            return

        await db.set_exchange_fee(new_fee, admin_id)
        logger.info(f"[ADMIN {admin_id}] Комиссия изменена на {new_fee}%")
        await message.answer(
            f"✅ Комиссия изменена на {new_fee}%",
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К настройкам", callback_data="admin_settings_menu"
            ).as_markup()
        )
        await state.clear()
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод числа: {message.text}")
        await message.answer("❌ Пожалуйста, введите корректное число:")


# ==================== ИЗМЕНЕНИЕ МИНИМАЛЬНОЙ СУММЫ ====================

@router.callback_query(F.data == "admin_set_min")
async def admin_set_min_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения минимальной суммы."""
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_min = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    await state.set_state(AdminStates.changing_min)

    logger.info(f"[ADMIN {admin_id}] Запрос на изменение минимальной суммы (текущая {current_min})")
    await callback.message.edit_text(
        f"📉 <b>Изменение минимальной суммы</b>\n\n"
        f"Текущая минимальная сумма: {current_min} ₽\n\n"
        f"Введите новую минимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_min)
async def admin_set_min_finish(message: Message, state: FSMContext):
    """Установка новой минимальной суммы."""
    admin_id = message.from_user.id
    try:
        new_min = float(message.text.replace(" ", ""))
        if new_min < 0:
            logger.warning(f"[ADMIN {admin_id}] Попытка установить отрицательную минимальную сумму: {new_min}")
            await message.answer("❌ Сумма не может быть отрицательной.")
            return

        await db.set_setting('min_amount', str(int(new_min)), admin_id)
        logger.info(f"[ADMIN {admin_id}] Минимальная сумма изменена на {int(new_min)}")
        await message.answer(
            f"✅ Минимальная сумма изменена на {int(new_min):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К настройкам", callback_data="admin_settings_menu"
            ).as_markup()
        )
        await state.clear()
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод числа: {message.text}")
        await message.answer("❌ Введите корректное число.")


# ==================== ИЗМЕНЕНИЕ МАКСИМАЛЬНОЙ СУММЫ ====================

@router.callback_query(F.data == "admin_set_max")
async def admin_set_max_start(callback: CallbackQuery, state: FSMContext):
    """Начало изменения максимальной суммы."""
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_max = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    await state.set_state(AdminStates.changing_max)

    logger.info(f"[ADMIN {admin_id}] Запрос на изменение максимальной суммы (текущая {current_max})")
    await callback.message.edit_text(
        f"📈 <b>Изменение максимальной суммы</b>\n\n"
        f"Текущая максимальная сумма: {current_max} ₽\n\n"
        f"Введите новую максимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_max)
async def admin_set_max_finish(message: Message, state: FSMContext):
    """Установка новой максимальной суммы."""
    admin_id = message.from_user.id
    try:
        new_max = float(message.text.replace(" ", ""))
        if new_max < 0:
            logger.warning(f"[ADMIN {admin_id}] Попытка установить отрицательную максимальную сумму: {new_max}")
            await message.answer("❌ Сумма не может быть отрицательной.")
            return

        await db.set_setting('max_amount', str(int(new_max)), admin_id)
        logger.info(f"[ADMIN {admin_id}] Максимальная сумма изменена на {int(new_max)}")
        await message.answer(
            f"✅ Максимальная сумма изменена на {int(new_max):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К настройкам", callback_data="admin_settings_menu"
            ).as_markup()
        )
        await state.clear()
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод числа: {message.text}")
        await message.answer("❌ Введите корректное число.")


# ==================== ПЕРЕКЛЮЧЕНИЕ РЕЖИМА ОПЛАТЫ ====================

@router.callback_query(F.data == "admin_toggle_payment_mode")
async def admin_toggle_payment_mode(callback: CallbackQuery):
    """Переключение между автоматическим и ручным режимом оплаты."""
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_mode = await db.get_payment_mode()
    new_mode = 'manual' if current_mode == 'auto' else 'auto'
    await db.set_payment_mode(new_mode, admin_id)

    logger.info(f"[ADMIN {admin_id}] Режим оплаты изменён с {current_mode} на {new_mode}")
    await callback.answer(f"Режим изменён на {'Ручной' if new_mode == 'manual' else 'Автоматический'}", show_alert=True)
    await admin_settings_menu(callback)


# ==================== ПЕРЕКЛЮЧЕНИЕ ИСТОЧНИКА РЕКВИЗИТОВ ====================

@router.callback_query(F.data == "admin_toggle_payment_source")
async def admin_toggle_payment_source(callback: CallbackQuery):
    """Переключение источника реквизитов в ручном режиме (из БД или вручную)."""
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.get_manual_payment_source()
    new_source = 'auto' if current == 'manual' else 'manual'
    await db.set_manual_payment_source(new_source, admin_id)

    logger.info(f"[ADMIN {admin_id}] Источник реквизитов изменён с {current} на {new_source}")
    await callback.answer(f"Источник реквизитов изменён на {'Из БД' if new_source == 'auto' else 'Вручную'}", show_alert=True)
    await admin_settings_menu(callback)


# ==================== УПРАВЛЕНИЕ УРОВНЕМ ЛОГИРОВАНИЯ (НОВОЕ) ====================

@router.callback_query(F.data == "admin_set_log_level")
async def admin_set_log_level_start(callback: CallbackQuery, state: FSMContext):
    """
    Показывает меню выбора уровня логирования.
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.get_log_level()
    logger.info(f"[ADMIN {admin_id}] Запрос на изменение уровня логов (текущий {current})")

    keyboard = InlineKeyboardBuilder()
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        mark = "✅ " if level == current else ""
        keyboard.button(text=f"{mark}{level}", callback_data=f"admin_set_log_level_{level}")
    keyboard.button(text="🔙 Назад", callback_data="admin_settings_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(
        f"📋 <b>Выберите уровень логирования</b>\n\n"
        f"Текущий: {current}\n\n"
        f"• DEBUG – все отладочные сообщения\n"
        f"• INFO – основные события (рекомендуется для разработки)\n"
        f"• WARNING – только предупреждения и ошибки (для эксплуатации)\n"
        f"• ERROR – только ошибки\n"
        f"• CRITICAL – только критические ошибки",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_log_level_"))
async def admin_set_log_level_execute(callback: CallbackQuery):
    """
    Устанавливает выбранный уровень логирования и применяет его.
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    new_level = callback.data.split("_")[-1]  # DEBUG, INFO и т.д.
    logger.info(f"[ADMIN {admin_id}] Изменение уровня логирования на {new_level}")

    # Сохраняем в БД
    success = await db.set_log_level(new_level, admin_id)
    if not success:
        await callback.answer("❌ Не удалось изменить уровень (недопустимое значение)", show_alert=True)
        return

    # Применяем новый уровень к корневому логгеру
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, new_level))
    # Также можно изменить уровень для консольного обработчика, но обычно корневого достаточно

    logger.info(f"[ADMIN {admin_id}] Уровень логирования успешно изменён на {new_level}")
    await callback.answer(f"✅ Уровень логирования изменён на {new_level}", show_alert=True)
    # Возвращаемся в меню настроек
    await admin_settings_menu(callback)