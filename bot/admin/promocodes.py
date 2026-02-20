"""Обработчики админ-панели для управления промокодами"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_promo_menu")
async def admin_promo_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    promos = await db.get_all_promo_codes()
    active_count = sum(1 for p in promos if p.is_active)

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Создать промокод", callback_data="admin_promo_create")
    keyboard.button(text="📋 Список промокодов", callback_data="admin_promo_list")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    await callback.message.edit_text(
        f"🎁 <b>Управление акциями</b>\n\n"
        f"Всего промокодов: {len(promos)}\n"
        f"Активных: {active_count}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.creating_promo_code)

    await callback.message.edit_text(
        "🎁 <b>Создание промокода</b>\n\n"
        "Введите код промокода (например: SUMMER2024):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.creating_promo_code)
async def admin_promo_discount(message: Message, state: FSMContext):
    code = message.text.strip().upper()

    if len(code) < 3:
        await message.answer("❌ Код должен быть не менее 3 символов")
        return

    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.creating_promo_discount)

    await message.answer("Введите размер скидки в процентах (например: 5):")


@router.message(AdminStates.creating_promo_discount)
async def admin_promo_uses(message: Message, state: FSMContext):
    try:
        discount = float(message.text.replace(",", "."))

        if discount <= 0 or discount > 50:
            await message.answer("❌ Скидка должна быть от 0.1 до 50%")
            return

        await state.update_data(promo_discount=discount)
        await state.set_state(AdminStates.creating_promo_uses)

        await message.answer("Введите максимальное количество использований (например: 100):")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


@router.message(AdminStates.creating_promo_uses)
async def admin_promo_days(message: Message, state: FSMContext):
    try:
        uses = int(message.text)

        if uses <= 0:
            await message.answer("❌ Количество должно быть больше 0")
            return

        await state.update_data(promo_uses=uses)
        await state.set_state(AdminStates.creating_promo_days)

        await message.answer("Введите срок действия в днях (например: 30):")
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


@router.message(AdminStates.creating_promo_days)
async def admin_promo_finish(message: Message, state: FSMContext):
    try:
        days = int(message.text)

        if days <= 0:
            await message.answer("❌ Срок должен быть больше 0")
            return

        data = await state.get_data()

        promo_id = await db.create_promo_code(
            code=data['promo_code'],
            discount_percent=data['promo_discount'],
            max_uses=data['promo_uses'],
            valid_days=days,
            created_by=message.from_user.id,
            description=f"Создано админом {message.from_user.id}"
        )

        await message.answer(
            f"✅ Промокод создан!\n\n"
            f"Код: <code>{data['promo_code']}</code>\n"
            f"Скидка: {data['promo_discount']}%\n"
            f"Использований: {data['promo_uses']}\n"
            f"Срок: {days} дней",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К акциям", callback_data="admin_promo_menu").as_markup(),
            parse_mode="HTML"
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")