# bot/admin/promocodes.py
"""Обработчики админ-панели для управления промокодами."""

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


@router.callback_query(F.data == "admin_promo_menu")
async def admin_promo_menu(callback: CallbackQuery):
    """Меню управления промокодами."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа к меню промокодов без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Открыто меню управления промокодами")

    try:
        promos = await db.get_all_promo_codes()
        active_count = sum(1 for p in promos if p.is_active)
        logger.debug(f"Всего промокодов: {len(promos)}, активных: {active_count}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка промокодов: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Создать промокод", callback_data="admin_promo_create")
    keyboard.button(text="📋 Список промокодов", callback_data="admin_promo_list")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    text = (
        f"🎁 <b>Управление акциями</b>\n\n"
        f"Всего промокодов: {len(promos)}\n"
        f"Активных: {active_count}\n\n"
        f"Выберите действие:"
    )

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промокода (запрос кода)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Начало создания промокода")
    await state.set_state(AdminStates.creating_promo_code)

    text = "🎁 <b>Создание промокода</b>\n\nВведите код промокода (например: SUMMER2024):"
    await safe_edit_message(callback.message, text, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.creating_promo_code)
async def admin_promo_discount(message: Message, state: FSMContext):
    """Обработка введённого кода, запрос скидки."""
    admin_id = message.from_user.id
    code = message.text.strip().upper()

    logger.info(f"[ADMIN {admin_id}] Ввод кода промокода: {code}")
    if len(code) < 3:
        logger.warning(f"[ADMIN {admin_id}] Слишком короткий код: {code}")
        await message.answer("❌ Код должен быть не менее 3 символов")
        return

    await state.update_data(promo_code=code)
    await state.set_state(AdminStates.creating_promo_discount)
    await message.answer("Введите размер скидки в процентах (0-100, например 10 или 100 для бесплатного обмена):")


@router.message(AdminStates.creating_promo_discount)
async def admin_promo_uses(message: Message, state: FSMContext):
    """Обработка скидки, запрос количества использований."""
    admin_id = message.from_user.id
    try:
        discount = float(message.text.replace(",", "."))
        logger.info(f"[ADMIN {admin_id}] Ввод скидки: {discount}%")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод скидки: {message.text}")
        await message.answer("❌ Пожалуйста, введите корректное число:")
        return

    if discount < 0 or discount > 100:
        logger.warning(f"[ADMIN {admin_id}] Скидка вне допустимого диапазона: {discount}")
        await message.answer("❌ Скидка должна быть от 0 до 100%")
        return

    await state.update_data(promo_discount=discount)
    await state.set_state(AdminStates.creating_promo_uses)
    await message.answer("Введите максимальное количество использований (например: 100):")


@router.message(AdminStates.creating_promo_uses)
async def admin_promo_days(message: Message, state: FSMContext):
    """Обработка количества использований, запрос срока действия."""
    admin_id = message.from_user.id
    try:
        uses = int(message.text)
        logger.info(f"[ADMIN {admin_id}] Ввод количества использований: {uses}")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод числа использований: {message.text}")
        await message.answer("❌ Пожалуйста, введите корректное число:")
        return

    if uses <= 0:
        logger.warning(f"[ADMIN {admin_id}] Количество использований должно быть >0: {uses}")
        await message.answer("❌ Количество должно быть больше 0")
        return

    await state.update_data(promo_uses=uses)
    await state.set_state(AdminStates.creating_promo_days)
    await message.answer("Введите срок действия в днях (например: 30):")


@router.message(AdminStates.creating_promo_days)
async def admin_promo_finish(message: Message, state: FSMContext):
    """Обработка срока действия и создание промокода в БД."""
    admin_id = message.from_user.id
    try:
        days = int(message.text)
        logger.info(f"[ADMIN {admin_id}] Ввод срока действия: {days} дней")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод числа дней: {message.text}")
        await message.answer("❌ Пожалуйста, введите корректное число:")
        return

    if days <= 0:
        logger.warning(f"[ADMIN {admin_id}] Срок действия должен быть >0: {days}")
        await message.answer("❌ Срок должен быть больше 0")
        return

    data = await state.get_data()
    logger.info(f"[ADMIN {admin_id}] Создание промокода в БД")

    try:
        promo_id = await db.create_promo_code(
            code=data['promo_code'],
            discount_percent=data['promo_discount'],
            max_uses=data['promo_uses'],
            valid_days=days,
            created_by=admin_id,
            description=f"Создано админом {admin_id}"
        )
        logger.info(f"[ADMIN {admin_id}] Промокод создан, ID: {promo_id}")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при создании промокода: {e}", exc_info=True)
        await message.answer("❌ Ошибка при создании промокода. Возможно, код уже существует.")
        await state.clear()
        return

    text = (
        f"✅ Промокод создан!\n\n"
        f"Код: <code>{escape_html(data['promo_code'])}</code>\n"
        f"Скидка: {data['promo_discount']}%\n"
        f"Использований: {data['promo_uses']}\n"
        f"Срок: {days} дней"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 К акциям", callback_data="admin_promo_menu")
    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "admin_promo_list")
async def admin_promo_list(callback: CallbackQuery):
    """Показывает список всех промокодов."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка промокодов")

    try:
        promos = await db.get_all_promo_codes()
        logger.debug(f"Получено {len(promos)} промокодов")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при получении списка промокодов: {e}", exc_info=True)
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    if not promos:
        text = "📭 Список промокодов пуст.\n\nДобавьте промокод через меню."
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔙 Назад", callback_data="admin_promo_menu")
        await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup())
        await callback.answer()
        return

    text = "🎁 <b>Список промокодов:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        expiry = promo.valid_to[:10] if promo.valid_to else "бессрочно"
        text += (
            f"{status} <b>{escape_html(promo.code)}</b>\n"
            f"   Скидка: {promo.discount_percent}%\n"
            f"   Использовано: {promo.used_count}/{promo.max_uses}\n"
            f"   Действует до: {expiry}\n"
            f"   Описание: {escape_html(promo.description or '—')}\n\n"
        )
        if promo.is_active:
            keyboard.button(text=f"❌ Деактивировать {promo.code}", callback_data=f"admin_promo_toggle_{promo.id}")
        else:
            keyboard.button(text=f"✅ Активировать {promo.code}", callback_data=f"admin_promo_toggle_{promo.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_promo_menu")
    keyboard.adjust(1)

    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_toggle_"))
async def admin_promo_toggle(callback: CallbackQuery):
    """Активация/деактивация промокода."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        promo_id = int(callback.data.split("_")[-1])
        logger.info(f"[ADMIN {admin_id}] Переключение активности промокода ID {promo_id}")
    except (IndexError, ValueError):
        logger.warning(f"[ADMIN {admin_id}] Некорректный формат данных: {callback.data}")
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    try:
        promos = await db.get_all_promo_codes()
        promo = next((p for p in promos if p.id == promo_id), None)
        if not promo:
            logger.warning(f"[ADMIN {admin_id}] Промокод ID {promo_id} не найден")
            await callback.answer("❌ Промокод не найден", show_alert=True)
            return

        new_state = not promo.is_active
        await db.toggle_promo_code(promo_id, new_state)
        logger.info(f"[ADMIN {admin_id}] Промокод ID {promo_id} теперь {'активен' if new_state else 'неактивен'}")
        await callback.answer(f"✅ Статус изменён", show_alert=True)
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка при переключении статуса промокода: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)
        return

    await admin_promo_list(callback)