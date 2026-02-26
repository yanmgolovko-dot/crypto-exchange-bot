# bot/admin/coupons.py
"""Обработчики админ-панели для управления купонами."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin
from bot.admin.states import AdminStates
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_coupons_menu")
async def admin_coupons_menu(callback: CallbackQuery):
    """Меню управления купонами."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа к меню купонов без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Открыто меню купонов")
    try:
        coupons = await db.coupons.get_all_coupons()
        active_count = sum(1 for c in coupons if c.is_active)
        logger.debug(f"Всего купонов: {len(coupons)}, активных: {active_count}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка купонов: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Создать купон", callback_data="admin_coupon_create")
    keyboard.button(text="📋 Список купонов", callback_data="admin_coupon_list")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    text = (
        f"🎫 <b>Управление купонами</b>\n\n"
        f"Всего купонов: {len(coupons)}\n"
        f"Активных: {active_count}\n\n"
        f"Выберите действие:"
    )

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_coupon_create")
async def admin_coupon_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания купона (запрос кода)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Начало создания купона")
    await state.set_state(AdminStates.creating_coupon_code)
    text = "🎫 <b>Создание купона</b>\n\nВведите код купона (например: SUMMER2026):"
    await safe_edit_message(callback.message, text, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.creating_coupon_code)
async def admin_coupon_discount_type(message: Message, state: FSMContext):
    """Обработка введённого кода, запрос типа скидки."""
    admin_id = message.from_user.id
    code = message.text.strip().upper()
    if len(code) < 3:
        logger.warning(f"[ADMIN {admin_id}] Слишком короткий код: {code}")
        await message.answer("❌ Код должен быть не менее 3 символов")
        return
    await state.update_data(coupon_code=code)
    await state.set_state(AdminStates.creating_coupon_discount_type)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Процент (%)", callback_data="coupon_type_percent")
    keyboard.button(text="Фиксированная сумма (₽)", callback_data="coupon_type_fixed")
    keyboard.button(text="🔙 Отмена", callback_data="admin_coupons_menu")
    keyboard.adjust(1)
    await message.answer(
        "Выберите тип скидки:",
        reply_markup=keyboard.as_markup()
    )


@router.callback_query(AdminStates.creating_coupon_discount_type)
async def admin_coupon_discount_value(callback: CallbackQuery, state: FSMContext):
    """Выбор типа скидки, запрос величины."""
    admin_id = callback.from_user.id
    discount_type = callback.data.split("_")[-1]  # percent или fixed
    await state.update_data(coupon_discount_type=discount_type)
    await state.set_state(AdminStates.creating_coupon_discount_value)
    text = f"Введите значение скидки:\n{' (в процентах, например 10)' if discount_type == 'percent' else ' (в рублях, например 500)'}:"
    await safe_edit_message(callback.message, text)
    await callback.answer()


@router.message(AdminStates.creating_coupon_discount_value)
async def admin_coupon_discount_on(message: Message, state: FSMContext):
    """Обработка величины скидки, запрос области применения."""
    admin_id = message.from_user.id
    try:
        value = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число")
        return
    await state.update_data(coupon_discount_value=value)
    await state.set_state(AdminStates.creating_coupon_discount_on)
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="На всю сумму заказа", callback_data="coupon_on_order")
    keyboard.button(text="Только на комиссию", callback_data="coupon_on_commission")
    keyboard.button(text="🔙 Отмена", callback_data="admin_coupons_menu")
    keyboard.adjust(1)
    await message.answer(
        "На что будет действовать скидка?",
        reply_markup=keyboard.as_markup()
    )


@router.callback_query(AdminStates.creating_coupon_discount_on)
async def admin_coupon_limits(callback: CallbackQuery, state: FSMContext):
    """Выбор области применения, запрос лимитов."""
    admin_id = callback.from_user.id
    discount_on = callback.data.split("_")[-1]  # order или commission
    await state.update_data(coupon_discount_on=discount_on)
    await state.set_state(AdminStates.creating_coupon_limits)
    text = (
        "Введите лимиты через пробел (или пропустите, нажав Enter):\n\n"
        "1. Общее максимальное количество использований (0 или пусто – безлимит)\n"
        "2. Максимум использований на одного пользователя (0 или пусто – безлимит)\n"
        "3. Минимальная сумма заказа в рублях (0 – без ограничений)\n\n"
        "Пример: 100 1 1000  (100 всего, 1 на пользователя, мин. сумма 1000 ₽)\n"
        "Или оставьте пустым для безлимита."
    )
    await safe_edit_message(callback.message, text)
    await callback.answer()


@router.message(AdminStates.creating_coupon_limits)
async def admin_coupon_valid_days(message: Message, state: FSMContext):
    """Обработка лимитов, запрос срока действия."""
    admin_id = message.from_user.id
    text = message.text.strip()
    limits = [int(x) for x in text.split()] if text else [0, 0, 0]
    # Приводим к нужному формату: 0 интерпретируем как None
    max_uses_total = limits[0] if len(limits) > 0 and limits[0] > 0 else None
    max_uses_per_user = limits[1] if len(limits) > 1 and limits[1] > 0 else None
    min_order_amount = limits[2] if len(limits) > 2 else 0
    await state.update_data(
        coupon_max_uses_total=max_uses_total,
        coupon_max_uses_per_user=max_uses_per_user,
        coupon_min_order_amount=min_order_amount
    )
    await state.set_state(AdminStates.creating_coupon_valid_days)
    await message.answer("Введите срок действия в днях (например 30, или 0 для бессрочного):")


@router.message(AdminStates.creating_coupon_valid_days)
async def admin_coupon_description(message: Message, state: FSMContext):
    """Обработка срока действия, запрос описания."""
    admin_id = message.from_user.id
    try:
        days = int(message.text)
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число дней (0 – бессрочно)")
        return
    await state.update_data(coupon_valid_days=days if days > 0 else None)
    await state.set_state(AdminStates.creating_coupon_description)
    await message.answer("Введите описание купона (или отправьте /skip):")


@router.message(AdminStates.creating_coupon_description)
async def admin_coupon_finish(message: Message, state: FSMContext):
    """Финализация создания купона."""
    admin_id = message.from_user.id
    description = message.text if message.text != "/skip" else None
    data = await state.get_data()
    logger.info(f"[ADMIN {admin_id}] Создание купона в БД")

    try:
        coupon_id = await db.coupons.create_coupon(
            code=data['coupon_code'],
            discount_type=data['coupon_discount_type'],
            discount_value=data['coupon_discount_value'],
            discount_on=data['coupon_discount_on'],
            max_uses_total=data.get('coupon_max_uses_total'),
            max_uses_per_user=data.get('coupon_max_uses_per_user'),
            min_order_amount=data.get('coupon_min_order_amount', 0),
            valid_days=data.get('coupon_valid_days'),
            created_by=admin_id,
            description=description
        )
        logger.info(f"[ADMIN {admin_id}] Купон создан, ID: {coupon_id}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при создании купона: {e}", exc_info=True)
        await message.answer("❌ Ошибка при создании купона. Возможно, код уже существует.")
        await state.clear()
        return

    text = (
        f"✅ Купон создан!\n\n"
        f"Код: <code>{escape_html(data['coupon_code'])}</code>\n"
        f"Тип: {'Процент' if data['coupon_discount_type'] == 'percent' else 'Фиксированная сумма'}\n"
        f"Значение: {data['coupon_discount_value']}\n"
        f"Применяется: {'на всю сумму' if data['coupon_discount_on'] == 'order' else 'на комиссию'}\n"
        f"Лимиты: общий {data.get('coupon_max_uses_total', '∞')}, на пользователя {data.get('coupon_max_uses_per_user', '∞')}\n"
        f"Мин. сумма: {data.get('coupon_min_order_amount', 0)} ₽\n"
        f"Срок: {data.get('coupon_valid_days', 'бессрочно')} дней\n"
        f"Описание: {escape_html(description or '—')}"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 К купонам", callback_data="admin_coupons_menu")
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "admin_coupon_list")
async def admin_coupon_list(callback: CallbackQuery):
    """Показывает список всех купонов."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка купонов")
    try:
        coupons = await db.coupons.get_all_coupons()
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка купонов: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not coupons:
        text = "📭 Список купонов пуст.\n\nДобавьте купон через меню."
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔙 Назад", callback_data="admin_coupons_menu")
        await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup())
        await callback.answer()
        return

    text = "🎫 <b>Список купонов:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for coup in coupons:
        status = "✅" if coup.is_active else "❌"
        expiry = coup.valid_to[:10] if coup.valid_to else "бессрочно"
        discount_type_str = "%" if coup.discount_type == "percent" else "₽"
        text += (
            f"{status} <b>{escape_html(coup.code)}</b>\n"
            f"   Скидка: {coup.discount_value}{discount_type_str} на "
            f"{'всю сумму' if coup.discount_on == 'order' else 'комиссию'}\n"
            f"   Использовано: {coup.used_count}/{coup.max_uses_total or '∞'}\n"
            f"   Мин. сумма: {coup.min_order_amount} ₽\n"
            f"   Действует до: {expiry}\n"
            f"   Описание: {escape_html(coup.description or '—')}\n\n"
        )
        if coup.is_active:
            keyboard.button(text=f"❌ Деактивировать {coup.code}", callback_data=f"admin_coupon_toggle_{coup.id}")
        else:
            keyboard.button(text=f"✅ Активировать {coup.code}", callback_data=f"admin_coupon_toggle_{coup.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_coupons_menu")
    keyboard.adjust(1)

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_coupon_toggle_"))
async def admin_coupon_toggle(callback: CallbackQuery):
    """Активация/деактивация купона."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        coupon_id = int(callback.data.split("_")[-1])
        logger.info(f"[ADMIN {admin_id}] Переключение активности купона ID {coupon_id}")
    except (IndexError, ValueError):
        logger.warning(f"[ADMIN {admin_id}] Некорректный формат данных: {callback.data}")
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    try:
        coupons = await db.coupons.get_all_coupons()
        coupon = next((c for c in coupons if c.id == coupon_id), None)
        if not coupon:
            await callback.answer("❌ Купон не найден", show_alert=True)
            return
        new_state = not coupon.is_active
        await db.coupons.toggle_coupon(coupon_id, new_state)
        await callback.answer(f"✅ Статус изменён", show_alert=True)
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при переключении статуса купона: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)
        return

    await admin_coupon_list(callback)