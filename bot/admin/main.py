# bot/admin/main.py
"""Главные обработчики админ-панели и общие функции."""

import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from bot.services.db import db
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    result = user_id in config.ADMIN_IDS
    if not result:
        logger.warning(f"Проверка is_admin: user_id={user_id}, ADMIN_IDS={config.ADMIN_IDS}")
    return result


async def notify_admins(bot: Bot, text: str, reply_markup=None, exclude_id: int = None):
    """
    Отправка уведомления всем администраторам с поддержкой HTML и опциональной клавиатурой.
    Параметр exclude_id позволяет исключить одного админа (например, инициатора действия).
    """
    for admin_id in config.ADMIN_IDS:
        if exclude_id and admin_id == exclude_id:
            continue
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            logger.info(f"Уведомление отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")


async def send_receipt(chat_id, file_path, caption, bot: Bot):
    """
    Отправляет чек в зависимости от расширения файла.
    Если .pdf – отправляет как документ, иначе как фото.
    """
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        if file_path.lower().endswith('.pdf'):
            await bot.send_document(chat_id, FSInputFile(file_path), caption=caption)
        else:
            await bot.send_photo(chat_id, FSInputFile(file_path), caption=caption)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки чека: {e}")
        return False


def admin_main_keyboard():
    """Главная клавиатура админ-панели."""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📋 Заявки", callback_data="admin_orders_menu")
    keyboard.button(text="💰 Финансы", callback_data="admin_finance_menu")
    keyboard.button(text="⚙️ Настройки", callback_data="admin_settings_menu")
    keyboard.button(text="👥 Пользователи", callback_data="admin_users_menu")
    keyboard.button(text="🎁 Акции", callback_data="admin_promo_menu")
    keyboard.button(text="💳 Реквизиты", callback_data="admin_bank_menu")
    keyboard.button(text="📊 Дашборд", callback_data="admin_dashboard")
    keyboard.button(text="💎 Кошельки", callback_data="admin_wallets_menu")
    keyboard.button(text="🔍 Диагностика", callback_data="admin_diagnostic")
    keyboard.adjust(3, 3, 3)
    return keyboard.as_markup()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Главное меню админ-панели."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return

    await state.clear()

    stats = await db.get_dashboard_stats()
    online = await db.get_online_users(minutes=5)
    payment_mode = await db.get_payment_mode()
    mode_text = "Авто" if payment_mode == 'auto' else "Ручной"

    text = (
        f"🔐 <b>Админ-панель</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"   Всего: {stats['total_users']}\n"
        f"   Онлайн: {online}\n"
        f"   Новых за 24ч: {stats['new_users_24h']}\n"
        f"   Активных за 24ч: {stats['active_users_24h']}\n"
        f"   Забанено: {stats['banned_users']}\n\n"
        f"📋 <b>Заявки:</b>\n"
        f"   Всего: {stats['total_orders']}\n"
        f"   ⏳ Ожидают оплаты: {stats['pending_orders']}\n"
        f"   💳 На проверке: {stats['paid_orders']}\n"
        f"   ✅ Выполнено: {stats['completed_orders']}\n\n"
        f"💰 <b>Финансы:</b>\n"
        f"   Оборот: {stats['total_volume']:,.0f} ₽\n"
        f"   За 24ч: {stats['volume_24h']:,.0f} ₽\n"
        f"   Комиссий: {stats['total_fees']:,.0f} ₽\n\n"
        f"🎁 Акций активно: {stats['active_promos']}\n"
        f"💳 Реквизитов активно: {stats['active_bank_details']}\n\n"
        f"⚙️ <b>Текущий режим оплаты:</b> {mode_text}"
    )

    await message.answer(text, reply_markup=admin_main_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(callback: CallbackQuery):
    """Подробный дашборд с финансовой статистикой."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    stats_24h = await db.get_financial_stats(days=1)
    stats_7d = await db.get_financial_stats(days=7)
    stats_30d = await db.get_financial_stats(days=30)
    daily_stats = await db.get_daily_stats(days=7)

    text = (
        f"📊 <b>Дашборд обменника</b>\n\n"
        f"<b>За 24 часа:</b>\n"
        f"   Выручка: {stats_24h['revenue']:,.0f} ₽\n"
        f"   Расходы: {stats_24h['expenses']:,.0f} ₽\n"
        f"   Прибыль: {stats_24h['profit']:,.0f} ₽\n"
        f"   Оборот: {stats_24h['trading_volume']:,.0f} ₽\n\n"
        f"<b>За 7 дней:</b>\n"
        f"   Выручка: {stats_7d['revenue']:,.0f} ₽\n"
        f"   Расходы: {stats_7d['expenses']:,.0f} ₽\n"
        f"   Прибыль: {stats_7d['profit']:,.0f} ₽\n"
        f"   Оборот: {stats_7d['trading_volume']:,.0f} ₽\n\n"
        f"<b>За 30 дней:</b>\n"
        f"   Выручка: {stats_30d['revenue']:,.0f} ₽\n"
        f"   Расходы: {stats_30d['expenses']:,.0f} ₽\n"
        f"   Прибыль: {stats_30d['profit']:,.0f} ₽\n"
        f"   Оборот: {stats_30d['trading_volume']:,.0f} ₽\n\n"
    )

    if daily_stats:
        text += "<b>Статистика по дням:</b>\n"
        for day in daily_stats[:5]:
            text += f"   {day['date']}: {day['orders_count']} заявок, {day['volume']:,.0f} ₽\n"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_back_main")
async def admin_back_main(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Назад' - возвращает в главное меню админки."""
    if not is_admin(callback.from_user.id):
        logger.warning(f"Доступ запрещён. User ID: {callback.from_user.id}, ADMIN_IDS: {config.ADMIN_IDS}")
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.clear()
    await cmd_admin(callback.message, state)
    await callback.answer()