"""Обработчики админ-панели для финансов"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.crypto_api import crypto_api
from bot.services.admin_finance_service import AdminFinanceService
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_finance_menu")
async def admin_finance_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📊 Статистика", callback_data="admin_finance_stats")
    keyboard.button(text="📈 Графики", callback_data="admin_finance_charts")
    keyboard.button(text="➕ Добавить расход", callback_data="admin_finance_add_expense")
    keyboard.button(text="📋 История операций", callback_data="admin_finance_history")
    keyboard.button(text="🔄 Обновить курсы", callback_data="admin_finance_refresh_rates")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(2, 2, 1, 1)

    await callback.message.edit_text(
        "💰 <b>Финансовое меню</b>\n\nВыберите действие:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_finance_stats")
async def admin_finance_stats(callback: CallbackQuery, admin_finance_service: AdminFinanceService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    stats_24h = await admin_finance_service.get_financial_stats(days=1)
    stats_7d = await admin_finance_service.get_financial_stats(days=7)
    stats_30d = await admin_finance_service.get_financial_stats(days=30)

    text = (
        f"📊 <b>Финансовая статистика</b>\n\n"
        f"<b>За 24 часа:</b>\n"
        f"   💰 Выручка: {stats_24h['revenue']:,.0f} ₽\n"
        f"   📤 Расходы: {stats_24h['expenses']:,.0f} ₽\n"
        f"   📈 Прибыль: {stats_24h['profit']:,.0f} ₽\n"
        f"   🔄 Оборот: {stats_24h['trading_volume']:,.0f} ₽\n\n"
        f"<b>За 7 дней:</b>\n"
        f"   💰 Выручка: {stats_7d['revenue']:,.0f} ₽\n"
        f"   📤 Расходы: {stats_7d['expenses']:,.0f} ₽\n"
        f"   📈 Прибыль: {stats_7d['profit']:,.0f} ₽\n"
        f"   🔄 Оборот: {stats_7d['trading_volume']:,.0f} ₽\n\n"
        f"<b>За 30 дней:</b>\n"
        f"   💰 Выручка: {stats_30d['revenue']:,.0f} ₽\n"
        f"   📤 Расходы: {stats_30d['expenses']:,.0f} ₽\n"
        f"   📈 Прибыль: {stats_30d['profit']:,.0f} ₽\n"
        f"   🔄 Оборот: {stats_30d['trading_volume']:,.0f} ₽\n\n"
        f"<b>Маржинальность:</b> {(stats_30d['profit'] / stats_30d['revenue'] * 100) if stats_30d['revenue'] > 0 else 0:.1f}%"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_finance_menu")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_finance_charts")
async def admin_finance_charts(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_finance_menu")

    await callback.message.edit_text(
        "📈 Функция построения графиков находится в разработке.\n\n"
        "Пока вы можете посмотреть статистику в разделе «📊 Статистика».",
        reply_markup=keyboard.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_finance_history")
async def admin_finance_history(callback: CallbackQuery, admin_finance_service: AdminFinanceService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    records = await admin_finance_service.get_recent_records(limit=20)

    if not records:
        await callback.message.edit_text(
            "📭 История операций пуста.",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_finance_menu").as_markup()
        )
        await callback.answer()
        return

    text = "📋 <b>Последние финансовые операции:</b>\n\n"
    for rec in records:
        emoji = {
            'income': '💰',
            'expense': '📤',
            'profit': '📈'
        }.get(rec.record_type, '🔄')

        sign = '+' if rec.record_type in ('income', 'profit') else '-'
        amount_str = f"{sign}{rec.amount:,.0f} ₽"

        text += (
            f"{emoji} <b>{rec.category}</b>\n"
            f"   {amount_str} | {rec.created_at[:16]}\n"
            f"   {rec.description or '—'}\n"
            f"   {rec.currency}\n\n"
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_finance_menu")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_finance_add_expense")
async def admin_add_expense_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.adding_expense)

    await callback.message.edit_text(
        "➕ <b>Добавление расхода</b>\n\n"
        "Введите сумму расхода в рублях:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.adding_expense)
async def admin_add_expense_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", "."))
        await state.update_data(expense_amount=amount)
        await state.set_state(AdminStates.adding_expense_desc)

        await message.answer("Введите описание расхода:")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


@router.message(AdminStates.adding_expense_desc)
async def admin_add_expense_desc(message: Message, state: FSMContext, admin_finance_service: AdminFinanceService):
    data = await state.get_data()
    amount = data.get('expense_amount')
    description = message.text

    await admin_finance_service.add_expense(amount, description, message.from_user.id)

    await message.answer(
        f"✅ Расход добавлен:\n\n"
        f"Сумма: {amount:,.0f} ₽\n"
        f"Описание: {description}",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К финансам", callback_data="admin_finance_menu").as_markup()
    )
    await state.clear()


@router.callback_query(F.data == "admin_finance_refresh_rates")
async def admin_finance_refresh_rates(callback: CallbackQuery, admin_finance_service: AdminFinanceService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔄 Обновляю курсы...", show_alert=False)

    prices = await admin_finance_service.get_exchange_rates(force_refresh=True)

    text = (
        "✅ <b>Курсы успешно обновлены!</b>\n\n"
        f"₿ BTC: {prices['BTC']:,.0f} ₽\n"
        f"Ł LTC: {prices['LTC']:,.0f} ₽\n\n"
        f"Время обновления: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_finance_menu")

    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")