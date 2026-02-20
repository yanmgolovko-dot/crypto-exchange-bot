"""Обработчики админ-панели для настроек"""

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
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    fee = await db.get_exchange_fee()
    min_amount = await db.get_setting('min_amount', str(config.MIN_AMOUNT))
    max_amount = await db.get_setting('max_amount', str(config.MAX_AMOUNT))
    payment_mode = await db.get_payment_mode()
    mode_text = "Автоматический" if payment_mode == 'auto' else "Ручной"
    payment_source = await db.get_manual_payment_source()
    source_text = "Из БД" if payment_source == 'auto' else "Вручную"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=f"💰 Комиссия ({fee}%)", callback_data="admin_set_fee")
    keyboard.button(text=f"📉 Мин. сумма ({min_amount} ₽)", callback_data="admin_set_min")
    keyboard.button(text=f"📈 Макс. сумма ({max_amount} ₽)", callback_data="admin_set_max")
    keyboard.button(text=f"🔄 Режим оплаты: {mode_text}", callback_data="admin_toggle_payment_mode")
    keyboard.button(text=f"💳 Ручной режим: реквизиты {source_text}", callback_data="admin_toggle_payment_source")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await callback.message.edit_text(
        "⚙️ <b>Настройки обменника</b>\n\n"
        f"Текущая комиссия: {fee}%\n"
        f"Мин. сумма обмена: {min_amount} ₽\n"
        f"Макс. сумма обмена: {max_amount} ₽\n"
        f"Режим оплаты: {mode_text}\n"
        f"Ручной режим: реквизиты {'из БД' if payment_source == 'auto' else 'вводятся вручную'}\n\n"
        "Выберите настройку для изменения:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_min")
async def admin_set_min_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_min = await db.get_setting('min_amount', str(config.MIN_AMOUNT))

    await state.set_state(AdminStates.changing_min)
    await callback.message.edit_text(
        f"📉 <b>Изменение минимальной суммы</b>\n\n"
        f"Текущая минимальная сумма: {current_min} ₽\n\n"
        f"Введите новую минимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_min)
async def admin_set_min_finish(message: Message, state: FSMContext):
    try:
        new_min = float(message.text.replace(" ", ""))
        if new_min < 0:
            await message.answer("❌ Сумма не может быть отрицательной.")
            return
        await db.set_setting('min_amount', str(int(new_min)), message.from_user.id)
        await message.answer(
            f"✅ Минимальная сумма изменена на {int(new_min):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К настройкам", callback_data="admin_settings_menu"
            ).as_markup()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректное число.")


@router.callback_query(F.data == "admin_set_max")
async def admin_set_max_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_max = await db.get_setting('max_amount', str(config.MAX_AMOUNT))

    await state.set_state(AdminStates.changing_max)
    await callback.message.edit_text(
        f"📈 <b>Изменение максимальной суммы</b>\n\n"
        f"Текущая максимальная сумма: {current_max} ₽\n\n"
        f"Введите новую максимальную сумму в рублях (целое число):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_max)
async def admin_set_max_finish(message: Message, state: FSMContext):
    try:
        new_max = float(message.text.replace(" ", ""))
        if new_max < 0:
            await message.answer("❌ Сумма не может быть отрицательной.")
            return
        await db.set_setting('max_amount', str(int(new_max)), message.from_user.id)
        await message.answer(
            f"✅ Максимальная сумма изменена на {int(new_max):,} ₽".replace(",", " "),
            reply_markup=InlineKeyboardBuilder().button(
                text="🔙 К настройкам", callback_data="admin_settings_menu"
            ).as_markup()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректное число.")


@router.callback_query(F.data == "admin_toggle_payment_mode")
async def admin_toggle_payment_mode(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_mode = await db.get_payment_mode()
    new_mode = 'manual' if current_mode == 'auto' else 'auto'
    await db.set_payment_mode(new_mode, callback.from_user.id)

    await callback.answer(f"Режим изменён на {'Ручной' if new_mode == 'manual' else 'Автоматический'}", show_alert=True)
    await admin_settings_menu(callback)


@router.callback_query(F.data == "admin_set_fee")
async def admin_set_fee_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_fee = await db.get_exchange_fee()

    await state.set_state(AdminStates.changing_fee)

    await callback.message.edit_text(
        f"💰 <b>Изменение комиссии</b>\n\n"
        f"Текущая комиссия: {current_fee}%\n\n"
        f"Введите новую комиссию в процентах (например: 2.5):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.changing_fee)
async def admin_set_fee_finish(message: Message, state: FSMContext):
    try:
        new_fee = float(message.text.replace(",", "."))

        if new_fee < 0 or new_fee > 50:
            await message.answer("❌ Комиссия должна быть от 0 до 50%")
            return

        await db.set_exchange_fee(new_fee, message.from_user.id)

        await message.answer(
            f"✅ Комиссия изменена на {new_fee}%",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К настройкам", callback_data="admin_settings_menu").as_markup()
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


@router.callback_query(F.data == "admin_toggle_payment_source")
async def admin_toggle_payment_source(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current = await db.get_manual_payment_source()
    new_source = 'auto' if current == 'manual' else 'manual'
    await db.set_manual_payment_source(new_source, callback.from_user.id)
    await callback.answer(f"Источник реквизитов изменён на {'Из БД' if new_source == 'auto' else 'Вручную'}", show_alert=True)
    await admin_settings_menu(callback)