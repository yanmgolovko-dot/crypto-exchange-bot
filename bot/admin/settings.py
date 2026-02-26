# bot/admin/settings.py
"""
Обработчики админ-панели для управления настройками бота.
Позволяют изменять комиссию, лимиты, режим оплаты, источник реквизитов, уровень логирования,
а также настройки приветственных купонов, купонов за активность и номеров заявок.
"""

import logging
import json
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.config.settings import config
from bot.admin.main import is_admin
from bot.admin.states import AdminStates
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


# ==================== ГЛАВНОЕ МЕНЮ НАСТРОЕК ====================
async def send_settings_menu(user_id: int, bot: Bot):
    """Отправляет пользователю меню настроек (новым сообщением)."""
    fee = await db.get_exchange_fee()
    min_amount = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    max_amount = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    payment_mode = await db.get_payment_mode()
    mode_text = "Автоматический" if payment_mode == 'auto' else "Ручной"
    payment_source = await db.get_manual_payment_source()
    source_text = "Из БД" if payment_source == 'auto' else "Вручную"
    log_level = await db.get_log_level()
    next_order = await db.settings.get_setting('next_order_number', '1')
    reminders_enabled = await db.settings.get_reminders_enabled()
    reminders_status = "✅ Вкл" if reminders_enabled else "❌ Выкл"

    welcome_config = await db.settings.get_json_setting('welcome_coupon_config', {})
    activity_config = await db.settings.get_json_setting('activity_coupon_config', {})

    welcome_status = "✅ Включены" if welcome_config.get('enabled') else "❌ Отключены"
    activity_status = "✅ Включены" if activity_config.get('enabled') else "❌ Отключены"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=f"💰 Комиссия ({fee}%)", callback_data="admin_set_fee")
    keyboard.button(text=f"📉 Мин. сумма ({min_amount} ₽)", callback_data="admin_set_min")
    keyboard.button(text=f"📈 Макс. сумма ({max_amount} ₽)", callback_data="admin_set_max")
    keyboard.button(text=f"🔄 Режим оплаты: {mode_text}", callback_data="admin_toggle_payment_mode")
    keyboard.button(text=f"💳 Ручной режим: реквизиты {source_text}", callback_data="admin_toggle_payment_source")
    keyboard.button(text=f"📋 Уровень логов: {log_level}", callback_data="admin_set_log_level")
    keyboard.button(text=f"🎁 Приветств. купоны {welcome_status}", callback_data="admin_edit_welcome_coupon")
    keyboard.button(text=f"🎁 Купоны за активность {activity_status}", callback_data="admin_edit_activity_coupon")
    keyboard.button(text=f"📋 След. № заявки ({next_order})", callback_data="admin_set_next_order_number")
    keyboard.button(text=f"🔔 Напоминания {reminders_status}", callback_data="admin_toggle_reminders")
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
        f"<b>Купоны:</b>\n"
        f"• Приветственные: {welcome_status}\n"
        f"• За активность: {activity_status}\n\n"
        f"<b>Нумерация заявок:</b>\n"
        f"• Следующий номер: {next_order}\n\n"
        f"<b>Напоминания о чеке:</b> {'включены' if reminders_enabled else 'отключены'}\n\n"
        "Выберите настройку для изменения:"
    )

    await bot.send_message(user_id, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_settings_menu")
async def admin_settings_menu(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # Получаем текущие настройки из БД
    fee = await db.get_exchange_fee()
    min_amount = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    max_amount = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    payment_mode = await db.get_payment_mode()
    mode_text = "Автоматический" if payment_mode == 'auto' else "Ручной"
    payment_source = await db.get_manual_payment_source()
    source_text = "Из БД" if payment_source == 'auto' else "Вручную"
    log_level = await db.get_log_level()
    next_order = await db.settings.get_setting('next_order_number', '1')
    reminders_enabled = await db.settings.get_reminders_enabled()
    reminders_status = "✅ Вкл" if reminders_enabled else "❌ Выкл"

    # Получаем настройки купонов (JSON)
    welcome_config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    activity_config = await db.settings.get_json_setting('activity_coupon_config', {
        "enabled": False,
        "thresholds": [
            {"orders": 5, "discount_type": "percent", "discount_value": 3, "discount_on": "commission", "valid_days": 30},
            {"orders": 10, "discount_type": "fixed", "discount_value": 100, "discount_on": "order", "valid_days": 30}
        ]
    })

    welcome_status = "✅ Включены" if welcome_config.get('enabled') else "❌ Отключены"
    activity_status = "✅ Включены" if activity_config.get('enabled') else "❌ Отключены"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=f"💰 Комиссия ({fee}%)", callback_data="admin_set_fee")
    keyboard.button(text=f"📉 Мин. сумма ({min_amount} ₽)", callback_data="admin_set_min")
    keyboard.button(text=f"📈 Макс. сумма ({max_amount} ₽)", callback_data="admin_set_max")
    keyboard.button(text=f"🔄 Режим оплаты: {mode_text}", callback_data="admin_toggle_payment_mode")
    keyboard.button(text=f"💳 Ручной режим: реквизиты {source_text}", callback_data="admin_toggle_payment_source")
    keyboard.button(text=f"📋 Уровень логов: {log_level}", callback_data="admin_set_log_level")
    keyboard.button(text=f"🎁 Приветств. купоны {welcome_status}", callback_data="admin_edit_welcome_coupon")
    keyboard.button(text=f"🎁 Купоны за активность {activity_status}", callback_data="admin_edit_activity_coupon")
    keyboard.button(text=f"📋 След. № заявки ({next_order})", callback_data="admin_set_next_order_number")
    keyboard.button(text=f"🔔 Напоминания {reminders_status}", callback_data="admin_toggle_reminders")
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
        f"<b>Купоны:</b>\n"
        f"• Приветственные: {welcome_status}\n"
        f"• За активность: {activity_status}\n\n"
        f"<b>Нумерация заявок:</b>\n"
        f"• Следующий номер: {next_order}\n\n"
        f"<b>Напоминания о чеке:</b> {'включены' if reminders_enabled else 'отключены'}\n\n"
        "Выберите настройку для изменения:"
    )

    await safe_edit_message(
        callback.message,
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ==================== НАСТРОЙКА ПРИВЕТСТВЕННЫХ КУПОНОВ ====================
@router.callback_query(F.data == "admin_edit_welcome_coupon")
async def admin_edit_welcome_coupon(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await send_welcome_edit_menu(callback.message)
    await callback.answer()


async def send_welcome_edit_menu(message: Message):
    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })

    text = (
        "🎁 <b>Настройка приветственного купона</b>\n\n"
        f"• Включён: {'✅' if config.get('enabled') else '❌'}\n"
        f"• Тип скидки: {escape_html(str(config.get('discount_type', '')))}\n"
        f"• Значение: {escape_html(str(config.get('discount_value', '')))}\n"
        f"• Применяется: {'на всю сумму' if config.get('discount_on') == 'order' else 'на комиссию'}\n"
        f"• Срок действия: {escape_html(str(config.get('valid_days', '')))} дней\n"
        f"• Описание: {escape_html(config.get('description', ''))}\n\n"
        "Выберите, что изменить:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔄 Вкл/Выкл", callback_data="admin_welcome_toggle_enabled")
    keyboard.button(text="📝 Тип скидки", callback_data="admin_welcome_set_discount_type")
    keyboard.button(text="🔢 Значение", callback_data="admin_welcome_set_value")
    keyboard.button(text="📌 Применять на", callback_data="admin_welcome_set_discount_on")
    keyboard.button(text="⏱ Срок (дни)", callback_data="admin_welcome_set_valid_days")
    keyboard.button(text="📄 Описание", callback_data="admin_welcome_set_description")
    keyboard.button(text="🔙 Назад", callback_data="admin_settings_menu")
    keyboard.adjust(1)

    await safe_edit_message(message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_welcome_toggle_enabled")
async def admin_welcome_toggle_enabled(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['enabled'] = not config.get('enabled', False)
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Приветственные купоны теперь {'включены' if config['enabled'] else 'отключены'}", show_alert=True)
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_discount_type")
async def admin_welcome_set_discount_type_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_discount_type)
    await safe_edit_message(
        callback.message,
        "📝 Выберите тип скидки:",
        reply_markup=InlineKeyboardBuilder()
            .button(text="Процент (%)", callback_data="welcome_discount_type_percent")
            .button(text="Фиксированная сумма (₽)", callback_data="welcome_discount_type_fixed")
            .button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon")
            .as_markup()
    )
    await callback.answer()


@router.callback_query(AdminStates.editing_welcome_discount_type, F.data.startswith("welcome_discount_type_"))
async def admin_welcome_set_discount_type_finish(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    discount_type = callback.data.split("_")[-1]  # percent или fixed
    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['discount_type'] = discount_type
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Тип скидки изменён на {discount_type}", show_alert=True)
    await state.clear()
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_value")
async def admin_welcome_set_value_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_value)
    await safe_edit_message(
        callback.message,
        "🔢 Введите значение скидки (например, 10 для процентов или 100 для рублей):",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.editing_welcome_value)
async def admin_welcome_set_value_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        value = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return

    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['discount_value'] = value
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Значение изменено на {value}")
    await state.clear()
    await send_welcome_edit_menu(message)


@router.callback_query(F.data == "admin_welcome_set_discount_on")
async def admin_welcome_set_discount_on_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_discount_on)
    await safe_edit_message(
        callback.message,
        "📌 На что будет действовать скидка?",
        reply_markup=InlineKeyboardBuilder()
            .button(text="На всю сумму заказа", callback_data="welcome_discount_on_order")
            .button(text="Только на комиссию", callback_data="welcome_discount_on_commission")
            .button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon")
            .as_markup()
    )
    await callback.answer()


@router.callback_query(AdminStates.editing_welcome_discount_on, F.data.startswith("welcome_discount_on_"))
async def admin_welcome_set_discount_on_finish(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    discount_on = callback.data.split("_")[-1]  # order или commission
    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['discount_on'] = discount_on
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Применение изменено: {'вся сумма' if discount_on == 'order' else 'комиссия'}", show_alert=True)
    await state.clear()
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_valid_days")
async def admin_welcome_set_valid_days_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_valid_days)
    await safe_edit_message(
        callback.message,
        "⏱ Введите срок действия купона в днях (например, 30):",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.editing_welcome_valid_days)
async def admin_welcome_set_valid_days_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        days = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['valid_days'] = days
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Срок действия изменён на {days} дней")
    await state.clear()
    await send_welcome_edit_menu(message)


@router.callback_query(F.data == "admin_welcome_set_description")
async def admin_welcome_set_description_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_description)
    await safe_edit_message(
        callback.message,
        "📄 Введите описание купона:",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.editing_welcome_description)
async def admin_welcome_set_description_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    description = message.text.strip()
    config = await db.settings.get_json_setting('welcome_coupon_config')
    config['description'] = description
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Описание изменено: {description}")
    await state.clear()
    await send_welcome_edit_menu(message)


# ==================== НАСТРОЙКА КУПОНОВ ЗА АКТИВНОСТЬ ====================
@router.callback_query(F.data == "admin_edit_activity_coupon")
async def admin_edit_activity_coupon(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await send_activity_edit_menu(callback.message)
    await callback.answer()


async def send_activity_edit_menu(message: Message):
    config = await db.settings.get_json_setting('activity_coupon_config', {
        "enabled": False,
        "thresholds": []
    })

    enabled_status = "✅ Включены" if config.get('enabled') else "❌ Отключены"
    text = f"🎁 <b>Настройка купонов за активность</b>\n\nСтатус: {enabled_status}\n\n<b>Пороги:</b>\n"
    for i, t in enumerate(config.get('thresholds', []), 1):
        text += f"{i}. {t['orders']} заявок: {t['discount_value']}{'%' if t['discount_type']=='percent' else '₽'} на {'всю сумму' if t['discount_on']=='order' else 'комиссию'}, {t['valid_days']} дн.\n"

    text += "\nВыберите действие:"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔄 Вкл/Выкл", callback_data="admin_activity_toggle_enabled")
    keyboard.button(text="➕ Добавить порог", callback_data="admin_activity_add_threshold")
    keyboard.button(text="✏️ Редактировать порог", callback_data="admin_activity_edit_threshold")
    keyboard.button(text="❌ Удалить порог", callback_data="admin_activity_remove_threshold")
    keyboard.button(text="🔙 Назад", callback_data="admin_settings_menu")
    keyboard.adjust(1)

    await safe_edit_message(message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_activity_toggle_enabled")
async def admin_activity_toggle_enabled(callback: CallbackQuery):
    admin_id = callback.from_user.id
    config = await db.settings.get_json_setting('activity_coupon_config', {"enabled": False, "thresholds": []})
    config['enabled'] = not config.get('enabled', False)
    await db.settings.set_json_setting('activity_coupon_config', config, admin_id)
    await callback.answer(f"Купоны за активность теперь {'включены' if config['enabled'] else 'отключены'}", show_alert=True)
    await admin_edit_activity_coupon(callback)


@router.callback_query(F.data == "admin_activity_add_threshold")
async def admin_activity_add_threshold_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.adding_activity_threshold_orders)
    await safe_edit_message(
        callback.message,
        "➕ Добавление порога\n\nВведите количество заявок (например, 5):",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_edit_activity_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.adding_activity_threshold_orders)
async def admin_activity_add_threshold_orders(message: Message, state: FSMContext):
    try:
        orders = int(message.text.strip())
        if orders <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    await state.update_data(threshold_orders=orders)
    await state.set_state(AdminStates.adding_activity_threshold_discount_type)
    await message.answer(
        "Выберите тип скидки:",
        reply_markup=InlineKeyboardBuilder()
            .button(text="Процент (%)", callback_data="activity_threshold_type_percent")
            .button(text="Фиксированная сумма (₽)", callback_data="activity_threshold_type_fixed")
            .button(text="🔙 Отмена", callback_data="admin_edit_activity_coupon")
            .as_markup()
    )


@router.callback_query(AdminStates.adding_activity_threshold_discount_type, F.data.startswith("activity_threshold_type_"))
async def admin_activity_add_threshold_type(callback: CallbackQuery, state: FSMContext):
    discount_type = callback.data.split("_")[-1]  # percent или fixed
    await state.update_data(threshold_discount_type=discount_type)
    await state.set_state(AdminStates.adding_activity_threshold_value)
    await safe_edit_message(
        callback.message,
        f"Введите значение скидки {'(в процентах)' if discount_type == 'percent' else '(в рублях)'}:",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_edit_activity_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.adding_activity_threshold_value)
async def admin_activity_add_threshold_value(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(",", "."))
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return

    await state.update_data(threshold_value=value)
    await state.set_state(AdminStates.adding_activity_threshold_discount_on)
    await message.answer(
        "На что будет действовать скидка?",
        reply_markup=InlineKeyboardBuilder()
            .button(text="На всю сумму заказа", callback_data="activity_threshold_on_order")
            .button(text="Только на комиссию", callback_data="activity_threshold_on_commission")
            .button(text="🔙 Отмена", callback_data="admin_edit_activity_coupon")
            .as_markup()
    )


@router.callback_query(AdminStates.adding_activity_threshold_discount_on, F.data.startswith("activity_threshold_on_"))
async def admin_activity_add_threshold_discount_on(callback: CallbackQuery, state: FSMContext):
    discount_on = callback.data.split("_")[-1]  # order или commission
    await state.update_data(threshold_discount_on=discount_on)
    await state.set_state(AdminStates.adding_activity_threshold_valid_days)
    await safe_edit_message(
        callback.message,
        "Введите срок действия купона в днях (например, 30):",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Отмена", callback_data="admin_edit_activity_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.adding_activity_threshold_valid_days)
async def admin_activity_add_threshold_finish(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    data = await state.get_data()
    config = await db.settings.get_json_setting('activity_coupon_config', {"enabled": False, "thresholds": []})
    if 'thresholds' not in config:
        config['thresholds'] = []
    new_threshold = {
        "orders": data['threshold_orders'],
        "discount_type": data['threshold_discount_type'],
        "discount_value": data['threshold_value'],
        "discount_on": data['threshold_discount_on'],
        "valid_days": days
    }
    config['thresholds'].append(new_threshold)
    await db.settings.set_json_setting('activity_coupon_config', config, message.from_user.id)

    await message.answer(f"✅ Порог добавлен: {new_threshold['orders']} заявок -> {new_threshold['discount_value']}{'%' if new_threshold['discount_type']=='percent' else '₽'}")
    await state.clear()
    await send_activity_edit_menu(message)


@router.callback_query(F.data == "admin_activity_remove_threshold")
async def admin_activity_remove_threshold_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    config = await db.settings.get_json_setting('activity_coupon_config', {"enabled": False, "thresholds": []})
    thresholds = config.get('thresholds', [])
    if not thresholds:
        await callback.answer("Нет порогов для удаления", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    for i, t in enumerate(thresholds, 1):
        keyboard.button(text=f"{i}. {t['orders']} заявок", callback_data=f"activity_remove_{i-1}")
    keyboard.button(text="🔙 Назад", callback_data="admin_edit_activity_coupon")
    keyboard.adjust(1)
    await safe_edit_message(
        callback.message,
        "Выберите порог для удаления:",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("activity_remove_"))
async def admin_activity_remove_threshold_execute(callback: CallbackQuery):
    admin_id = callback.from_user.id
    index = int(callback.data.split("_")[-1])
    config = await db.settings.get_json_setting('activity_coupon_config', {"enabled": False, "thresholds": []})
    if 0 <= index < len(config.get('thresholds', [])):
        removed = config['thresholds'].pop(index)
        await db.settings.set_json_setting('activity_coupon_config', config, admin_id)
        await callback.answer(f"Порог удалён", show_alert=True)
    else:
        await callback.answer("Ошибка индекса", show_alert=True)
    await admin_edit_activity_coupon(callback)


# ==================== НАСТРОЙКА СЛЕДУЮЩЕГО НОМЕРА ЗАЯВКИ ====================
@router.callback_query(F.data == "admin_set_next_order_number")
async def admin_set_next_order_number_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.settings.get_setting('next_order_number', '1')
    await state.set_state(AdminStates.setting_next_order_number)
    await safe_edit_message(
        callback.message,
        f"📋 <b>Установка следующего номера заявки</b>\n\n"
        f"Текущее значение: {current}\n\n"
        f"Введите новый номер (целое число больше 0):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.setting_next_order_number)
async def admin_set_next_order_number_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        new_number = int(message.text.strip())
        if new_number <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return

    await db.settings.set_setting('next_order_number', str(new_number), admin_id)
    await message.answer(f"✅ Следующий номер заявки установлен: {new_number}")

    # Возвращаемся в меню настроек
    await send_settings_menu(message.from_user.id, message.bot)
    await state.clear()


# ==================== ПЕРЕКЛЮЧЕНИЕ НАПОМИНАНИЙ ====================
@router.callback_query(F.data == "admin_toggle_reminders")
async def admin_toggle_reminders(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.settings.get_reminders_enabled()
    new_state = not current
    await db.settings.set_reminders_enabled(new_state, admin_id)
    await callback.answer(f"Напоминания {'включены' if new_state else 'отключены'}", show_alert=True)
    await admin_settings_menu(callback)


# ==================== ИЗМЕНЕНИЕ КОМИССИИ ====================
@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_fee = await db.get_exchange_fee()
    await state.set_state(AdminStates.changing_fee)
    await safe_edit_message(
        callback.message,
        f"💰 <b>Изменение комиссии</b>\n\n"
        f"Текущая комиссия: {current_fee}%\n\n"
        f"Введите новую комиссию в процентах (например: 2.5):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_fee)
async def admin_set_fee_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        new_fee = float(message.text.replace(",", "."))
        if new_fee < 0 or new_fee > 50:
            await message.answer("❌ Комиссия должна быть от 0 до 50%")
            return
        await db.set_exchange_fee(new_fee, admin_id)
        await message.answer(
            f"✅ Комиссия изменена на {new_fee}%",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К настройкам", callback_data="admin_settings_menu").as_markup()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


# ==================== ИЗМЕНЕНИЕ МИНИМАЛЬНОЙ СУММЫ ====================
@router.callback_query(F.data == "admin_set_min")
async def admin_set_min_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_min = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    await state.set_state(AdminStates.changing_min)
    await safe_edit_message(
        callback.message,
        f"📉 <b>Изменение минимальной суммы</b>\n\n"
        f"Текущая минимальная сумма: {current_min} ₽\n\n"
        f"Введите новую минимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_min)
async def admin_set_min_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        new_min = float(message.text.replace(" ", ""))
        if new_min < 0:
            await message.answer("❌ Сумма не может быть отрицательной.")
            return
        await db.set_setting('min_amount', str(int(new_min)), admin_id)
        await message.answer(
            f"✅ Минимальная сумма изменена на {int(new_min):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К настройкам", callback_data="admin_settings_menu").as_markup()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректное число.")


# ==================== ИЗМЕНЕНИЕ МАКСИМАЛЬНОЙ СУММЫ ====================
@router.callback_query(F.data == "admin_set_max")
async def admin_set_max_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_max = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    await state.set_state(AdminStates.changing_max)
    await safe_edit_message(
        callback.message,
        f"📈 <b>Изменение максимальной суммы</b>\n\n"
        f"Текущая максимальная сумма: {current_max} ₽\n\n"
        f"Введите новую максимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_max)
async def admin_set_max_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    try:
        new_max = float(message.text.replace(" ", ""))
        if new_max < 0:
            await message.answer("❌ Сумма не может быть отрицательной.")
            return
        await db.set_setting('max_amount', str(int(new_max)), admin_id)
        await message.answer(
            f"✅ Максимальная сумма изменена на {int(new_max):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К настройкам", callback_data="admin_settings_menu").as_markup()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректное число.")


# ==================== ПЕРЕКЛЮЧЕНИЕ РЕЖИМА ОПЛАТЫ ====================
@router.callback_query(F.data == "admin_toggle_payment_mode")
async def admin_toggle_payment_mode(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_mode = await db.get_payment_mode()
    new_mode = 'manual' if current_mode == 'auto' else 'auto'
    await db.set_payment_mode(new_mode, admin_id)
    await callback.answer(f"Режим изменён на {'Ручной' if new_mode == 'manual' else 'Автоматический'}", show_alert=True)
    await admin_settings_menu(callback)


# ==================== ПЕРЕКЛЮЧЕНИЕ ИСТОЧНИКА РЕКВИЗИТОВ ====================
@router.callback_query(F.data == "admin_toggle_payment_source")
async def admin_toggle_payment_source(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.get_manual_payment_source()
    new_source = 'auto' if current == 'manual' else 'manual'
    await db.set_manual_payment_source(new_source, admin_id)
    await callback.answer(f"Источник реквизитов изменён на {'Из БД' if new_source == 'auto' else 'Вручную'}", show_alert=True)
    await admin_settings_menu(callback)


# ==================== УПРАВЛЕНИЕ УРОВНЕМ ЛОГИРОВАНИЯ ====================
@router.callback_query(F.data == "admin_set_log_level")
async def admin_set_log_level_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
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

    await safe_edit_message(
        callback.message,
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
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    new_level = callback.data.split("_")[-1]
    success = await db.set_log_level(new_level, admin_id)
    if not success:
        await callback.answer("❌ Не удалось изменить уровень (недопустимое значение)", show_alert=True)
        return
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, new_level))
    await callback.answer(f"✅ Уровень логирования изменён на {new_level}", show_alert=True)
    await admin_settings_menu(callback)