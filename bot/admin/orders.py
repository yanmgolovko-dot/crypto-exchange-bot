# bot/admin/orders.py
"""Обработчики админ-панели для управления заявками."""

import logging
import os
import html
import asyncio
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime

from bot.services.db import db
from bot.services.crypto_wallets import wallet_manager, CryptoWalletManager
from bot.services.payment_service import PaymentService
from bot.services.order_service import OrderService
from bot.services.admin_order_service import AdminOrderService
from bot.services.coupon_service import coupon_service
from bot.keyboards import admin_order_keyboard, manual_pending_keyboard, auto_pending_keyboard, receipt_received_keyboard
from bot.admin.main import is_admin, notify_admins, send_receipt
from bot.admin.states import AdminStates
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()


def _tx_hash_hint(crypto_type: str) -> str:
    """Возвращает подсказку по формату хеша для конкретной валюты."""
    cur = (crypto_type or "").upper()
    if cur in {"BTC", "LTC", "USDT", "TRX", "BCH", "DOGE", "DASH"}:
        return f"{cur} — ровно 64 hex-символа"
    return f"{cur} — минимум 32 hex-символа"


def get_explorer_url(crypto_type: str, tx_hash: str) -> Optional[str]:
    """Генерирует ссылку на блокчейн-эксплорер в зависимости от валюты."""
    if not tx_hash or tx_hash == 'N/A':
        return None
        
    cur = (crypto_type or "").upper()
    if cur == 'BTC':
        return f"https://live.blockcypher.com/btc/tx/{tx_hash}/"
    elif cur == 'LTC':
        return f"https://live.blockcypher.com/ltc/tx/{tx_hash}/"
    elif cur in ['USDT', 'TRX']:
        return f"https://tronscan.org/#/transaction/{tx_hash}"
    
    return None


@router.callback_query(F.data == "admin_orders_menu")
async def admin_orders_menu(callback: CallbackQuery):
    """Меню управления заявками."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Попытка доступа без прав")
        return

    logger.info(f"[ADMIN {admin_id}] Открыто меню управления заявками")
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="⏳ Ожидают оплаты", callback_data="admin_orders_pending")
    keyboard.button(text="💳 На проверке", callback_data="admin_orders_paid")
    keyboard.button(text="✅ Выполненные", callback_data="admin_orders_completed")
    keyboard.button(text="❌ Отмененные", callback_data="admin_orders_cancelled")
    keyboard.button(text="🔍 Найти заявку", callback_data="admin_orders_search")
    keyboard.button(text="🗑 Очистить все заявки", callback_data="admin_orders_clear_all")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(2, 2, 1, 1)

    await callback.message.edit_text(
        "📋 <b>Управление заявками</b>\n\nВыберите категорию:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_orders_pending")
async def admin_orders_pending(callback: CallbackQuery):
    """Список заявок, ожидающих оплаты (статус pending)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка ожидающих заявок")
    orders = await db.get_pending_orders()
    pending_orders = [o for o in orders if o.status == 'pending']

    if not pending_orders:
        await callback.answer("Нет ожидающих заявок", show_alert=True)
        logger.info(f"[ADMIN {admin_id}] Нет ожидающих заявок")
        return

    text = f"⏳ <b>Ожидают оплаты ({len(pending_orders)}):</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for order in pending_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.public_order_number or order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Тип: {order.order_type or 'shop'}\n\n"
        )
        keyboard.button(text=f"Управление #{order.public_order_number or order.id}", callback_data=f"admin_order_manage_{order.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_paid")
async def admin_orders_paid(callback: CallbackQuery):
    """Список заявок на проверке (статус paid)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка заявок на проверке")
    orders = await db.get_pending_orders()
    paid_orders = [o for o in orders if o.status == 'paid']

    if not paid_orders:
        await callback.answer("Нет заявок на проверке", show_alert=True)
        logger.info(f"[ADMIN {admin_id}] Нет заявок на проверке")
        return

    text = f"💳 <b>На проверке оплаты ({len(paid_orders)}):</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for order in paid_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.public_order_number or order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Тип: {order.order_type or 'shop'}\n\n"
        )
        keyboard.button(text=f"Проверить #{order.public_order_number or order.id}", callback_data=f"admin_order_check_{order.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_completed")
async def admin_orders_completed(callback: CallbackQuery):
    """Список выполненных заявок (последние 20)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка выполненных заявок")
    orders = await db.get_all_orders(limit=20)
    completed_orders = [o for o in orders if o.status == 'completed']

    if not completed_orders:
        await callback.answer("Нет выполненных заявок", show_alert=True)
        logger.info(f"[ADMIN {admin_id}] Нет выполненных заявок")
        return

    text = f"✅ <b>Выполненные заявки (последние 20):</b>\n\n"
    for order in completed_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.public_order_number or order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Завершена: {order.completed_at}\n\n"
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_cancelled")
async def admin_orders_cancelled(callback: CallbackQuery):
    """Список отменённых заявок (последние 20)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос списка отменённых заявок")
    orders = await db.get_all_orders(limit=20)
    cancelled_orders = [o for o in orders if o.status == 'cancelled']

    if not cancelled_orders:
        await callback.answer("Нет отменённых заявок", show_alert=True)
        logger.info(f"[ADMIN {admin_id}] Нет отменённых заявок")
        return

    text = f"❌ <b>Отменённые заявки (последние 20):</b>\n\n"
    for order in cancelled_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.public_order_number or order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Отменена: {order.completed_at or 'N/A'}\n\n"
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_search")
async def admin_orders_search(callback: CallbackQuery, state: FSMContext):
    """Начало поиска заявки по ID."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Начало поиска заявки")
    await state.set_state(AdminStates.searching_order)
    await callback.message.answer("🔍 Введите номер заявки (ID):")
    await callback.answer()


@router.message(AdminStates.searching_order)
async def admin_orders_search_by_id(message: Message, state: FSMContext, bot: Bot):
    """Поиск заявки по введённому ID."""
    admin_id = message.from_user.id
    try:
        order_id = int(message.text.strip())
        logger.info(f"[ADMIN {admin_id}] Поиск заявки #{order_id}")
    except ValueError:
        logger.warning(f"[ADMIN {admin_id}] Некорректный ввод ID: {message.text}")
        await message.answer("❌ Введите корректный числовой ID.")
        await state.clear()
        return

    order = await db.get_order(order_id)
    if not order:
        logger.info(f"[ADMIN {admin_id}] Заявка #{order_id} не найдена")
        await message.answer("❌ Заявка с таким ID не найдена.")
        await state.clear()
        return

    logger.info(f"[ADMIN {admin_id}] Найдена заявка #{order_id}, статус {order.status}")
    if order.bank_receipt:
        await send_receipt(
            chat_id=message.chat.id,
            file_path=order.bank_receipt,
            caption=f"🧾 Чек по заявке #{order.id}",
            bot=bot
        )
        logger.info(f"[ADMIN {admin_id}] Отправлен чек по заявке #{order_id}")

    safe_username = html.escape(order.username) if order.username else 'N/A'
    safe_address = html.escape(order.crypto_address)
    safe_tx_hash = html.escape(order.tx_hash) if order.tx_hash else ''

    text = (
        f"📋 <b>Заявка #{order.public_order_number or order.id}</b>\n\n"
        f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
        f"Криптовалюта: {order.crypto_type}\n"
        f"Сумма RUB: {order.amount_rub:,.0f} ₽\n"
        f"Сумма крипты: {order.amount_crypto:.8f}\n"
        f"Курс: {order.rate:,.0f} ₽\n"
        f"Комиссия: {order.fee_percent}%\n"
        f"Статус: {order.status}\n"
        f"Тип заявки: {order.order_type or 'shop'}\n"
        f"Создана: {order.created_at}\n"
        f"Кошелёк: <code>{safe_address}</code>\n"
    )
    if order.network:
        text += f"Сеть: {order.network}\n"
    if order.user_payment_details:
        text += f"Реквизиты клиента: <code>{html.escape(order.user_payment_details)}</code>\n"
    if order.paid_at:
        text += f"Оплачена: {order.paid_at}\n"
    if order.completed_at:
        text += f"Завершена: {order.completed_at}\n"
        
    if order.tx_hash:
        text += f"🔗 <b>Хеш транзакции:</b> <code>{safe_tx_hash}</code>\n"
        explorer_url = get_explorer_url(order.crypto_type, order.tx_hash)
        if explorer_url:
            text += f"<a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n"

    keyboard = InlineKeyboardBuilder()
    if order.status == 'paid':
        if order.order_type == 'p2p_sell':
            keyboard.button(text="✅ Крипта получена, выплатить рубли", callback_data=f"admin_approve_{order.id}")
        else:
            keyboard.button(text="✅ Подтвердить", callback_data=f"admin_approve_{order.id}")
        keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order.id}")
    elif order.status == 'processing':
        keyboard.button(text="✏️ Ввести хеш транзакции", callback_data=f"admin_enter_tx_hash_{order.id}")
    elif order.status == 'pending':
        if order.order_type == 'p2p_sell':
            keyboard.button(text="🏦 Отправить адрес для крипты", callback_data=f"admin_p2p_address_{order.id}")
        else:
            keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order.id}")
            keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order.id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "admin_orders_clear_all")
async def admin_orders_clear_confirm(callback: CallbackQuery):
    """Подтверждение удаления всех заявок."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Запрос на очистку всех заявок")
    text = (
        "⚠️ <b>Очистка всех заявок</b>\n\n"
        "Это удалит ВСЕ заявки из базы данных, включая ожидающие, выполненные и отменённые.\n"
        "Финансовые записи и транзакции останутся.\n\n"
        "Вы уверены?"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить всё", callback_data="admin_orders_clear_execute")
    keyboard.button(text="❌ Нет", callback_data="admin_orders_menu")
    keyboard.adjust(2)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_clear_execute")
async def admin_orders_clear_execute(callback: CallbackQuery):
    """Исполнение удаления всех заявок."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Выполнение очистки всех заявок")
    await db.clear_all_orders()
    await callback.answer("✅ Все заявки удалены", show_alert=True)
    await admin_orders_menu(callback)


@router.callback_query(F.data.startswith("admin_order_manage_"))
async def admin_order_manage(callback: CallbackQuery, bot: Bot):
    """Показать детали конкретной заявки и кнопки управления."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    logger.info(f"[ADMIN {admin_id}] Просмотр деталей заявки #{order_id}")

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не найдена")
        return

    if order.bank_receipt:
        await send_receipt(
            chat_id=callback.message.chat.id,
            file_path=order.bank_receipt,
            caption=f"🧾 Чек по заявке #{order.id}",
            bot=bot
        )
        logger.info(f"[ADMIN {admin_id}] Отправлен чек по заявке #{order_id}")

    safe_username = html.escape(order.username) if order.username else 'N/A'
    safe_address = html.escape(order.crypto_address)
    safe_tx_hash = html.escape(order.tx_hash) if order.tx_hash else ''

    text = (
        f"📋 <b>Заявка #{order.public_order_number or order.id}</b>\n\n"
        f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
        f"Криптовалюта: {order.crypto_type}\n"
        f"Сумма RUB: {order.amount_rub:,.0f} ₽\n"
        f"Сумма крипты: {order.amount_crypto:.8f}\n"
        f"Курс: {order.rate:,.0f} ₽\n"
        f"Комиссия: {order.fee_percent}%\n"
        f"Статус: {order.status}\n"
        f"Тип заявки: {order.order_type or 'shop'}\n"
        f"Создана: {order.created_at}\n"
        f"Кошелёк: <code>{safe_address}</code>\n"
    )
    if order.network:
        text += f"Сеть: {order.network}\n"
    if order.user_payment_details:
        text += f"Реквизиты клиента: <code>{html.escape(order.user_payment_details)}</code>\n"
    if order.paid_at:
        text += f"Оплачена: {order.paid_at}\n"
    if order.completed_at:
        text += f"Завершена: {order.completed_at}\n"
        
    if order.tx_hash:
        text += f"🔗 <b>Хеш транзакции:</b> <code>{safe_tx_hash}</code>\n"
        explorer_url = get_explorer_url(order.crypto_type, order.tx_hash)
        if explorer_url:
            text += f"<a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n"

    keyboard = InlineKeyboardBuilder()
    if order.status == 'paid':
        if order.order_type == 'p2p_sell':
            keyboard.button(text="✅ Крипта получена, выплатить рубли", callback_data=f"admin_approve_{order.id}")
        else:
            keyboard.button(text="✅ Подтвердить", callback_data=f"admin_approve_{order.id}")
        keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order.id}")
    elif order.status == 'processing':
        keyboard.button(text="✏️ Ввести хеш транзакции", callback_data=f"admin_enter_tx_hash_{order.id}")
    elif order.status == 'pending':
        if order.order_type == 'p2p_sell':
            keyboard.button(text="🏦 Отправить адрес для крипты", callback_data=f"admin_p2p_address_{order.id}")
        else:
            keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order.id}")
            keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order.id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order_check_"))
async def admin_order_check(callback: CallbackQuery, bot: Bot):
    """Проверка конкретной заявки со статусом paid (после загрузки чека или получения хеша)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    logger.info(f"[ADMIN {admin_id}] Проверка заявки #{order_id} (статус paid)")

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if order.bank_receipt:
        await send_receipt(
            chat_id=callback.message.chat.id,
            file_path=order.bank_receipt,
            caption=f"🧾 Чек по заявке #{order.id}",
            bot=bot
        )
        logger.info(f"[ADMIN {admin_id}] Отправлен чек по заявке #{order_id}")

    safe_username = html.escape(order.username) if order.username else 'N/A'
    safe_address = html.escape(order.crypto_address) if order.crypto_address != 'N/A' else 'N/A'

    text = (
        f"💳 <b>Проверка заявки #{order.public_order_number or order.id}</b>\n\n"
        f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
        f"Сумма: {order.amount_rub:,.0f} ₽\n"
        f"Крипта: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Кошелек: <code>{safe_address}</code>\n"
    )
    if order.network:
        text += f"Сеть: {order.network}\n"
    if order.user_payment_details:
        text += f"Реквизиты клиента: <code>{html.escape(order.user_payment_details)}</code>\n"
        
    if order.tx_hash:
        text += f"\n🔗 <b>Хеш транзакции клиента:</b>\n<code>{html.escape(order.tx_hash)}</code>\n"
        explorer_url = get_explorer_url(order.crypto_type, order.tx_hash)
        if explorer_url:
            text += f"<a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n"
    
    text += f"\nВремя оплаты/отправки: {order.paid_at}\n\n"
    if order.order_type == 'p2p_sell':
        text += "Проверьте поступление криптовалюты на кошелек и подтвердите выплату рублей."
    else:
        text += "Проверьте поступление средств и подтвердите заявку."

    keyboard = InlineKeyboardBuilder()
    if order.order_type == 'p2p_sell':
        keyboard.button(text="✅ Крипта получена, выплатить рубли", callback_data=f"admin_approve_{order.id}")
    else:
        keyboard.button(text="✅ Оплата получена", callback_data=f"admin_approve_{order.id}")
        
    keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order.id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_paid")
    keyboard.adjust(1)

    await callback.message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_request_receipt_"))
async def admin_request_receipt(callback: CallbackQuery, bot: Bot):
    """Отправить пользователю напоминание об оплате (с проверкой лимита)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    logger.info(f"[ADMIN {admin_id}] Запрос чека (напоминание) для заявки #{order_id}")

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    if order.reminder_count >= 3:
        logger.info(f"[ADMIN {admin_id}] Максимальное количество напоминаний (3) уже отправлено для заявки #{order_id}")
        await callback.answer("❌ Максимальное количество напоминаний (3) уже отправлено.", show_alert=True)
        return

    try:
        safe_address = html.escape(order.crypto_address)
        await bot.send_message(
            order.user_id,
            f"📎 <b>Напоминание по заявке #{order.public_order_number or order.id}</b>\n\n"
            f"Пожалуйста, оплатите заявку и отправьте чек.\n\n"
            f"Сумма к оплате: {order.amount_rub:,.0f} ₽\n"
            f"Криптовалюта: {order.crypto_type}\n"
            f"Количество: {order.amount_crypto:.8f}\n\n"
            f"Для отправки чека используйте кнопку ниже.",
            reply_markup=InlineKeyboardBuilder().button(
                text="📎 Отправить чек",
                callback_data=f"upload_receipt_{order.id}"
            ).as_markup(),
            parse_mode="HTML"
        )
        await db.orders.increment_reminder_count(order_id)
        logger.info(f"[ADMIN {admin_id}] Напоминание отправлено пользователю {order.user_id} по заявке #{order_id}")
        await callback.answer("✅ Напоминание отправлено клиенту.")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка отправки напоминания: {e}")
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("admin_msg_"))
async def admin_msg_start(callback: CallbackQuery, state: FSMContext):
    """Начать отправку сообщения клиенту."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    logger.info(f"[ADMIN {admin_id}] Начало отправки сообщения клиенту по заявке #{order_id}")

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    await state.update_data(msg_user_id=order.user_id, msg_order_id=order_id)
    await state.set_state(AdminStates.sending_message_to_user)

    await callback.message.answer("💬 Введите сообщение для отправки клиенту (или отправьте /cancel для отмены):")
    await callback.answer()


@router.message(AdminStates.sending_message_to_user)
async def admin_send_message_to_user(message: Message, state: FSMContext, bot: Bot):
    """Отправка введённого сообщения клиенту."""
    admin_id = message.from_user.id
    if message.text == "/cancel":
        await message.answer("❌ Отправка сообщения отменена.")
        logger.info(f"[ADMIN {admin_id}] Отправка сообщения отменена")
        await state.clear()
        return

    data = await state.get_data()
    user_id = data.get('msg_user_id')
    order_id = data.get('msg_order_id')

    if not user_id or not order_id:
        logger.warning(f"[ADMIN {admin_id}] Ошибка: данные не найдены")
        await message.answer("❌ Ошибка: данные не найдены. Попробуйте снова.")
        await state.clear()
        return

    try:
        safe_text = html.escape(message.text)
        await bot.send_message(
            user_id,
            f"💬 <b>Сообщение от администратора по заявке #{order_id}:</b>\n\n{safe_text}",
            parse_mode="HTML"
        )
        logger.info(f"[ADMIN {admin_id}] Сообщение отправлено пользователю {user_id} по заявке #{order_id}")
        await message.answer("✅ Сообщение успешно отправлено клиенту.")
    except Exception as e:
        logger.error(f"[ADMIN {admin_id}] Ошибка отправки сообщения: {e}")
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")

    await state.clear()


# ==================== ВВОД АДРЕСА ДЛЯ P2P SELL ====================

@router.callback_query(F.data.startswith("admin_p2p_address_"))
async def admin_p2p_address_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    order = await db.get_order(order_id)
    
    if not order or order.order_type != 'p2p_sell' or order.status != 'pending':
        await callback.answer("❌ Заявка недействительна или не в статусе 'pending'.", show_alert=True)
        return

    await state.update_data(p2p_order_id=order_id)
    await state.set_state(AdminStates.entering_p2p_wallet_address)

    await callback.message.answer(
        f"🏦 Введите <b>адрес вашего кошелька</b> для приёма {order.crypto_type} ({order.network}), "
        f"чтобы отправить его клиенту.\n\n"
        f"Сумма: <b>{order.amount_crypto:.8f} {order.crypto_type}</b>\n"
        f"Курс: {order.rate:,.0f} ₽\n\n"
        f"Введите текст (или /cancel для отмены):"
    )
    await callback.answer()

@router.message(AdminStates.entering_p2p_wallet_address)
async def admin_p2p_address_finish(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await message.answer("❌ Отменено.")
        await state.clear()
        return

    address = message.text.strip()
    data = await state.get_data()
    order_id = data.get('p2p_order_id')
    order = await db.get_order(order_id)

    if not order:
        await message.answer("❌ Ошибка: заявка не найдена.")
        await state.clear()
        return

    # Отправляем адрес клиенту и даем кнопку для ввода хеша
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Я оплатил (Ввести хеш)", callback_data=f"p2p_client_confirm_tx_{order.id}")
    
    await bot.send_message(
        order.user_id,
        f"🏦 <b>Адрес для отправки {order.crypto_type} по заявке #{order.public_order_number}</b>\n\n"
        f"Пожалуйста, переведите <b>{order.amount_crypto:.8f} {order.crypto_type}</b> (сеть {order.network}) на адрес:\n"
        f"<code>{html.escape(address)}</code>\n\n"
        f"⚠️ <b>Важно!</b> После отправки обязательно нажмите кнопку ниже и введите хеш транзакции, чтобы администратор быстрее подтвердил ваш перевод.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

    await message.answer(f"✅ Адрес отправлен клиенту. Ожидайте ввода хеша от клиента.")
    await state.clear()


# ==================== ПОДТВЕРЖДЕНИЕ ЗАЯВКИ ====================

@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve_order(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_order_service: AdminOrderService
):
    """Подтверждение заявки (авто, ручной режим, или P2P Sell)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    logger.info(f"[ADMIN {admin_id}] Нажата кнопка 'Подтвердить' для заявки #{order_id}")
    
    order = await db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    # ---- ЛОГИКА ДЛЯ P2P SELL ----
    if order.order_type == 'p2p_sell':
        if order.status != 'paid':
            await callback.answer("❌ Ожидался статус 'На проверке'.", show_alert=True)
            return
            
        await db.update_order_status(order_id, 'completed', admin_comment="Выплата рублей произведена", admin_id=admin_id)
        
        user_text = (
            f"✅ <b>Заявка #{order.public_order_number or order.id} успешно завершена!</b>\n\n"
            f"Криптовалюта получена. Рубли в размере <b>{order.amount_rub:,.0f} ₽</b> "
            f"отправлены на ваши реквизиты: <code>{html.escape(order.user_payment_details or '')}</code>.\n\n"
        )
        
        # Добавляем хеш и ссылку в сообщение клиенту
        if order.tx_hash:
            user_text += f"🔗 Хеш вашей транзакции:\n<code>{html.escape(order.tx_hash)}</code>\n"
            explorer_url = get_explorer_url(order.crypto_type, order.tx_hash)
            if explorer_url:
                user_text += f"<a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n\n"
                
        user_text += "Спасибо за обмен!"

        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

        hash_text = ""
        if order.tx_hash:
            hash_text = f"\n🔗 Хеш: <code>{html.escape(order.tx_hash)}</code>\n"
            explorer_url = get_explorer_url(order.crypto_type, order.tx_hash)
            if explorer_url:
                hash_text += f"<a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n"

        await callback.message.edit_text(
            f"✅ Заявка #{order.public_order_number or order.id} завершена.\n\n"
            f"Пользователь уведомлен о выплате {order.amount_rub:,.0f} ₽.{hash_text}",
            reply_markup=InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup(),
            parse_mode="HTML"
        )
        await callback.answer("Заявка завершена")
        return
    # ---- КОНЕЦ ЛОГИКИ P2P SELL ----

    payment_mode = await db.get_payment_mode()

    if payment_mode == 'auto':
        result = await admin_order_service.approve_order_auto(order_id, admin_id, bot)
        if not result['success']:
            logger.warning(f"[ADMIN {admin_id}] Ошибка подтверждения заявки #{order_id}: {result['error']}")
            await callback.answer(f"❌ {result['error']}", show_alert=True)
            return

        order = result['order']
        tx_hash = result['tx_hash']
        logger.info(f"[ADMIN {admin_id}] Заявка #{order_id} подтверждена, tx_hash: {tx_hash}")

        # Выдаём купоны за активность
        await coupon_service.check_and_give_activity_coupons(order.user_id)

        explorer_url = get_explorer_url(order.crypto_type, tx_hash)

        user_text = (
            f"✅ <b>Заявка #{order.public_order_number or order.id} выполнена!</b>\n\n"
            f"Криптовалюта отправлена:\n"
            f"<b>{order.amount_crypto:.8f} {order.crypto_type}</b>\n"
            f"На адрес: <code>{html.escape(order.crypto_address)}</code>\n\n"
        )
        if tx_hash != 'N/A':
            user_text += f"📝 Хеш транзакции:\n<code>{html.escape(tx_hash)}</code>\n\n"
            if explorer_url:
                user_text += f"🔗 <a href='{explorer_url}'>Посмотреть в эксплорере</a>\n\n"
        user_text += "Спасибо за использование нашего обменника! 🎉"

        admin_text = (
            f"💸 <b>Криптовалюта отправлена!</b>\n\n"
            f"Заявка: #{order.public_order_number or order.id}\n"
            f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"Кошелек: <code>{html.escape(order.crypto_address)}</code>\n"
            f"TX Hash: <code>{html.escape(tx_hash)}</code>\n"
            f"Комиссия: {order.amount_rub * order.fee_percent / 100:,.0f} ₽"
        )

        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML", disable_web_page_preview=True)
            logger.info(f"Пользователь {order.user_id} уведомлен о выполнении заявки #{order_id}")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

        await notify_admins(bot, admin_text, exclude_id=admin_id)

        result_text = (
            f"✅ <b>Заявка #{order.public_order_number or order.id} выполнена!</b>\n\n"
            f"💸 Криптовалюта отправлена:\n"
            f"   Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   TX Hash: <code>{html.escape(tx_hash)}</code>\n"
        )
        if explorer_url:
             result_text += f"   <a href='{explorer_url}'>👀 Открыть в эксплорере</a>\n"
             
        result_text += f"   Комиссия: {order.amount_rub * order.fee_percent / 100:,.0f} ₽\n\nПользователь уведомлен."
        
        reply_markup = InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()
        try:
            await callback.message.edit_text(result_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await callback.message.answer(result_text, reply_markup=reply_markup, parse_mode="HTML")

        await callback.answer("Заявка подтверждена!")

    else:  # Ручной режим
        if order.status != 'paid':
            logger.warning(f"[ADMIN {admin_id}] Попытка подтвердить заявку #{order_id} со статусом {order.status}, требуется 'paid'")
            await callback.answer("❌ Заявка не в статусе 'оплачена'. Чек ещё не получен.", show_alert=True)
            return

        # ВАЖНО: переводим paid → processing, чтобы затем стало возможно ввести tx-хеш.
        approved = await admin_order_service.approve_order_manual(order_id, admin_id)
        if not approved:
            logger.error(
                f"[ADMIN {admin_id}] Не удалось перевести заявку #{order_id} "
                f"в processing. Статус не изменён."
            )
            await callback.answer(
                "❌ Не удалось перевести заявку в обработку. "
                "Возможно, статус уже изменился. Обновите список.",
                show_alert=True,
            )
            return

        await state.update_data(confirming_order_id=order_id, confirming_admin=admin_id)

        user_text = (
            f"✅ <b>Ваш платёж по заявке #{order.public_order_number or order.id} подтверждён!</b>\n\n"
            f"Сумма: {order.amount_rub:,.0f} ₽ получена.\n"
            f"Сейчас администратор отправит криптовалюту на ваш кошелёк.\n"
            f"Ожидайте транзакцию в ближайшее время."
        )
        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML")
            logger.info(f"Пользователь {order.user_id} уведомлен о подтверждении оплаты по заявке #{order_id}")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

        admin_text = (
            f"✏️ <b>Введите хеш транзакции для заявки #{order.public_order_number or order.id}</b>\n\n"
            f"Кошелёк получателя: <code>{html.escape(order.crypto_address)}</code>\n"
            f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"Формат: {_tx_hash_hint(order.crypto_type)}\n\n"
            f"После ввода хеша пользователь получит ссылку для отслеживания.\n"
            f"Для отмены введите /cancel"
        )
        await callback.message.answer(admin_text, parse_mode="HTML")
        await state.set_state(AdminStates.waiting_tx_hash)

        await callback.answer()


@router.callback_query(F.data.startswith("admin_enter_tx_hash_"))
async def admin_start_tx_hash_input(callback: CallbackQuery, state: FSMContext):
    """
    Начать ввод хеша для заявки в статусе 'processing'.
    Используется, когда админ уже подтвердил оплату, но хеш отклонён
    (или сессия была прервана). Не меняет статус — он уже processing.
    """
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[4])
    except (IndexError, ValueError):
        await callback.answer("❌ Некорректный callback", show_alert=True)
        return

    logger.info(f"[ADMIN {admin_id}] Начало ввода хеша для заявки #{order_id}")

    order = await db.get_order(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    if order.status != 'processing':
        logger.warning(
            f"[ADMIN {admin_id}] Заявка #{order_id} в статусе '{order.status}', "
            f"ввод хеша доступен только для 'processing'"
        )
        await callback.answer(
            f"❌ Заявка в статусе '{order.status}'. Ввод хеша доступен только "
            f"для статуса 'processing'.",
            show_alert=True,
        )
        return

    await state.update_data(confirming_order_id=order_id, confirming_admin=admin_id)
    await callback.message.answer(
        f"✏️ <b>Введите хеш транзакции для заявки #{order.public_order_number or order.id}</b>\n\n"
        f"Кошелёк получателя: <code>{html.escape(order.crypto_address)}</code>\n"
        f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Формат: {_tx_hash_hint(order.crypto_type)}\n\n"
        f"Для отмены введите /cancel"
    )
    await state.set_state(AdminStates.waiting_tx_hash)
    await callback.answer()


@router.message(AdminStates.waiting_tx_hash)
async def admin_enter_tx_hash(message: Message, state: FSMContext, bot: Bot, admin_order_service: AdminOrderService):
    """Ввод хеша транзакции в ручном режиме."""
    admin_id = message.from_user.id
    data = await state.get_data()
    order_id = data.get('confirming_order_id')
    confirming_admin = data.get('confirming_admin')

    if not order_id or confirming_admin != admin_id:
        logger.warning(f"[ADMIN {admin_id}] Ошибка: данные не найдены или доступ запрещён")
        await message.answer("❌ Ошибка: данные не найдены или доступ запрещён.")
        await state.clear()
        return

    if message.text == "/cancel":
        logger.info(f"[ADMIN {admin_id}] Ввод хеша отменён для заявки #{order_id}")
        await message.answer(
            "❌ Ввод хеша отменён.\n\n"
            f"Заявка #{order_id} остаётся в статусе 'processing'. "
            f"Вернуться к вводу хеша можно через карточку заявки."
        )
        await state.clear()
        return

    tx_hash = message.text.strip()
    if len(tx_hash) < 10 or len(tx_hash) > 100:
        logger.warning(f"[ADMIN {admin_id}] Некорректный хеш (длина {len(tx_hash)}): {tx_hash}")
        await message.answer(
            "❌ Некорректная длина хеша (должно быть от 10 до 100 символов).\n"
            "Введите ещё раз или /cancel для отмены:"
        )
        return

    order = await db.get_order(order_id)
    if not order:
        await message.answer("❌ Заявка не найдена.")
        await state.clear()
        return

    ok, err = await admin_order_service.complete_order_with_tx_hash(order_id, tx_hash, admin_id, bot)
    if not ok:
        logger.warning(
            f"[ADMIN {admin_id}] Заявка #{order_id} НЕ завершена: {err} "
            f"Хеш '{tx_hash}' не сохранён."
        )
        extra_hint = ""
        current = await db.get_order(order_id)
        if current and current.status == 'processing':
            extra_hint = "\n\nℹ️ Заявка в статусе 'processing' — можно повторить ввод хеша."
        elif current:
            extra_hint = (
                f"\n\nℹ️ Текущий статус заявки: '{current.status}'. "
                f"Ввод хеша доступен только в статусе 'processing'."
            )
        await message.answer(
            f"❌ Не удалось завершить заявку #{order_id}.\n\n"
            f"Причина: {html.escape(err)}"
            f"{extra_hint}\n\n"
            f"Для отмены введите /cancel."
        )
        return

    logger.info(f"[ADMIN {admin_id}] Заявка #{order_id} завершена, хеш {tx_hash} сохранён")

    explorer_url = get_explorer_url(order.crypto_type, tx_hash)

    user_text = (
        f"✅ <b>Криптовалюта по заявке #{order.public_order_number or order.id} отправлена!</b>\n\n"
        f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Хеш транзакции: <code>{html.escape(tx_hash)}</code>\n"
    )
    if explorer_url:
        user_text += f"🔗 <a href='{explorer_url}'>Отследить транзакцию</a>"

    try:
        await bot.send_message(order.user_id, user_text, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"Пользователь {order.user_id} уведомлён об отправке по заявке #{order_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    await message.answer(f"✅ Хеш сохранён. Пользователь уведомлён. Заявка #{order.public_order_number or order.id} выполнена.")
    await state.clear()


@router.callback_query(F.data.startswith("admin_manual_complete_"))
async def admin_manual_complete(callback: CallbackQuery, bot: Bot, admin_order_service: AdminOrderService):
    """Принудительное завершение заявки без хеша (для экстренных случаев)."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    logger.warning(f"[ADMIN {admin_id}] Принудительное завершение заявки #{order_id} без хеша")

    order = await db.get_order(order_id)
    fee_amount = order.amount_rub * order.fee_percent / 100

    async with db.uow() as uow:
        await uow.orders.update_order_status(
            order_id,
            "completed",
            f"Подтверждено админом {admin_id} вручную (после ошибки отправки)",
            admin_id
        )
        await uow.finance.add_financial_record(
            record_type='income',
            category='exchange_fee',
            amount=fee_amount,
            description=f'Комиссия с заявки #{order_id}',
            order_id=order_id,
            created_by=admin_id
        )
        await uow.commit()

    # Выдаём купоны за активность
    await coupon_service.check_and_give_activity_coupons(order.user_id)

    user_text = (
        f"✅ <b>Заявка #{order.public_order_number or order.id} выполнена!</b>\n\n"
        f"Криптовалюта будет отправлена вручную администратором.\n"
        f"Ожидайте сообщения с подтверждением."
    )
    try:
        await bot.send_message(order.user_id, user_text, parse_mode="HTML")
        logger.info(f"Пользователь {order.user_id} уведомлён о принудительном завершении заявки #{order_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    await callback.message.edit_text(
        f"✅ Заявка #{order.public_order_number or order.id} отмечена как выполненная вручную.\n\nПользователь уведомлен.",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_order(callback: CallbackQuery, bot: Bot, admin_order_service: AdminOrderService):
    """Отклонение заявки."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    logger.info(f"[ADMIN {admin_id}] Отклонение заявки #{order_id}")

    await admin_order_service.reject_order(order_id, admin_id)

    order = await db.get_order(order_id)

    try:
        await bot.send_message(
            order.user_id,
            f"❌ <b>Заявка #{order.public_order_number or order.id} отклонена.</b>\n\n"
            f"Причина: Оплата не подтверждена.\n"
            f"По вопросам обратитесь в поддержку.",
            parse_mode="HTML"
        )
        logger.info(f"Пользователь {order.user_id} уведомлен об отклонении заявки #{order_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    result_text = f"❌ Заявка #{order.public_order_number or order.id} отклонена."
    reply_markup = InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()

    try:
        await callback.message.edit_text(result_text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(result_text, reply_markup=reply_markup)

    await callback.answer("Заявка отклонена")


@router.callback_query(F.data.startswith("admin_enter_payment_details_"))
async def admin_enter_payment_details_start(callback: CallbackQuery, state: FSMContext):
    """Начало ввода реквизитов для ручного режима."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[4])
    logger.info(f"[ADMIN {admin_id}] Начало ввода реквизитов для заявки #{order_id}")

    order = await db.get_order(order_id)
    if not order:
        logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не найдена")
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    if order.status != 'pending':
        logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} имеет статус {order.status}, требуется pending")
        await callback.answer("❌ Эта заявка уже обработана или не ожидает реквизитов.", show_alert=True)
        return

    await state.update_data(manual_order_id=order_id)
    await state.set_state(AdminStates.entering_manual_payment_details)

    await callback.message.answer(
        f"💳 Введите платёжные реквизиты для заявки #{order.public_order_number or order.id}.\n"
        f"Например: карта, номер телефона, имя получателя, банк и т.д.\n\n"
        f"Отправьте текст (или /cancel для отмены):"
    )
    await callback.answer()


@router.message(AdminStates.entering_manual_payment_details)
async def admin_enter_payment_details_finish(
    message: Message,
    state: FSMContext,
    bot: Bot,
    payment_service: PaymentService,
    admin_order_service: AdminOrderService
):
    """Сохранение введённых реквизитов и отправка пользователю."""
    admin_id = message.from_user.id
    if message.text == "/cancel":
        logger.info(f"[ADMIN {admin_id}] Ввод реквизитов отменён")
        await message.answer("❌ Ввод реквизитов отменён.")
        await state.clear()
        return

    data = await state.get_data()
    order_id = data.get('manual_order_id')
    if not order_id:
        logger.warning(f"[ADMIN {admin_id}] Ошибка: заявка не найдена в состоянии")
        await message.answer("❌ Ошибка: заявка не найдена. Попробуйте снова.")
        await state.clear()
        return

    order = await db.get_order(order_id)
    if not order:
        logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не существует")
        await message.answer("❌ Заявка не существует.")
        await state.clear()
        return

    details = message.text
    logger.info(f"[ADMIN {admin_id}] Введены реквизиты для заявки #{order_id}: {details[:50]}...")

    await admin_order_service.send_payment_details(order_id, details, order.user_id)
    success = await payment_service.process_manual_payment_details(
        order_id=order_id,
        details=details,
        user_id=order.user_id,
        username=order.username,
        bot=bot
    )
    if success:
        safe_username = html.escape(order.username) if order.username else str(order.user_id)
        logger.info(f"[ADMIN {admin_id}] Реквизиты успешно отправлены пользователю {order.user_id}")
        await message.answer(f"✅ Реквизиты отправлены пользователю @{safe_username}.")
    else:
        logger.error(f"[ADMIN {admin_id}] Не удалось отправить реквизиты пользователю {order.user_id}")
        await message.answer("❌ Не удалось отправить реквизиты.")

    await state.clear()