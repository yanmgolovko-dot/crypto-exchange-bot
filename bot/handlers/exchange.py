# bot/handlers/exchange.py
"""
Обновлённая версия файла exchange.py с использованием модульной системы создания заявки.
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
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from bot.services.db import Database
from bot.services.crypto_api import CryptoAPI
from bot.services.crypto_wallets import CryptoWalletManager
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.services.coupon_service import coupon_service
from bot.keyboards import (
    main_menu_keyboard, order_info_keyboard, crypto_select_keyboard,
    currency_choice_keyboard, amount_select_keyboard, confirm_order_keyboard,
    cancel_creation_keyboard, receipt_keyboard, admin_order_keyboard,
    manual_pending_keyboard, auto_pending_keyboard, receipt_received_keyboard,
    coupons_selection_keyboard
)
from bot.order_creation.manager import OrderCreationManager
from bot.order_creation.exceptions import OrderCreationError
from bot.order_creation.states import ExchangeStates
from bot.admin.main import notify_admins
from bot.config.settings import config
from bot.utils.decorators import rate_limiter
from bot.services.validator import validate_crypto_address
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
router = Router()

MAX_RECEIPT_SIZE_MB = 10
MAX_RECEIPT_SIZE_BYTES = MAX_RECEIPT_SIZE_MB * 1024 * 1024

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RECEIPTS_DIR = os.path.join(_PROJECT_ROOT, "data", "receipts")
user_managers: dict[int, OrderCreationManager] = {}


class PromoStates(StatesGroup):
    selecting_coupon = State()
    entering_promo_text = State()


class HasActiveManagerFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in user_managers


class HasActiveManagerCallbackFilter(BaseFilter):
    async def __call__(self, callback: CallbackQuery) -> bool:
        return callback.from_user.id in user_managers


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    user_id = message.from_user.id
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
    await safe_edit_message(callback.message, "❌ Создание заявки отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("upload_receipt_"))
async def process_upload_receipt(callback: CallbackQuery, state: FSMContext, db: Database):
    user_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    order = await db.get_order(order_id)
    if order is None:
        await callback.answer("❌ Заявка не найдена.", show_alert=True)
        return
    if order.status != "pending":
        await callback.answer(f"ℹ️ Чек по заявке #{order.public_order_number or order.id} уже принят.", show_alert=True)
        return
    await state.update_data(order_id=order_id)
    await state.set_state(ExchangeStates.uploading_receipt)
    await callback.message.answer("📎 Отправьте PDF-файл с чеком:")
    await callback.answer()


@router.message(ExchangeStates.uploading_receipt, F.document)
async def process_receipt_document(message: Message, state: FSMContext, bot: Bot, db: Database, payment_service: PaymentService):
    user_id = message.from_user.id
    document = message.document
    if document.mime_type != "application/pdf":
        await message.answer("❌ Только PDF.")
        return
    if document.file_size is not None and document.file_size > MAX_RECEIPT_SIZE_BYTES:
        await message.answer(f"❌ Файл слишком большой. Максимум {MAX_RECEIPT_SIZE_MB} МБ.")
        return
    data = await state.get_data()
    order_id = data.get('order_id')
    if not order_id:
        await message.answer("❌ Ошибка.")
        await state.clear()
        return
    order = await db.get_order(order_id)
    if order is None:
        await message.answer("❌ Заявка не найдена.")
        await state.clear()
        return
    display_number = order.public_order_number if order.public_order_number else order.id
    if order.status != "pending":
        await message.answer(f"ℹ️ По заявке #{display_number} чек уже принят.")
        await state.clear()
        return
    try:
        file = await bot.get_file(document.file_id)
        os.makedirs(_RECEIPTS_DIR, exist_ok=True)
        file_path = os.path.join(_RECEIPTS_DIR, f"receipt_{order_id}_{document.file_id}.pdf")
        await bot.download_file(file.file_path, file_path)
    except Exception as e:
        logger.error(f"Ошибка скачивания чека: {e}")
        await message.answer("❌ Не удалось сохранить файл.")
        return
    accepted = await payment_service.save_receipt(order_id, file_path)
    if not accepted:
        await message.answer(f"ℹ️ Чек по заявке #{display_number} уже был принят.")
        await state.clear()
        return
    await message.answer(f"✅ Чек получен! Заявка #{display_number} на проверке.", reply_markup=order_info_keyboard(order_id))
    await payment_service.notify_admins_about_receipt(
        bot, order_id, user_id, message.from_user.username,
        order.amount_rub, order.amount_crypto, order.crypto_type,
        order.crypto_address, file_path
    )
    await state.clear()


@router.message(ExchangeStates.uploading_receipt)
async def process_invalid_receipt(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте PDF-файл с чеком.")


@router.message(F.text == "💰 Купить криптовалюту")
async def buy_crypto(message: Message, state: FSMContext, **services):
    user_id = message.from_user.id
    if user_id in user_managers:
        del user_managers[user_id]
    manager = OrderCreationManager(state, user_id, message.from_user.username)
    user_managers[user_id] = manager
    await manager.start(message, services)


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


async def _process_after_promo(target, state: FSMContext, order_service: OrderService, crypto_api: CryptoAPI, db: Database):
    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    discount_percent = data.get('discount_percent', 0)
    input_type = data.get('input_type')
    amount = data.get('net_amount') if input_type == 'rub' else data.get('desired_crypto')
    rate = data.get('rate')
    if not rate:
        rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    calc_result = await order_service.calculate_order(
        crypto_type=crypto_type, input_type=input_type, amount=amount,
        discount_percent=discount_percent, rate=rate
    )
    if not calc_result:
        error_text = "❌ Ошибка расчёта. Попробуйте позже."
        if hasattr(target, 'message'):
            await target.message.answer(error_text)
        else:
            await target.answer(error_text)
        return
    await state.update_data(**calc_result)
    text = (
        f"📋 <b>Подтверждение заявки</b>\n\n"
        f"Криптовалюта: {crypto_type}\n"
        f"💵 <b>Сумма к получению:</b> {calc_result['net_amount']:,.0f} ₽\n"
        f"💳 <b>Сумма к оплате:</b> {calc_result['gross_amount']:,.0f} ₽\n"
        f"Вы получите: {calc_result['amount_crypto']:.8f} {crypto_type}\n"
        f"Курс: {calc_result['rate']:,.0f} ₽\n\n"
    )
    if discount_percent > 0:
        text += f"🎁 Скидка: {discount_percent}%\n\n"
    text += f"Теперь введите адрес вашего {crypto_type}-кошелька для получения криптовалюты:"
    await state.set_state(ExchangeStates.entering_wallet)
    if hasattr(target, 'message'):
        await safe_edit_message(target.message, text, parse_mode="HTML", reply_markup=cancel_creation_keyboard())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=cancel_creation_keyboard())


async def _show_coupon_selection(target, state: FSMContext, user_id: int, net_amount: float):
    coupons = await coupon_service.get_user_coupons(user_id)
    valid = []
    for c in coupons:
        ok, _, _ = await db.validate_coupon(c.code, user_id, net_amount)
        if ok: valid.append(c)
        
    if valid:
        await state.set_state(PromoStates.selecting_coupon)
        kb = coupons_selection_keyboard(valid, skip_cb="skip_promo")
        text = f"🎁 <b>У вас есть купоны!</b>\n\nВыберите купон для скидки или пропустите этот шаг.\n\nЖелаемая сумма: {net_amount:,.0f} ₽"
        if isinstance(target, CallbackQuery):
            await safe_edit_message(target.message, text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await state.set_state(PromoStates.entering_promo_text)
        text = (
            f"🎁 <b>Промокод</b>\n\n"
            f"У вас есть промокод?\n"
            f"Введите код для получения скидки или нажмите «Пропустить»:\n\n"
            f"Желаемая сумма: {net_amount:,.0f} ₽"
        )
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⏩ Пропустить", callback_data="skip_promo")
        keyboard.adjust(1)
        if isinstance(target, CallbackQuery):
            await safe_edit_message(target.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("buy_"))
async def process_crypto_selection(callback: CallbackQuery, state: FSMContext):
    crypto_type = callback.data.split("_")[1]
    await state.update_data(crypto_type=crypto_type)
    await state.set_state(ExchangeStates.selecting_currency)
    text = f"Выберите, в чём вы хотите ввести сумму для {crypto_type}:"
    await safe_edit_message(callback.message, text, reply_markup=currency_choice_keyboard(crypto_type))
    await callback.answer()


@router.callback_query(F.data.startswith("currency_rub_"))
async def process_currency_rub(callback: CallbackQuery, state: FSMContext, crypto_api: CryptoAPI, db: Database):
    crypto_type = callback.data.split("_")[2]
    await state.update_data(crypto_type=crypto_type, input_type='rub')
    await state.set_state(ExchangeStates.selecting_amount)
    rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    await state.update_data(rate=rate)
    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
    standard_amounts = [1000, 3000, 5000, 10000, 20000, 50000, 100000, 200000, 500000]
    amounts = [a for a in standard_amounts if min_net <= a <= max_net]
    if not amounts:
        amounts = sorted(set([int(min_net), int(max_net)]))
    text = f"💰 Покупка {crypto_type}\n\nТекущий курс: {rate:,.0f} ₽\n\nВыберите сумму, которую хотите получить (в рублях):"
    await safe_edit_message(callback.message, text, reply_markup=amount_select_keyboard(crypto_type, amounts))
    await callback.answer()


@router.callback_query(F.data.startswith("currency_crypto_"))
async def process_currency_crypto(callback: CallbackQuery, state: FSMContext, crypto_api: CryptoAPI):
    crypto_type = callback.data.split("_")[2]
    await state.update_data(crypto_type=crypto_type, input_type='crypto')
    await state.set_state(ExchangeStates.entering_crypto_amount)
    rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    await state.update_data(rate=rate)
    text = f"💰 Покупка {crypto_type}\n\nТекущий курс: {rate:,.0f} ₽\n\nВведите количество {crypto_type} (например, 0.001):"
    await safe_edit_message(callback.message, text)
    await callback.answer()


@router.callback_query(F.data.startswith("amount_"))
async def process_amount_selection(callback: CallbackQuery, state: FSMContext, db: Database):
    parts = callback.data.split("_")
    crypto_type, net_amount = parts[1], int(parts[2])
    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
    if net_amount < min_net or net_amount > max_net:
        await callback.answer(f"❌ Сумма должна быть от {min_net:,.0f} до {max_net:,.0f} ₽", show_alert=True)
        return
    await state.update_data(net_amount=net_amount, input_type='rub')
    await _show_coupon_selection(callback, state, callback.from_user.id, net_amount)
    await callback.answer()


@router.callback_query(F.data.startswith("custom_amount_"))
async def process_custom_amount(callback: CallbackQuery, state: FSMContext, db: Database):
    crypto_type = callback.data.split("_")[2]
    await state.update_data(crypto_type=crypto_type)
    await state.set_state(ExchangeStates.entering_custom_amount)
    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
    text = f"✏️ Введите желаемую сумму в рублях\n\nМинимум: {min_net:,.0f} ₽\nМаксимум: {max_net:,.0f} ₽\n\nВведите целое число:"
    await safe_edit_message(callback.message, text)
    await callback.answer()


@router.message(ExchangeStates.entering_custom_amount)
async def process_custom_amount_input(message: Message, state: FSMContext, db: Database):
    try:
        net_amount = int(message.text.replace(" ", "").replace(",", ""))
        min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
        max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
        if net_amount < min_net or net_amount > max_net:
            await message.answer(f"❌ Сумма должна быть от {min_net:,.0f} до {max_net:,.0f} ₽\n\nПопробуйте еще раз:")
            return
        await state.update_data(net_amount=net_amount, input_type='rub')
        await _show_coupon_selection(message, state, message.from_user.id, net_amount)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


@router.message(ExchangeStates.entering_crypto_amount)
async def process_crypto_amount_input(message: Message, state: FSMContext, crypto_api: CryptoAPI, db: Database):
    try:
        crypto_amount = float(message.text.replace(",", "."))
        if crypto_amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное положительное число.")
        return
    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    rate = data.get('rate')
    if not rate:
        rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    net_equivalent = round(crypto_amount * rate, 2)
    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
    if net_equivalent < min_net or net_equivalent > max_net:
        await message.answer(f"❌ Сумма эквивалентна {net_equivalent:,.0f} ₽, что выходит за пределы от {min_net:,.0f} до {max_net:,.0f} ₽.")
        return
    await state.update_data(desired_crypto=crypto_amount, net_equivalent=net_equivalent, rate=rate)
    await _show_coupon_selection(message, state, message.from_user.id, net_equivalent)


@router.callback_query(F.data == "skip_promo")
async def skip_promo(callback: CallbackQuery, state: FSMContext, order_service: OrderService, crypto_api: CryptoAPI, db: Database):
    await state.update_data(promo_code=None, discount_percent=0)
    await _process_after_promo(callback, state, order_service, crypto_api, db)


@router.callback_query(PromoStates.selecting_coupon, F.data.startswith("apply_coupon_"))
async def apply_coupon_callback(callback: CallbackQuery, state: FSMContext, order_service: OrderService, crypto_api: CryptoAPI, db: Database):
    code = callback.data.split("_")[2]
    data = await state.get_data()
    net_amount = data.get('net_amount')
    if not net_amount:
        net_amount = data.get('desired_crypto', 0) * data.get('rate', 1)
        
    is_valid, msg, coupon = await db.validate_coupon(code, callback.from_user.id, net_amount)
    if is_valid:
        if coupon.discount_type == 'percent':
            discount = coupon.discount_value
        else:
            discount = (coupon.discount_value / net_amount) * 100
            
        await state.update_data(promo_code=code, discount_percent=discount)
        await _process_after_promo(callback, state, order_service, crypto_api, db)
    else:
        await callback.answer(f"❌ {msg}", show_alert=True)


@router.callback_query(PromoStates.selecting_coupon, F.data == "promo_manual")
async def promo_manual_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.entering_promo_text)
    await safe_edit_message(
        callback.message,
        "🎁 <b>Промокод</b>\n\nВведите код промокода или нажмите «Пропустить»:",
        reply_markup=InlineKeyboardBuilder().button(text="⏩ Пропустить", callback_data="skip_promo").as_markup()
    )


@router.message(PromoStates.entering_promo_text)
async def process_promo_code(message: Message, state: FSMContext, db: Database, user_service: UserService, order_service: OrderService, crypto_api: CryptoAPI):
    code = message.text.strip()
    await user_service.register_or_update(
        user_id=message.from_user.id, username=message.from_user.username,
        first_name=message.from_user.first_name, last_name=message.from_user.last_name
    )
    is_valid, msg, discount = await db.validate_promo_code(code, message.from_user.id)
    if is_valid:
        await message.answer(f"✅ {escape_html(msg)}\nСкидка: {discount}%")
        await state.update_data(promo_code=code, discount_percent=discount)
    else:
        await message.answer(f"❌ {escape_html(msg)}\nПродолжаем без скидки.")
        await state.update_data(promo_code=None, discount_percent=0)
    await _process_after_promo(message, state, order_service, crypto_api, db)


@router.message(ExchangeStates.entering_wallet)
async def process_wallet_input(message: Message, state: FSMContext, bot: Bot, db: Database, crypto_api: CryptoAPI, wallet_manager: CryptoWalletManager, order_service: OrderService, payment_service: PaymentService, user_service: UserService):
    if not rate_limiter.is_allowed(message.from_user.id):
        await message.answer("⏳ Слишком много запросов. Пожалуйста, подождите немного.")
        return
    wallet_address = message.text.strip()
    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    if not validate_crypto_address(wallet_address, crypto_type):
        await message.answer(f"❌ Некорректный {crypto_type}-адрес. Попробуйте еще раз:")
        return
    await user_service.register_or_update(
        user_id=message.from_user.id, username=message.from_user.username,
        first_name=message.from_user.first_name, last_name=message.from_user.last_name
    )
    gross_amount = data.get('gross_amount')
    amount_crypto = data.get('amount_crypto')
    rate = data.get('rate')
    effective_fee = data.get('fee_percent')
    net_amount = data.get('net_amount')
    order_id = await order_service.create_order(
        user_id=message.from_user.id, username=message.from_user.username,
        crypto_type=crypto_type, amount_rub=gross_amount, amount_crypto=amount_crypto,
        rate=rate, fee_percent=effective_fee, crypto_address=wallet_address,
        promo_code=data.get('promo_code'), discount_percent=data.get('discount_percent', 0)
    )
    order = await db.get_order(order_id)
    public_order_number = order.public_order_number if order and order.public_order_number else order_id

    await state.update_data(order_id=order_id, wallet_address=wallet_address)
    payment_mode = await db.get_payment_mode()
    payment_source = await db.get_manual_payment_source()
    payment_info = await payment_service.get_bank_details_for_order(payment_mode, payment_source)
    if not payment_info['success']:
        await message.answer(f"❌ {payment_info['error']}")
        return

    safe_username = escape_html(message.from_user.username) if message.from_user.username else 'N/A'
    safe_address = escape_html(wallet_address)

    if payment_info['auto']:
        safe_card = escape_html(payment_info['card_number'])
        safe_holder = escape_html(payment_info['holder_name'])
        text = (
            f"✅ <b>Заявка #{public_order_number} создана!</b>\n\n"
            f"💳 <b>Реквизиты для оплаты:</b>\nБанк: {payment_info['bank_name']}\nКарта: <code>{safe_card}</code>\nПолучатель: {safe_holder}\n\n"
            f"💰 <b>Сумма к переводу:</b> {gross_amount:,.0f} ₽\n"
            f"💵 <b>Вы получите:</b> {amount_crypto:.8f} {crypto_type} (эквивалент {net_amount:,.0f} ₽)\n\n"
        )
        if data.get('discount_percent', 0) > 0:
            text += f"🎁 Скидка: {data.get('discount_percent')}%\n\n"
        text += f"⚠️ <b>Важно!</b> После оплаты нажмите «Прикрепить чек» и отправьте PDF.\n\n⏱ Заявка будет обработана в течение 5-15 минут."
        await message.answer(text, reply_markup=receipt_keyboard(order_id), parse_mode="HTML")
        admin_text = (
            f"🔔 <b>Новая заявка #{public_order_number}!</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {message.from_user.id})\nКрипта: {crypto_type}\n"
            f"Сумма к оплате: {gross_amount:,.0f} ₽\nСумма к получению: {net_amount:,.0f} ₽ → {amount_crypto:.8f} {crypto_type}\n"
            f"Кошелек: <code>{safe_address}</code>\n"
        )
        if data.get('promo_code'):
            admin_text += f"Промокод: {data.get('promo_code')} (-{data.get('discount_percent')}%)\n"
        admin_text += f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await notify_admins(message.bot, admin_text, reply_markup=auto_pending_keyboard(order_id))
    else:
        text = (
            f"✅ <b>Заявка #{public_order_number} создана!</b>\n\n"
            f"Ожидайте, администратор отправит вам реквизиты для оплаты в ближайшее время.\n\n"
            f"💰 <b>Сумма к переводу:</b> {gross_amount:,.0f} ₽\n"
            f"💵 <b>Вы получите:</b> {amount_crypto:.8f} {crypto_type} (эквивалент {net_amount:,.0f} ₽)\n\n"
        )
        if data.get('discount_percent', 0) > 0:
            text += f"🎁 Скидка по промокоду: {data.get('discount_percent')}%\n\n"
        await message.answer(text, reply_markup=order_info_keyboard(order_id), parse_mode="HTML")
        admin_text = (
            f"🔔 <b>Новая заявка #{public_order_number} (ручной режим)!</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {message.from_user.id})\nКрипта: {crypto_type}\n"
            f"Сумма к оплате: {gross_amount:,.0f} ₽\nСумма к получению: {net_amount:,.0f} ₽ → {amount_crypto:.8f} {crypto_type}\n"
            f"Кошелек: <code>{safe_address}</code>\n"
            f"Требуется ввести реквизиты вручную.\nВремя: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await notify_admins(message.bot, admin_text, reply_markup=manual_pending_keyboard(order_id))
    await state.set_state(ExchangeStates.waiting_for_payment)