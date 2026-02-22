# bot/handlers/exchange.py
"""
Обновлённая версия файла exchange.py с использованием модульной системы создания заявки.
Содержит точки входа и обработчики, которые активируются только во время активного процесса создания заявки,
а также обработчики для уже созданных заявок (загрузка чека, отмена).
"""

import html
import logging
import os
import sys
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from bot.services.db import Database
from bot.services.crypto_api import CryptoAPI
from bot.services.crypto_wallets import CryptoWalletManager
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.keyboards import (
    main_menu_keyboard,
    order_info_keyboard,
    crypto_select_keyboard,
    currency_choice_keyboard,
    amount_select_keyboard,
    confirm_order_keyboard,
    cancel_creation_keyboard,
    receipt_keyboard,
    admin_order_keyboard,
    manual_pending_keyboard,
    auto_pending_keyboard,
    receipt_received_keyboard
)
from bot.order_creation.manager import OrderCreationManager
from bot.order_creation.exceptions import OrderCreationError
from bot.order_creation.states import ExchangeStates
from bot.admin.main import notify_admins
from bot.config.settings import config
from bot.utils.decorators import rate_limiter
from bot.services.validator import validate_crypto_address

logger = logging.getLogger(__name__)

# ДИАГНОСТИКА: принудительно устанавливаем уровень логгера в DEBUG
logger.setLevel(logging.DEBUG)

# ========== ВАЖНО: создаём экземпляр роутера ==========
router = Router()

# Словарь для хранения менеджеров по ID пользователя
user_managers: dict[int, OrderCreationManager] = {}


# ---------- Фильтры для проверки наличия активного менеджера ----------
class HasActiveManagerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in user_managers


class HasActiveManagerCallbackFilter(BaseFilter):
    async def __call__(self, callback: CallbackQuery) -> bool:
        return callback.from_user.id in user_managers


# ---------- ОБЩИЕ КОМАНДЫ ----------
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"[{user_id}] Команда /cancel")
    if user_id in user_managers:
        del user_managers[user_id]
    await state.clear()
    await message.answer("❌ Действие отменено. Возвращаю в главное меню.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "cancel_order_creation")
async def cancel_order_creation(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_managers:
        del user_managers[user_id]
    await state.clear()
    await callback.message.edit_text("❌ Создание заявки отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ---------- ЗАГРУЗКА ЧЕКА ----------
@router.callback_query(F.data.startswith("upload_receipt_"))
async def process_upload_receipt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    logger.info(f"[{user_id}] Кнопка 'Прикрепить чек' для #{order_id}")
    await state.update_data(order_id=order_id)
    await state.set_state(ExchangeStates.uploading_receipt)
    await callback.message.answer("📎 Отправьте PDF-файл с чеком:")
    await callback.answer()


@router.message(ExchangeStates.uploading_receipt, F.document)
async def process_receipt_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    payment_service: PaymentService
):
    user_id = message.from_user.id
    if message.document.mime_type != "application/pdf":
        await message.answer("❌ Только PDF.")
        return
    data = await state.get_data()
    order_id = data.get('order_id')
    if not order_id:
        await message.answer("❌ Ошибка.")
        await state.clear()
        return

    document = message.document
    file = await bot.get_file(document.file_id)
    receipts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    file_path = os.path.join(receipts_dir, f"receipt_{order_id}_{document.file_id}.pdf")
    await bot.download_file(file.file_path, file_path)

    await payment_service.save_receipt(order_id, file_path)
    order = await db.get_order(order_id)

    await message.answer(
        f"✅ Чек получен! Заявка #{order_id} на проверке.",
        reply_markup=order_info_keyboard(order_id)
    )

    await payment_service.notify_admins_about_receipt(
        bot, order_id, user_id, message.from_user.username,
        order.amount_rub, order.amount_crypto, order.crypto_type,
        order.crypto_address, file_path
    )
    await state.clear()


# ---------- СТАРТ ПОКУПКИ ----------
@router.message(F.text == "💰 Купить криптовалюту")
async def buy_crypto(message: Message, state: FSMContext, **services):
    print(">>> buy_crypto вызвана (print)")
    logger.info(">>> buy_crypto вызвана (logger.info)")
    sys.stderr.write(">>> stderr message\n")
    print(f"Уровень логгера exchange: {logger.getEffectiveLevel()}", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()

    user_id = message.from_user.id
    if user_id in user_managers:
        del user_managers[user_id]
    manager = OrderCreationManager(state, user_id, message.from_user.username)
    user_managers[user_id] = manager
    await manager.start(message, services)


# ---------- ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ----------
@router.message(HasActiveManagerFilter())
async def handle_order_message(message: Message, **services):
    user_id = message.from_user.id
    manager = user_managers.get(user_id)
    if not manager:
        return
    try:
        completed = await manager.handle_message(message, services)
        if completed:
            del user_managers[user_id]
    except OrderCreationError as e:
        await message.answer(f"❌ Ошибка: {e}")
        del user_managers[user_id]


@router.callback_query(HasActiveManagerCallbackFilter())
async def handle_order_callback(callback: CallbackQuery, **services):
    user_id = callback.from_user.id
    manager = user_managers.get(user_id)
    if not manager:
        return
    try:
        completed = await manager.handle_callback(callback, services)
        if completed:
            del user_managers[user_id]
    except OrderCreationError as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
        del user_managers[user_id]