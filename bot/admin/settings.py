# bot/admin/settings.py
"""
Обработчики админ-панели для управления настройками бота.
Позволяют изменять комиссию, лимиты, режим оплаты, источник реквизитов, уровень логирования,
а также настройки приветственных купонов и купонов за активность.
"""

import logging
import json
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


# ==================== ГЛАВНОЕ МЕНЮ НАСТРОЕК ====================
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
    log_level = await db.get_log_level()

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
    # Кнопки для купонов
    keyboard.button(text=f"🎁 Приветств. купоны {welcome_status}", callback_data="admin_edit_welcome_coupon")
    keyboard.button(text=f"🎁 Купоны за активность {activity_status}", callback_data="admin_edit_activity_coupon")
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
        "Выберите настройку для изменения:"
    )

    logger.info(f"[ADMIN {admin_id}] Открыто меню настроек")
    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ВОЗВРАТА В МЕНЮ ====================
async def send_welcome_edit_menu(message: Message):
    """Отправляет сообщение с меню настройки приветственного купона."""
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
        f"• Тип скидки: {config.get('discount_type')}\n"
        f"• Значение: {config.get('discount_value')}\n"
        f"• Применяется: {'на всю сумму' if config.get('discount_on') == 'order' else 'на комиссию'}\n"
        f"• Срок действия: {config.get('valid_days')} дней\n"
        f"• Описание: {config.get('description')}\n\n"
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

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


async def send_activity_edit_menu(message: Message):
    """Отправляет сообщение с меню настройки купонов за активность."""
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

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


# ==================== НАСТРОЙКА ПРИВЕТСТВЕННЫХ КУПОНОВ ====================
@router.callback_query(F.data == "admin_edit_welcome_coupon")
async def admin_edit_welcome_coupon(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await send_welcome_edit_menu(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin_welcome_toggle_enabled")
async def admin_welcome_toggle_enabled(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['enabled'] = not config.get('enabled', False)
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Приветственные купоны теперь {'включены' if config['enabled'] else 'отключены'}", show_alert=True)
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_discount_type")
async def admin_welcome_set_discount_type_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_discount_type)
    await callback.message.edit_text(
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
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    discount_type = callback.data.split("_")[-1]  # percent или fixed
    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['discount_type'] = discount_type
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Тип скидки изменён на {discount_type}", show_alert=True)
    await state.clear()
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_value")
async def admin_welcome_set_value_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_value)
    await callback.message.edit_text(
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

    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['discount_value'] = value
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Значение изменено на {value}")
    await state.clear()
    await send_welcome_edit_menu(message)


@router.callback_query(F.data == "admin_welcome_set_discount_on")
async def admin_welcome_set_discount_on_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_discount_on)
    await callback.message.edit_text(
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
    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['discount_on'] = discount_on
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await callback.answer(f"Применение изменено: {'вся сумма' if discount_on == 'order' else 'комиссия'}", show_alert=True)
    await state.clear()
    await admin_edit_welcome_coupon(callback)


@router.callback_query(F.data == "admin_welcome_set_valid_days")
async def admin_welcome_set_valid_days_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_valid_days)
    await callback.message.edit_text(
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

    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['valid_days'] = days
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Срок действия изменён на {days} дней")
    await state.clear()
    await send_welcome_edit_menu(message)


@router.callback_query(F.data == "admin_welcome_set_description")
async def admin_welcome_set_description_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.editing_welcome_description)
    await callback.message.edit_text(
        "📄 Введите описание купона:",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_edit_welcome_coupon").as_markup()
    )
    await callback.answer()


@router.message(AdminStates.editing_welcome_description)
async def admin_welcome_set_description_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    description = message.text.strip()
    config = await db.settings.get_json_setting('welcome_coupon_config', {
        "enabled": False,
        "discount_type": "percent",
        "discount_value": 5,
        "discount_on": "commission",
        "valid_days": 30,
        "description": "Приветственный купон"
    })
    config['description'] = description
    await db.settings.set_json_setting('welcome_coupon_config', config, admin_id)
    await message.answer(f"✅ Описание изменено: {description}")
    await state.clear()
    await send_welcome_edit_menu(message)


# ==================== НАСТРОЙКА КУПОНОВ ЗА АКТИВНОСТЬ ====================
@router.callback_query(F.data == "admin_edit_activity_coupon")
async def admin_edit_activity_coupon(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await send_activity_edit_menu(callback.message)
    await callback.answer()


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
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.adding_activity_threshold_orders)
    await callback.message.edit_text(
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
    await callback.message.edit_text(
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
    await callback.message.edit_text(
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

    # Показываем список порогов для выбора
    keyboard = InlineKeyboardBuilder()
    for i, t in enumerate(thresholds, 1):
        keyboard.button(text=f"{i}. {t['orders']} заявок", callback_data=f"activity_remove_{i-1}")
    keyboard.button(text="🔙 Назад", callback_data="admin_edit_activity_coupon")
    keyboard.adjust(1)
    await callback.message.edit_text(
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


# ==================== ИЗМЕНЕНИЕ КОМИССИИ ====================
@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee_start(callback: CallbackQuery, state: FSMContext):
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


# ==================== УПРАВЛЕНИЕ УРОВНЕМ ЛОГИРОВАНИЯ ====================
@router.callback_query(F.data == "admin_set_log_level")
async def admin_set_log_level_start(callback: CallbackQuery, state: FSMContext):
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
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    new_level = callback.data.split("_")[-1]  # DEBUG, INFO и т.д.
    logger.info(f"[ADMIN {admin_id}] Изменение уровня логирования на {new_level}")

    success = await db.set_log_level(new_level, admin_id)
    if not success:
        await callback.answer("❌ Не удалось изменить уровень (недопустимое значение)", show_alert=True)
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, new_level))

    logger.info(f"[ADMIN {admin_id}] Уровень логирования успешно изменён на {new_level}")
    await callback.answer(f"✅ Уровень логирования изменён на {new_level}", show_alert=True)
    await admin_settings_menu(callback)