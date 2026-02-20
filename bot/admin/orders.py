# bot/admin/orders.py
"""Обработчики админ-панели для управления заявками."""

import logging
import os
import html
import asyncio
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
from bot.keyboards import admin_order_keyboard
from bot.admin.main import is_admin, notify_admins, send_receipt
from bot.admin.states import AdminStates
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_orders_menu")
async def admin_orders_menu(callback: CallbackQuery):
    """Меню управления заявками."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

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
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    orders = await db.get_pending_orders()
    pending_orders = [o for o in orders if o.status == 'pending']

    if not pending_orders:
        await callback.answer("Нет ожидающих заявок", show_alert=True)
        return

    text = f"⏳ <b>Ожидают оплаты ({len(pending_orders)}):</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for order in pending_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Кошелек: <code>{html.escape(order.crypto_address[:20])}...</code>\n"
            f"   Создана: {order.created_at}\n\n"
        )
        keyboard.button(text=f"Управление #{order.id}", callback_data=f"admin_order_manage_{order.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_paid")
async def admin_orders_paid(callback: CallbackQuery):
    """Список заявок на проверке (статус paid)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    orders = await db.get_pending_orders()
    paid_orders = [o for o in orders if o.status == 'paid']

    if not paid_orders:
        await callback.answer("Нет заявок на проверке", show_alert=True)
        return

    text = f"💳 <b>На проверке оплаты ({len(paid_orders)}):</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for order in paid_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.id}</b> | @{safe_username}\n"
            f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   Кошелек: <code>{html.escape(order.crypto_address[:20])}...</code>\n"
            f"   Оплачена: {order.paid_at}\n\n"
        )
        keyboard.button(text=f"Проверить #{order.id}", callback_data=f"admin_order_check_{order.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_orders_completed")
async def admin_orders_completed(callback: CallbackQuery):
    """Список выполненных заявок (последние 20)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    orders = await db.get_all_orders(limit=20)
    completed_orders = [o for o in orders if o.status == 'completed']

    if not completed_orders:
        await callback.answer("Нет выполненных заявок", show_alert=True)
        return

    text = f"✅ <b>Выполненные заявки (последние 20):</b>\n\n"
    for order in completed_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.id}</b> | @{safe_username}\n"
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
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    orders = await db.get_all_orders(limit=20)
    cancelled_orders = [o for o in orders if o.status == 'cancelled']

    if not cancelled_orders:
        await callback.answer("Нет отменённых заявок", show_alert=True)
        return

    text = f"❌ <b>Отменённые заявки (последние 20):</b>\n\n"
    for order in cancelled_orders[:10]:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        text += (
            f"<b>#{order.id}</b> | @{safe_username}\n"
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
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.searching_order)
    await callback.message.answer(
        "🔍 Введите номер заявки (ID):"
    )
    await callback.answer()


@router.message(AdminStates.searching_order)
async def admin_orders_search_by_id(message: Message, state: FSMContext, bot: Bot):
    """Поиск заявки по введённому ID."""
    try:
        order_id = int(message.text.strip())
        order = await db.get_order(order_id)
        if not order:
            await message.answer("❌ Заявка с таким ID не найдена.")
        else:
            if order.bank_receipt:
                await send_receipt(
                    chat_id=message.chat.id,
                    file_path=order.bank_receipt,
                    caption=f"🧾 Чек по заявке #{order.id}",
                    bot=bot
                )

            safe_username = html.escape(order.username) if order.username else 'N/A'
            safe_address = html.escape(order.crypto_address)
            safe_tx_hash = html.escape(order.tx_hash) if order.tx_hash else ''

            text = (
                f"📋 <b>Заявка #{order.id}</b>\n\n"
                f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
                f"Криптовалюта: {order.crypto_type}\n"
                f"Сумма RUB: {order.amount_rub:,.0f} ₽\n"
                f"Сумма крипты: {order.amount_crypto:.8f}\n"
                f"Курс: {order.rate:,.0f} ₽\n"
                f"Комиссия: {order.fee_percent}%\n"
                f"Статус: {order.status}\n"
                f"Создана: {order.created_at}\n"
                f"Кошелёк: <code>{safe_address}</code>\n"
            )
            if order.paid_at:
                text += f"Оплачена: {order.paid_at}\n"
            if order.completed_at:
                text += f"Завершена: {order.completed_at}\n"
            if order.tx_hash:
                text += f"Хеш транзакции: <code>{safe_tx_hash}</code>\n"

            keyboard = InlineKeyboardBuilder()
            if order.status == 'paid':
                keyboard.button(text="✅ Подтвердить", callback_data=f"admin_approve_{order.id}")
                keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order.id}")
            elif order.status == 'pending':
                keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order.id}")
                keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order.id}")
            keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
            keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
            keyboard.adjust(1)

            await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")

    await state.clear()


@router.callback_query(F.data == "admin_orders_clear_all")
async def admin_orders_clear_confirm(callback: CallbackQuery):
    """Подтверждение удаления всех заявок."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

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
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await db.clear_all_orders()
    await callback.answer("✅ Все заявки удалены", show_alert=True)
    await admin_orders_menu(callback)


@router.callback_query(F.data.startswith("admin_order_manage_"))
async def admin_order_manage(callback: CallbackQuery, bot: Bot):
    """Показать детали конкретной заявки и кнопки управления."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    if order.bank_receipt:
        await send_receipt(
            chat_id=callback.message.chat.id,
            file_path=order.bank_receipt,
            caption=f"🧾 Чек по заявке #{order.id}",
            bot=bot
        )

    safe_username = html.escape(order.username) if order.username else 'N/A'
    safe_address = html.escape(order.crypto_address)
    safe_tx_hash = html.escape(order.tx_hash) if order.tx_hash else ''

    text = (
        f"📋 <b>Заявка #{order.id}</b>\n\n"
        f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
        f"Криптовалюта: {order.crypto_type}\n"
        f"Сумма RUB: {order.amount_rub:,.0f} ₽\n"
        f"Сумма крипты: {order.amount_crypto:.8f}\n"
        f"Курс: {order.rate:,.0f} ₽\n"
        f"Комиссия: {order.fee_percent}%\n"
        f"Статус: {order.status}\n"
        f"Создана: {order.created_at}\n"
        f"Кошелёк: <code>{safe_address}</code>\n"
    )
    if order.paid_at:
        text += f"Оплачена: {order.paid_at}\n"
    if order.completed_at:
        text += f"Завершена: {order.completed_at}\n"
    if order.tx_hash:
        text += f"Хеш транзакции: <code>{safe_tx_hash}</code>\n"

    keyboard = InlineKeyboardBuilder()
    if order.status == 'paid':
        keyboard.button(text="✅ Подтвердить", callback_data=f"admin_approve_{order.id}")
        keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order.id}")
    elif order.status == 'pending':
        keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order.id}")
        keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order.id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_order_check_"))
async def admin_order_check(callback: CallbackQuery, bot: Bot):
    """Проверка конкретной заявки со статусом paid (после загрузки чека)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
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

    safe_username = html.escape(order.username) if order.username else 'N/A'
    safe_address = html.escape(order.crypto_address)

    text = (
        f"💳 <b>Проверка заявки #{order.id}</b>\n\n"
        f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
        f"Сумма: {order.amount_rub:,.0f} ₽\n"
        f"Крипта: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Кошелек: <code>{safe_address}</code>\n"
        f"Время оплаты: {order.paid_at}\n\n"
        f"Проверьте поступление средств и подтвердите заявку."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Оплата получена", callback_data=f"admin_approve_{order.id}")
    keyboard.button(text="❌ Оплата не поступила", callback_data=f"admin_reject_{order.id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order.id}")
    keyboard.button(text="🔙 Назад", callback_data="admin_orders_paid")
    keyboard.adjust(1)

    await callback.message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


# ========== ИСПРАВЛЕННАЯ ФУНКЦИЯ (ограничение напоминаний) ==========
@router.callback_query(F.data.startswith("admin_request_receipt_"))
async def admin_request_receipt(callback: CallbackQuery, bot: Bot):
    """Отправить пользователю напоминание об оплате (с проверкой лимита)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    # Проверяем количество уже отправленных напоминаний
    if order.reminder_count >= 3:
        await callback.answer("❌ Максимальное количество напоминаний (3) уже отправлено.", show_alert=True)
        return

    try:
        safe_address = html.escape(order.crypto_address)
        await bot.send_message(
            order.user_id,
            f"📎 <b>Напоминание по заявке #{order.id}</b>\n\n"
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
        # Увеличиваем счётчик напоминаний
        await db.orders.increment_reminder_count(order_id)
        await callback.answer("✅ Напоминание отправлено клиенту.")
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


@router.callback_query(F.data.startswith("admin_msg_"))
async def admin_msg_start(callback: CallbackQuery, state: FSMContext):
    """Начать отправку сообщения клиенту."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    await state.update_data(msg_user_id=order.user_id, msg_order_id=order_id)
    await state.set_state(AdminStates.sending_message_to_user)

    await callback.message.answer(
        "💬 Введите сообщение для отправки клиенту (или отправьте /cancel для отмены):"
    )
    await callback.answer()


@router.message(AdminStates.sending_message_to_user)
async def admin_send_message_to_user(message: Message, state: FSMContext, bot: Bot):
    """Отправка введённого сообщения клиенту."""
    if message.text == "/cancel":
        await message.answer("❌ Отправка сообщения отменена.")
        await state.clear()
        return

    data = await state.get_data()
    user_id = data.get('msg_user_id')
    order_id = data.get('msg_order_id')

    if not user_id or not order_id:
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
        await message.answer("✅ Сообщение успешно отправлено клиенту.")
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")

    await state.clear()


# ==================== ЛОГИКА ПОДТВЕРЖДЕНИЯ ====================

@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve_order(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    admin_order_service: AdminOrderService
):
    """Подтверждение заявки (авто или ручной режим)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])
    payment_mode = await db.get_payment_mode()

    if payment_mode == 'auto':
        # Автоматический режим: отправка крипты через сервис
        result = await admin_order_service.approve_order_auto(order_id, callback.from_user.id)
        if not result['success']:
            await callback.answer(f"❌ {result['error']}", show_alert=True)
            return

        order = result['order']
        tx_hash = result['tx_hash']

        explorer_url = None
        if order.crypto_type == 'LTC':
            explorer_url = f"https://live.blockcypher.com/ltc/tx/{tx_hash}/" if tx_hash != 'N/A' else None
        elif order.crypto_type == 'BTC':
            explorer_url = f"https://live.blockcypher.com/btc/tx/{tx_hash}/" if tx_hash != 'N/A' else None

        user_text = (
            f"✅ <b>Заявка #{order_id} выполнена!</b>\n\n"
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
            f"Заявка: #{order_id}\n"
            f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"Кошелек: <code>{html.escape(order.crypto_address)}</code>\n"
            f"TX Hash: <code>{html.escape(tx_hash)}</code>\n"
            f"Комиссия: {order.amount_rub * order.fee_percent / 100:,.0f} ₽"
        )

        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

        await notify_admins(bot, admin_text, exclude_id=callback.from_user.id)

        result_text = (
            f"✅ <b>Заявка #{order_id} выполнена!</b>\n\n"
            f"💸 Криптовалюта отправлена:\n"
            f"   Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"   TX Hash: <code>{html.escape(tx_hash)}</code>\n"
            f"   Комиссия: {order.amount_rub * order.fee_percent / 100:,.0f} ₽\n\n"
            f"Пользователь уведомлен."
        )
        reply_markup = InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()
        try:
            await callback.message.edit_text(result_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            await callback.message.answer(result_text, reply_markup=reply_markup, parse_mode="HTML")

        await callback.answer("Заявка подтверждена!")

    else:  # Ручной режим
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        if order.status != 'paid':
            await callback.answer("❌ Заявка не в статусе 'оплачена'. Чек ещё не получен.", show_alert=True)
            return

        await state.update_data(confirming_order_id=order_id, confirming_admin=callback.from_user.id)

        user_text = (
            f"✅ <b>Ваш платёж по заявке #{order_id} подтверждён!</b>\n\n"
            f"Сумма: {order.amount_rub:,.0f} ₽ получена.\n"
            f"Сейчас администратор отправит криптовалюту на ваш кошелёк.\n"
            f"Ожидайте транзакцию в ближайшее время."
        )
        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

        admin_text = (
            f"✏️ <b>Введите хеш транзакции для заявки #{order_id}</b>\n\n"
            f"Кошелёк получателя: <code>{html.escape(order.crypto_address)}</code>\n"
            f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n\n"
            f"После ввода хеша пользователь получит ссылку для отслеживания.\n"
            f"Для отмены введите /cancel"
        )
        await callback.message.answer(admin_text, parse_mode="HTML")
        await state.set_state(AdminStates.waiting_tx_hash)

        await callback.answer()


@router.message(AdminStates.waiting_tx_hash)
async def admin_enter_tx_hash(message: Message, state: FSMContext, bot: Bot, admin_order_service: AdminOrderService):
    """Ввод хеша транзакции в ручном режиме."""
    data = await state.get_data()
    order_id = data.get('confirming_order_id')
    admin_id = data.get('confirming_admin')

    if not order_id or admin_id != message.from_user.id:
        await message.answer("❌ Ошибка: данные не найдены или доступ запрещён.")
        await state.clear()
        return

    if message.text == "/cancel":
        await message.answer("❌ Ввод хеша отменён.")
        await state.clear()
        return

    tx_hash = message.text.strip()
    if len(tx_hash) < 10 or len(tx_hash) > 100:
        await message.answer("❌ Некорректный хеш. Введите ещё раз (или /cancel для отмены):")
        return

    order = await db.get_order(order_id)
    if not order:
        await message.answer("❌ Заявка не найдена.")
        await state.clear()
        return

    success = await admin_order_service.complete_order_with_tx_hash(order_id, tx_hash, message.from_user.id)
    if not success:
        await message.answer("❌ Не удалось завершить заявку.")
        await state.clear()
        return

    explorer_url = None
    if order.crypto_type == 'LTC':
        explorer_url = f"https://live.blockcypher.com/ltc/tx/{tx_hash}/"
    elif order.crypto_type == 'BTC':
        explorer_url = f"https://live.blockcypher.com/btc/tx/{tx_hash}/"

    user_text = (
        f"✅ <b>Криптовалюта по заявке #{order_id} отправлена!</b>\n\n"
        f"Сумма: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Хеш транзакции: <code>{html.escape(tx_hash)}</code>\n"
    )
    if explorer_url:
        user_text += f"🔗 <a href='{explorer_url}'>Отследить транзакцию</a>"

    try:
        await bot.send_message(order.user_id, user_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    await message.answer(f"✅ Хеш сохранён. Пользователь уведомлён. Заявка #{order_id} выполнена.")
    await state.clear()


@router.callback_query(F.data.startswith("admin_manual_complete_"))
async def admin_manual_complete(callback: CallbackQuery, bot: Bot, admin_order_service: AdminOrderService):
    """
    Принудительное завершение заявки без хеша (для экстренных случаев).
    Используется только когда отправка крипты не удалась, но деньги всё равно нужно зачислить.
    """
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[3])
    order = await db.get_order(order_id)

    # Завершаем без хеша (ручное вмешательство)
    fee_amount = order.amount_rub * order.fee_percent / 100

    async with db.uow() as uow:
        await uow.orders.update_order_status(
            order_id,
            "completed",
            f"Подтверждено админом {callback.from_user.id} вручную (после ошибки отправки)",
            callback.from_user.id
        )
        await uow.finance.add_financial_record(
            record_type='income',
            category='exchange_fee',
            amount=fee_amount,
            description=f'Комиссия с заявки #{order_id}',
            order_id=order_id,
            created_by=callback.from_user.id
        )
        await uow.commit()

    user_text = (
        f"✅ <b>Заявка #{order_id} выполнена!</b>\n\n"
        f"Криптовалюта будет отправлена вручную администратором.\n"
        f"Ожидайте сообщения с подтверждением."
    )
    try:
        await bot.send_message(order.user_id, user_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    await callback.message.edit_text(
        f"✅ Заявка #{order_id} отмечена как выполненная вручную.\n\nПользователь уведомлен.",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject_order(callback: CallbackQuery, bot: Bot, admin_order_service: AdminOrderService):
    """Отклонение заявки."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[2])

    await admin_order_service.reject_order(order_id, callback.from_user.id)

    order = await db.get_order(order_id)

    try:
        await bot.send_message(
            order.user_id,
            f"❌ <b>Заявка #{order_id} отклонена.</b>\n\n"
            f"Причина: Оплата не подтверждена.\n"
            f"По вопросам обратитесь в поддержку.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {order.user_id}: {e}")

    result_text = f"❌ Заявка #{order_id} отклонена."
    reply_markup = InlineKeyboardBuilder().button(text="🔙 К заявкам", callback_data="admin_orders_menu").as_markup()

    try:
        await callback.message.edit_text(result_text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(result_text, reply_markup=reply_markup)

    await callback.answer("Заявка отклонена")


# ==================== ВВОД РЕКВИЗИТОВ В РУЧНОМ РЕЖИМЕ ====================

@router.callback_query(F.data.startswith("admin_enter_payment_details_"))
async def admin_enter_payment_details_start(callback: CallbackQuery, state: FSMContext):
    """Начало ввода реквизитов для ручного режима."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split("_")[4])
    order = await db.get_order(order_id)

    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    await state.update_data(manual_order_id=order_id)
    await state.set_state(AdminStates.entering_manual_payment_details)

    await callback.message.answer(
        f"💳 Введите платёжные реквизиты для заявки #{order_id}.\n"
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
    if message.text == "/cancel":
        await message.answer("❌ Ввод реквизитов отменён.")
        await state.clear()
        return

    data = await state.get_data()
    order_id = data.get('manual_order_id')
    if not order_id:
        await message.answer("❌ Ошибка: заявка не найдена. Попробуйте снова.")
        await state.clear()
        return

    order = await db.get_order(order_id)
    if not order:
        await message.answer("❌ Заявка не существует.")
        await state.clear()
        return

    details = message.text
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
        await message.answer(f"✅ Реквизиты отправлены пользователю @{safe_username}.")
    else:
        await message.answer("❌ Не удалось отправить реквизиты.")

    await state.clear()