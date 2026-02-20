# bot/handlers/profile.py
"""
Обработчики для личного кабинета пользователя.
Отображают информацию о пользователе, статистику, бонусы, промокоды,
реферальную программу и настройки.
"""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.crypto_api import crypto_api
from bot.keyboards import main_menu_keyboard

# Настройка логгера для текущего модуля
logger = logging.getLogger(__name__)
router = Router()


def user_profile_keyboard():
    """
    Создаёт инлайн-клавиатуру для разделов личного кабинета.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📊 Моя статистика", callback_data="user_stats")
    keyboard.button(text="💰 Бонусный баланс", callback_data="user_bonus")
    keyboard.button(text="🎁 Мои промокоды", callback_data="user_promos")
    keyboard.button(text="🔗 Реферальная программа", callback_data="user_referral")
    keyboard.button(text="⚙️ Настройки", callback_data="user_settings")
    keyboard.button(text="🔙 Главное меню", callback_data="user_back_main")
    keyboard.adjust(1)
    return keyboard.as_markup()


@router.message(Command("profile"))
@router.message(F.text == "👤 Личный кабинет")
async def cmd_profile(message: Message):
    """
    Обработчик команды /profile или нажатия кнопки «👤 Личный кабинет».
    Отображает основную информацию о пользователе и статистику.
    """
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Открыт личный кабинет")

    # Получаем пользователя из БД (если не существует, создаём)
    user = await db.get_user(user_id)
    if not user:
        logger.info(f"[{user_id}] Пользователь не найден в БД, создаём запись")
        await db.add_or_update_user(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        user = await db.get_user(user_id)
        logger.info(f"[{user_id}] Запись пользователя создана")

    # Проверяем, не забанен ли пользователь
    is_banned, ban_reason = await db.is_user_banned(user_id)
    if is_banned:
        logger.warning(f"[{user_id}] Попытка доступа забаненным пользователем")
        await message.answer(
            f"🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
            f"Причина: {ban_reason}\n\n"
            f"Для разблокировки обратитесь в поддержку.",
            parse_mode="HTML"
        )
        return

    # Получаем статистику пользователя
    stats = await db.get_user_stats(user_id)
    prices = await crypto_api.get_all_prices()

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"<b>Информация:</b>\n"
        f"   ID: <code>{user.user_id}</code>\n"
        f"   Имя: {user.first_name or 'Не указано'}\n"
        f"   Дата регистрации: {user.created_at[:10] if user.created_at else 'N/A'}\n\n"
        f"<b>Статистика:</b>\n"
        f"   Всего обменов: {stats['total_orders']}\n"
        f"   Общий объем: {stats['total_volume']:,.0f} ₽\n"
        f"   Сэкономлено: {stats['total_saved']:,.0f} ₽\n\n"
        f"<b>Бонусы:</b>\n"
        f"   Баланс: {user.bonus_balance:,.0f} ₽\n\n"
    )

    if user.referral_code:
        text += f"<b>Реферальный код:</b> <code>{user.referral_code}</code>\n\n"

    text += "Выберите раздел:"

    await message.answer(text, reply_markup=user_profile_keyboard(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Информация профиля отправлена")


@router.callback_query(F.data == "user_stats")
async def user_stats(callback: CallbackQuery):
    """
    Показывает подробную статистику пользователя и последние заявки.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Запрошена статистика")

    stats = await db.get_user_stats(user_id)
    orders = await db.get_user_orders(user_id, limit=5)

    text = (
        f"📊 <b>Моя статистика</b>\n\n"
        f"<b>Общая информация:</b>\n"
        f"   Всего обменов: {stats['total_orders']}\n"
        f"   Общий объем: {stats['total_volume']:,.0f} ₽\n"
        f"   Сэкономлено на скидках: {stats['total_saved']:,.0f} ₽\n\n"
    )

    if orders:
        text += "<b>Последние заявки:</b>\n"
        for order in orders:
            status_emoji = {
                "pending": "⏳",
                "paid": "💳",
                "completed": "✅",
                "cancelled": "❌"
            }.get(order.status, "❓")

            status_text = {
                "pending": "Ожидает оплаты",
                "paid": "На проверке",
                "completed": "Выполнена",
                "cancelled": "Отменена"
            }.get(order.status, "Неизвестно")

            text += (
                f"{status_emoji} <b>#{order.id}</b> | {order.crypto_type}\n"
                f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f}\n"
                f"   Статус: {status_text}\n"
                f"   Дата: {order.created_at[:10] if order.created_at else 'N/A'}\n\n"
            )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Статистика отправлена")
    await callback.answer()


@router.callback_query(F.data == "user_bonus")
async def user_bonus(callback: CallbackQuery):
    """
    Показывает бонусный баланс и информацию о том, как его заработать.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Запрошен бонусный баланс")

    user = await db.get_user(user_id)
    if not user:
        logger.error(f"[{user_id}] Пользователь не найден в БД при запросе бонусов")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    text = (
        f"💰 <b>Бонусный баланс</b>\n\n"
        f"Текущий баланс: <b>{user.bonus_balance:,.0f} ₽</b>\n\n"
        f"<b>Как заработать бонусы?</b>\n"
        f"• Приглашайте друзей по реферальной ссылке\n"
        f"• Используйте промокоды\n"
        f"• Совершайте обмены\n\n"
        f"<b>Как использовать?</b>\n"
        f"Бонусы автоматически применяются при обмене и уменьшают комиссию."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔗 Реферальная программа", callback_data="user_referral")
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Информация о бонусах отправлена")
    await callback.answer()


@router.callback_query(F.data == "user_promos")
async def user_promos(callback: CallbackQuery):
    """
    Показывает список доступных и использованных промокодов.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Запрошен список промокодов")

    try:
        all_promos = await db.get_all_promo_codes()
        used_promo_ids = await db.get_user_used_promo_ids(user_id)
        used_promo_ids = set(used_promo_ids)

        now = datetime.now().isoformat()
        available = []
        used = []

        for promo in all_promos:
            if not promo.is_active:
                continue
            if promo.valid_to and promo.valid_to < now:
                continue

            if promo.id in used_promo_ids:
                used.append(promo)
            else:
                available.append(promo)

        text = "🎁 <b>Мои промокоды</b>\n\n"

        if available:
            text += "<b>Доступные для использования:</b>\n"
            for promo in available:
                text += f"• <code>{promo.code}</code> — скидка {promo.discount_percent}% (осталось {promo.max_uses - promo.used_count} шт.)\n"
        else:
            text += "У вас нет доступных промокодов.\n"

        if used:
            text += "\n<b>Использованные:</b>\n"
            for promo in used:
                text += f"• {promo.code} — скидка {promo.discount_percent}%\n"

        if not available and not used:
            text = "🎁 <b>Мои промокоды</b>\n\nУ вас пока нет промокодов. Следите за акциями!"

    except Exception as e:
        logger.error(f"[{user_id}] Ошибка при получении промокодов: {e}", exc_info=True)
        text = "❌ Произошла ошибка при загрузке промокодов."

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Список промокодов отправлен")
    await callback.answer()


@router.callback_query(F.data == "user_referral")
async def user_referral(callback: CallbackQuery):
    """
    Показывает реферальную ссылку и код пользователя.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Запрошена реферальная программа")

    user = await db.get_user(user_id)
    if not user:
        logger.error(f"[{user_id}] Пользователь не найден в БД при запросе рефералов")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    bot_info = await callback.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref{user.user_id}"

    text = (
        f"🔗 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте <b>1%</b> от каждого их обмена!\n\n"
        f"<b>Ваша реферальная ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"<b>Ваш реферальный код:</b> <code>{user.referral_code}</code>\n\n"
        f"Поделитесь ссылкой с друзьями, и когда они совершат обмен, вы автоматически получите бонус."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📤 Поделиться", url=f"https://t.me/share/url?url={referral_link}&text=Крипто-обменник с лучшими курсами!")
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Реферальная информация отправлена")
    await callback.answer()


@router.callback_query(F.data == "user_settings")
async def user_settings(callback: CallbackQuery):
    """
    Отображает настройки пользователя (уведомления, язык).
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Запрошены настройки")

    user = await db.get_user(user_id)
    if not user:
        logger.error(f"[{user_id}] Пользователь не найден в БД при запросе настроек")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"<b>Уведомления:</b> {'✅ Включены' if user.notifications_enabled else '❌ Отключены'}\n"
        f"<b>Язык:</b> {user.language or 'ru'}\n\n"
        f"Выберите настройку для изменения:"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔔 Уведомления", callback_data="user_toggle_notifications")
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    logger.debug(f"[{user_id}] Настройки отправлены")
    await callback.answer()


@router.callback_query(F.data == "user_toggle_notifications")
async def user_toggle_notifications(callback: CallbackQuery):
    """
    Переключает состояние уведомлений для пользователя.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Переключение уведомлений")

    user = await db.get_user(user_id)
    if not user:
        logger.error(f"[{user_id}] Пользователь не найден в БД при переключении уведомлений")
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    new_value = not user.notifications_enabled
    await db.set_user_notifications(user_id, new_value)

    status = "включены" if new_value else "отключены"
    logger.info(f"[{user_id}] Уведомления теперь {status}")
    await callback.answer(f"Уведомления {status}", show_alert=True)

    # Возвращаемся в меню настроек
    await user_settings(callback)


@router.callback_query(F.data == "user_back_profile")
async def user_back_profile(callback: CallbackQuery):
    """
    Возвращает пользователя в главное меню личного кабинета.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Возврат в главное меню профиля")

    # Просто вызываем cmd_profile, передавая callback.message как message
    await cmd_profile(callback.message)
    await callback.answer()


@router.callback_query(F.data == "user_back_main")
async def user_back_main(callback: CallbackQuery):
    """
    Возвращает пользователя в главное меню бота.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Возврат в главное меню")

    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None
    )
    await callback.message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()
    logger.debug(f"[{user_id}] Главное меню отображено")