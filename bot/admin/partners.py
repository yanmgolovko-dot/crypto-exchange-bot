# bot/admin/partners.py
"""Админ-панель для управления партнёрской программой."""

import logging
import json
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.partner_service import partner_service
from bot.admin.main import is_admin
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()


class AdminPartnerStates(StatesGroup):
    # Состояния для редактирования настроек
    editing_enabled = State()
    editing_max_levels = State()
    editing_level_reward_level = State()
    editing_level_reward_type = State()
    editing_level_reward_value = State()
    editing_commission_source = State()
    editing_min_withdraw = State()
    editing_withdraw_fee_type = State()
    editing_withdraw_fee_value = State()
    editing_auto_approve = State()
    # Состояния для добавления партнёра
    adding_partner = State()


async def partners_main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Настройки программы", callback_data="admin_partners_settings")
    kb.button(text="📋 Список партнёров", callback_data="admin_partners_list")
    kb.button(text="💸 Заявки на вывод", callback_data="admin_partners_withdrawals")
    kb.button(text="➕ Добавить партнёра", callback_data="admin_partners_add")
    kb.button(text="🔙 Назад", callback_data="admin_back_main")
    kb.adjust(1)
    return kb.as_markup()


async def send_partners_menu(user_id: int, bot: Bot):
    """Отправляет пользователю главное меню партнёрской программы (новым сообщением)."""
    text = (
        "🤝 <b>Партнёрская программа</b>\n\n"
        "Управление партнёрами, настройками и выплатами."
    )
    kb = await partners_main_keyboard()
    await bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_partners_menu")
async def admin_partners_menu(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    text = (
        "🤝 <b>Партнёрская программа</b>\n\n"
        "Управление партнёрами, настройками и выплатами."
    )
    kb = await partners_main_keyboard()
    await safe_edit_message(callback.message, text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ==================== НАСТРОЙКИ ====================
@router.callback_query(F.data == "admin_partners_settings")
async def admin_partners_settings(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    settings = await db.partners.get_settings()
    # Форматируем награды для отображения
    rewards_text = ""
    for reward in settings.level_rewards:
        reward_type = "процент" if reward['type'] == 'percent' else "фикс."
        rewards_text += f"  Уровень {reward['level']}: {reward['value']}{'%' if reward['type'] == 'percent' else '₽'}\n"

    text = (
        f"⚙️ <b>Настройки партнёрской программы</b>\n\n"
        f"Включена: {'✅' if settings.enabled else '❌'}\n"
        f"Макс. уровней: {settings.max_levels}\n"
        f"Награды по уровням:\n{rewards_text}"
        f"Источник комиссии: {'fee (комиссия)' if settings.commission_source == 'fee' else 'order (сумма заказа)'}\n"
        f"Мин. вывод: {settings.min_withdraw} ₽\n"
        f"Комиссия за вывод: {settings.withdraw_fee}{'%' if settings.withdraw_fee_type == 'percent' else '₽'}\n"
        f"Автоодобрение: {'✅' if settings.auto_approve else '❌'}\n"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редактировать", callback_data="admin_partners_edit_settings")
    kb.button(text="🔙 Назад", callback_data="admin_partners_menu")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_partners_edit_settings")
async def admin_partners_edit_settings_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    settings = await db.partners.get_settings()
    await state.update_data(settings=settings, current_level=1, rewards=settings.level_rewards)
    await state.set_state(AdminPartnerStates.editing_enabled)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Включить", callback_data="partner_set_enabled_1")
    kb.button(text="❌ Выключить", callback_data="partner_set_enabled_0")
    kb.button(text="🔙 Отмена", callback_data="admin_partners_settings")
    kb.adjust(2, 1)
    await safe_edit_message(
        callback.message,
        "⚙️ <b>Редактирование настроек</b>\n\nВключить партнёрскую программу?",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(AdminPartnerStates.editing_enabled, F.data.startswith("partner_set_enabled_"))
async def partner_set_enabled(callback: CallbackQuery, state: FSMContext):
    enabled = bool(int(callback.data.split("_")[-1]))
    data = await state.get_data()
    settings = data['settings']
    settings.enabled = enabled
    await state.update_data(settings=settings)
    await state.set_state(AdminPartnerStates.editing_max_levels)
    await safe_edit_message(
        callback.message,
        f"⚙️ Введите максимальное количество уровней (сейчас {settings.max_levels}):"
    )
    await callback.answer()


@router.message(AdminPartnerStates.editing_max_levels)
async def partner_set_max_levels(message: Message, state: FSMContext):
    try:
        max_levels = int(message.text.strip())
        if max_levels <= 0 or max_levels > 20:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число от 1 до 20.")
        return
    data = await state.get_data()
    settings = data['settings']
    settings.max_levels = max_levels
    await state.update_data(settings=settings)
    await state.set_state(AdminPartnerStates.editing_level_reward_level)
    await message.answer(
        f"⚙️ Теперь настройте вознаграждения для каждого уровня.\n"
        f"Начнём с уровня 1. Введите тип вознаграждения:\n"
        f"• percent – процент от комиссии\n"
        f"• fixed – фиксированная сумма в рублях"
    )


@router.message(AdminPartnerStates.editing_level_reward_level)
async def partner_set_reward_type(message: Message, state: FSMContext):
    reward_type = message.text.strip().lower()
    if reward_type not in ('percent', 'fixed'):
        await message.answer("❌ Введите 'percent' или 'fixed'.")
        return
    await state.update_data(reward_type=reward_type)
    await state.set_state(AdminPartnerStates.editing_level_reward_value)
    await message.answer("Введите значение вознаграждения (например, 10 для 10% или 100 для 100₽):")


@router.message(AdminPartnerStates.editing_level_reward_value)
async def partner_set_reward_value(message: Message, state: FSMContext):
    try:
        value = float(message.text.replace(",", "."))
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    data = await state.get_data()
    current_level = data.get('current_level', 1)
    reward_type = data['reward_type']
    rewards = data.get('rewards', [])

    # Добавляем или обновляем награду для текущего уровня
    rewards = [r for r in rewards if r['level'] != current_level]
    rewards.append({
        'level': current_level,
        'type': reward_type,
        'value': value
    })
    # Сортируем по уровню
    rewards.sort(key=lambda x: x['level'])
    await state.update_data(rewards=rewards)

    # Переходим к следующему уровню или завершаем
    max_levels = data['settings'].max_levels
    if current_level < max_levels:
        next_level = current_level + 1
        await state.update_data(current_level=next_level)
        await state.set_state(AdminPartnerStates.editing_level_reward_level)
        await message.answer(
            f"✅ Уровень {current_level} сохранён.\n"
            f"Теперь настройте уровень {next_level}. Введите тип вознаграждения (percent/fixed):"
        )
    else:
        # Все уровни настроены, переходим к следующему параметру
        await state.set_state(AdminPartnerStates.editing_commission_source)
        kb = InlineKeyboardBuilder()
        kb.button(text="fee (комиссия)", callback_data="partner_commission_fee")
        kb.button(text="order (сумма заказа)", callback_data="partner_commission_order")
        kb.button(text="🔙 Отмена", callback_data="admin_partners_settings")
        kb.adjust(2, 1)
        await message.answer(
            "⚙️ Выберите источник для начисления:",
            reply_markup=kb.as_markup()
        )


@router.callback_query(AdminPartnerStates.editing_commission_source, F.data.startswith("partner_commission_"))
async def partner_set_commission_source(callback: CallbackQuery, state: FSMContext):
    source = callback.data.split("_")[-1]  # fee или order
    data = await state.get_data()
    settings = data['settings']
    settings.commission_source = source
    await state.update_data(settings=settings)
    await state.set_state(AdminPartnerStates.editing_min_withdraw)
    await safe_edit_message(
        callback.message,
        f"⚙️ Введите минимальную сумму для вывода в рублях (сейчас {settings.min_withdraw}):"
    )
    await callback.answer()


@router.message(AdminPartnerStates.editing_min_withdraw)
async def partner_set_min_withdraw(message: Message, state: FSMContext):
    try:
        min_withdraw = float(message.text.replace(",", "."))
        if min_withdraw < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число (неотрицательное).")
        return
    data = await state.get_data()
    settings = data['settings']
    settings.min_withdraw = min_withdraw
    await state.update_data(settings=settings)
    await state.set_state(AdminPartnerStates.editing_withdraw_fee_type)
    kb = InlineKeyboardBuilder()
    kb.button(text="Процент (%)", callback_data="partner_fee_type_percent")
    kb.button(text="Фиксированная сумма (₽)", callback_data="partner_fee_type_fixed")
    kb.button(text="🔙 Отмена", callback_data="admin_partners_settings")
    kb.adjust(2, 1)
    await message.answer(
        "⚙️ Выберите тип комиссии за вывод:",
        reply_markup=kb.as_markup()
    )


@router.callback_query(AdminPartnerStates.editing_withdraw_fee_type, F.data.startswith("partner_fee_type_"))
async def partner_set_fee_type(callback: CallbackQuery, state: FSMContext):
    fee_type = callback.data.split("_")[-1]  # percent или fixed
    await state.update_data(fee_type=fee_type)
    await state.set_state(AdminPartnerStates.editing_withdraw_fee_value)
    await safe_edit_message(
        callback.message,
        f"⚙️ Введите значение комиссии за вывод:"
    )
    await callback.answer()


@router.message(AdminPartnerStates.editing_withdraw_fee_value)
async def partner_set_fee_value(message: Message, state: FSMContext):
    try:
        fee_value = float(message.text.replace(",", "."))
        if fee_value < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число (неотрицательное).")
        return
    data = await state.get_data()
    settings = data['settings']
    settings.withdraw_fee = fee_value
    settings.withdraw_fee_type = data['fee_type']
    await state.update_data(settings=settings)
    await state.set_state(AdminPartnerStates.editing_auto_approve)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data="partner_auto_approve_1")
    kb.button(text="❌ Нет", callback_data="partner_auto_approve_0")
    kb.button(text="🔙 Отмена", callback_data="admin_partners_settings")
    kb.adjust(2, 1)
    await message.answer(
        "⚙️ Автоматически одобрять выводы?",
        reply_markup=kb.as_markup()
    )


@router.callback_query(AdminPartnerStates.editing_auto_approve, F.data.startswith("partner_auto_approve_"))
async def partner_set_auto_approve(callback: CallbackQuery, state: FSMContext):
    auto_approve = bool(int(callback.data.split("_")[-1]))
    data = await state.get_data()
    settings = data['settings']
    settings.auto_approve = auto_approve
    # Сохраняем все настройки
    new_settings = {
        'enabled': settings.enabled,
        'max_levels': settings.max_levels,
        'level_rewards': json.dumps(data['rewards']),
        'commission_source': settings.commission_source,
        'min_withdraw': settings.min_withdraw,
        'withdraw_fee': settings.withdraw_fee,
        'withdraw_fee_type': settings.withdraw_fee_type,
        'auto_approve': settings.auto_approve
    }
    await db.partners.update_settings(new_settings)
    await safe_edit_message(callback.message, "✅ Настройки сохранены.")
    await state.clear()
    # Возвращаемся в меню настроек
    await admin_partners_settings(callback)


# ==================== СПИСОК ПАРТНЁРОВ ====================
@router.callback_query(F.data == "admin_partners_list")
async def admin_partners_list(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    partners = await db.partners.get_all_partners()
    if not partners:
        text = "📋 Список партнёров пуст."
    else:
        text = "📋 <b>Список партнёров</b>\n\n"
        for p in partners:
            user = await db.get_user(p.user_id)
            username = user.username if user and user.username else str(p.user_id)
            text += (
                f"• {escape_html(username)}\n"
                f"  Баланс: {p.balance:.2f} ₽\n"
                f"  Всего заработано: {p.total_earned:.2f} ₽\n"
                f"  Уровень: {p.level}\n"
                f"  Активен: {'✅' if p.is_active else '❌'}\n\n"
            )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_partners_menu")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== ЗАЯВКИ НА ВЫВОД ====================
@router.callback_query(F.data == "admin_partners_withdrawals")
async def admin_partners_withdrawals(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    requests = await db.partners.get_pending_withdraw_requests()
    if not requests:
        text = "💸 Нет заявок на вывод."
    else:
        text = "💸 <b>Заявки на вывод</b>\n\n"
        for req in requests:
            user = await db.get_user(req.user_id)
            username = user.username if user and user.username else str(req.user_id)
            text += (
                f"#{req.id} от {escape_html(username)}\n"
                f"Сумма: {req.amount} ₽\n"
                f"Способ: {escape_html(req.payment_method or '')}\n"
                f"Реквизиты: {escape_html(req.payment_details or '')}\n"
                f"Дата: {req.created_at}\n"
                f"Статус: {req.status}\n\n"
            )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_partners_menu")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== ДОБАВЛЕНИЕ ПАРТНЁРА ====================
@router.callback_query(F.data == "admin_partners_add")
async def admin_partners_add_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminPartnerStates.adding_partner)
    await safe_edit_message(
        callback.message,
        "➕ <b>Добавление партнёра</b>\n\nВведите ID пользователя (целое число), которого хотите сделать партнёром:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminPartnerStates.adding_partner)
async def admin_partners_add_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await is_admin(admin_id):
        await message.answer("⛔ Нет доступа.")
        await state.clear()
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")
        return

    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь с таким ID не найден.")
        return

    existing = await db.partners.get_partner(user_id)
    if existing:
        await message.answer("❌ Этот пользователь уже является партнёром.")
        return

    await db.partners.add_partner(user_id, f"PARTNER{user_id}")
    await message.answer(f"✅ Пользователь {user_id} назначен партнёром.")
    await state.clear()

    # Возвращаемся в меню партнёров
    await send_partners_menu(message.from_user.id, message.bot)