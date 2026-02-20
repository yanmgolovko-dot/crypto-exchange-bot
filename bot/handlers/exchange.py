# bot/handlers/exchange.py
"""
Обработчики процесса покупки криптовалюты.
Содержит все шаги создания заявки: выбор криптовалюты, ввод суммы,
применение промокода, ввод адреса кошелька, формирование заявки,
загрузка чека и отмена заявки.
"""

import math
import logging
import os
import asyncio
import html
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import Database
from bot.services.crypto_api import CryptoAPI
from bot.services.crypto_wallets import CryptoWalletManager
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.services.validator import validate_crypto_address
from bot.keyboards import (
    crypto_select_keyboard,
    currency_choice_keyboard,
    amount_select_keyboard,
    receipt_keyboard,
    admin_order_keyboard,
    main_menu_keyboard,
    order_info_keyboard
)
from bot.admin.main import notify_admins
from bot.config.settings import config
from bot.utils.decorators import rate_limiter

logger = logging.getLogger(__name__)
router = Router()

# Директория для сохранения чеков
data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
receipts_dir = os.path.join(data_dir, "receipts")
os.makedirs(receipts_dir, exist_ok=True)


class ExchangeStates(StatesGroup):
    """
    Состояния FSM для процесса создания заявки.
    """
    selecting_crypto = State()          # выбор криптовалюты
    selecting_currency = State()        # выбор валюты ввода (рубли/крипта)
    selecting_amount = State()          # выбор предустановленной суммы
    entering_custom_amount = State()    # ввод своей суммы
    entering_crypto_amount = State()    # ввод суммы в крипте
    entering_wallet = State()           # ввод адреса кошелька
    entering_promo = State()            # ввод промокода
    uploading_receipt = State()         # загрузка чека
    waiting_for_payment = State()       # ожидание оплаты


def cancel_creation_keyboard():
    """
    Клавиатура с кнопкой отмены создания заявки.
    Используется на этапе ввода адреса кошелька.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отменить", callback_data="cancel_order_creation")
    return keyboard.as_markup()


# ==================== ОБЩИЕ КОМАНДЫ ====================

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """
    Обработчик команды /cancel.
    Отменяет текущее действие и возвращает в главное меню.
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer(
        "❌ Действие отменено. Возвращаю в главное меню.",
        reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == "cancel_order_creation")
async def cancel_order_creation(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик нажатия на кнопку отмены создания заявки (до фактического создания).
    """
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание заявки отменено. Возвращаюсь в главное меню.",
        reply_markup=None
    )
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# ==================== НАЧАЛО ПОКУПКИ ====================

@router.message(F.text == "💰 Купить криптовалюту")
async def buy_crypto(message: Message, state: FSMContext, crypto_api: CryptoAPI):
    """
    Начало процесса покупки.
    Показывает актуальные курсы и предлагает выбрать криптовалюту.
    """
    await state.set_state(ExchangeStates.selecting_crypto)

    prices = await crypto_api.get_all_prices()

    rates_text = "📊 Актуальные курсы:\n"
    if prices["BTC"]:
        rates_text += f"• ₿ BTC: {prices['BTC']:,.0f} ₽\n"
    if prices["LTC"]:
        rates_text += f"• Ł LTC: {prices['LTC']:,.0f} ₽\n"
    rates_text += "\nВыберите криптовалюту для покупки:"

    await message.answer(rates_text, reply_markup=crypto_select_keyboard())


@router.callback_query(F.data.startswith("buy_"))
async def process_crypto_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора криптовалюты (BTC или LTC).
    Сохраняет тип криптовалюты и переходит к выбору валюты ввода.
    """
    crypto_type = callback.data.split("_")[1]
    await state.update_data(crypto_type=crypto_type)
    await state.set_state(ExchangeStates.selecting_currency)

    text = f"Выберите, в чём вы хотите ввести сумму для {crypto_type}:"
    await callback.message.edit_text(text, reply_markup=currency_choice_keyboard(crypto_type))
    await callback.answer()


# ==================== ВЫБОР ВАЛЮТЫ ВВОДА ====================

@router.callback_query(F.data.startswith("currency_rub_"))
async def process_currency_rub(callback: CallbackQuery, state: FSMContext, crypto_api: CryptoAPI):
    """
    Пользователь выбрал ввод суммы в рублях.
    Показывает текущий курс и предлагает выбрать предустановленную сумму.
    """
    crypto_type = callback.data.split("_")[2]
    await state.update_data(crypto_type=crypto_type, input_type='rub')
    await state.set_state(ExchangeStates.selecting_amount)

    rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    text = (
        f"💰 Покупка {crypto_type}\n\n"
        f"Текущий курс: {rate:,.0f} ₽\n\n"
        f"Выберите сумму, которую хотите получить (в рублях):"
    )
    await callback.message.edit_text(text, reply_markup=amount_select_keyboard(crypto_type))
    await callback.answer()


@router.callback_query(F.data.startswith("currency_crypto_"))
async def process_currency_crypto(callback: CallbackQuery, state: FSMContext, crypto_api: CryptoAPI):
    """
    Пользователь выбрал ввод суммы в криптовалюте.
    Запрашивает ввод количества крипты.
    """
    crypto_type = callback.data.split("_")[2]
    await state.update_data(crypto_type=crypto_type, input_type='crypto')
    await state.set_state(ExchangeStates.entering_crypto_amount)

    rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    text = (
        f"💰 Покупка {crypto_type}\n\n"
        f"Текущий курс: {rate:,.0f} ₽\n\n"
        f"Введите количество {crypto_type}, которое хотите получить (например, 0.001):"
    )
    await callback.message.edit_text(text)
    await callback.answer()


# ==================== ВВОД СУММЫ В КРИПТОВАЛЮТЕ ====================

@router.message(ExchangeStates.entering_crypto_amount)
async def process_crypto_amount_input(
    message: Message,
    state: FSMContext,
    crypto_api: CryptoAPI,
    db: Database
):
    """
    Обработка введённого пользователем количества криптовалюты.
    Проверяет, что сумма в рублях попадает в допустимые пределы,
    затем переходит к вводу промокода.
    """
    try:
        crypto_amount = float(message.text.replace(",", "."))
        if crypto_amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное положительное число.")
        return

    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    rate = await crypto_api.get_btc_price_rub() if crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
    if not rate:
        await message.answer("❌ Ошибка получения курса. Попробуйте позже или введите сумму в рублях.")
        return

    net_equivalent = crypto_amount * rate
    net_equivalent = round(net_equivalent, 2)

    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))

    if net_equivalent < min_net or net_equivalent > max_net:
        await message.answer(
            f"❌ Сумма в рублях эквивалентна {net_equivalent:,.0f} ₽, что выходит за пределы "
            f"от {min_net:,.0f} до {max_net:,.0f} ₽. Введите другую сумму крипты."
        )
        return

    await state.update_data(desired_crypto=crypto_amount, net_equivalent=net_equivalent, rate=rate)
    await state.set_state(ExchangeStates.entering_promo)

    text = (
        f"🎁 <b>Промокод</b>\n\n"
        f"Вы хотите получить {crypto_amount:.8f} {crypto_type}, что эквивалентно {net_equivalent:,.0f} ₽.\n\n"
        f"У вас есть промокод?\n"
        f"Введите код или нажмите «Пропустить»:"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="⏩ Пропустить", callback_data="skip_promo")
    keyboard.adjust(1)

    await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


# ==================== ВЫБОР ПРЕДУСТАНОВЛЕННОЙ СУММЫ В РУБЛЯХ ====================

@router.callback_query(F.data.startswith("amount_"))
async def process_amount_selection(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database
):
    """
    Обработка выбора одной из предустановленных сумм в рублях.
    Проверяет, что сумма в пределах лимитов, затем переходит к вводу промокода.
    """
    parts = callback.data.split("_")
    crypto_type = parts[1]
    net_amount = int(parts[2])

    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))

    if net_amount < min_net or net_amount > max_net:
        await callback.answer(f"❌ Сумма должна быть от {min_net:,.0f} до {max_net:,.0f} ₽", show_alert=True)
        return

    await state.update_data(net_amount=net_amount, input_type='rub')
    await state.set_state(ExchangeStates.entering_promo)

    text = (
        f"🎁 <b>Промокод</b>\n\n"
        f"У вас есть промокод?\n"
        f"Введите код для получения скидки или нажмите «Пропустить»:\n\n"
        f"Желаемая сумма получения: {net_amount:,.0f} ₽"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="⏩ Пропустить", callback_data="skip_promo")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== ВВОД СВОЕЙ СУММЫ В РУБЛЯХ ====================

@router.callback_query(F.data.startswith("custom_amount_"))
async def process_custom_amount(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database
):
    """
    Запрос на ввод своей суммы в рублях.
    """
    crypto_type = callback.data.split("_")[2]

    await state.update_data(crypto_type=crypto_type)
    await state.set_state(ExchangeStates.entering_custom_amount)

    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))

    text = (
        f"✏️ Введите желаемую сумму получения в рублях\n\n"
        f"Минимум: {min_net:,.0f} ₽\n"
        f"Максимум: {max_net:,.0f} ₽\n\n"
        f"Введите целое число:"
    )

    await callback.message.edit_text(text)
    await callback.answer()


@router.message(ExchangeStates.entering_custom_amount)
async def process_custom_amount_input(
    message: Message,
    state: FSMContext,
    db: Database
):
    """
    Обработка введённой пользователем суммы в рублях.
    Проверяет лимиты и переходит к вводу промокода.
    """
    try:
        net_amount = int(message.text.replace(" ", "").replace(",", ""))

        min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
        max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))

        if net_amount < min_net or net_amount > max_net:
            await message.answer(
                f"❌ Сумма должна быть от {min_net:,.0f} до {max_net:,.0f} ₽\n\n"
                f"Попробуйте еще раз:"
            )
            return

        await state.update_data(net_amount=net_amount, input_type='rub')
        await state.set_state(ExchangeStates.entering_promo)

        text = (
            f"🎁 <b>Промокод</b>\n\n"
            f"У вас есть промокод?\n"
            f"Введите код для получения скидки или нажмите «Пропустить»:\n\n"
            f"Желаемая сумма получения: {net_amount:,.0f} ₽"
        )

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⏩ Пропустить", callback_data="skip_promo")
        keyboard.adjust(1)

        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")

    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректное число:")


# ==================== ОБРАБОТКА ПРОМОКОДА ====================

async def _process_after_promo(
    target,
    state: FSMContext,
    order_service: OrderService,
    crypto_api: CryptoAPI,
    db: Database
):
    """
    Внутренняя функция, вызываемая после обработки промокода (или пропуска).
    Рассчитывает итоговые суммы и запрашивает адрес кошелька.
    """
    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    discount_percent = data.get('discount_percent', 0)
    input_type = data.get('input_type')
    amount = data.get('net_amount') if input_type == 'rub' else data.get('desired_crypto')

    rate = data.get('rate')
    if not rate:
        if crypto_type == "BTC":
            rate = await crypto_api.get_btc_price_rub()
        else:
            rate = await crypto_api.get_ltc_price_rub()

    calc_result = await order_service.calculate_order(
        crypto_type=crypto_type,
        input_type=input_type,
        amount=amount,
        discount_percent=discount_percent,
        rate=rate
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
        text += f"🎁 Скидка по промокоду: {discount_percent}%\n\n"
    text += f"Теперь введите адрес вашего {crypto_type}-кошелька для получения криптовалюты:"

    await state.set_state(ExchangeStates.entering_wallet)

    if hasattr(target, 'message'):  # CallbackQuery
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_creation_keyboard())
    else:  # Message
        await target.answer(text, parse_mode="HTML", reply_markup=cancel_creation_keyboard())


@router.callback_query(F.data == "skip_promo")
async def skip_promo(
    callback: CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    crypto_api: CryptoAPI,
    db: Database
):
    """
    Пользователь пропустил ввод промокода.
    """
    await state.update_data(promo_code=None, discount_percent=0)
    await _process_after_promo(callback, state, order_service, crypto_api, db)


@router.message(ExchangeStates.entering_promo)
async def process_promo_code(
    message: Message,
    state: FSMContext,
    db: Database,
    user_service: UserService,
    order_service: OrderService,
    crypto_api: CryptoAPI
):
    """
    Обработка введённого промокода.
    Проверяет его валидность и применяет скидку.
    """
    code = message.text.strip()

    # Регистрируем/обновляем пользователя (на случай, если он только что зашёл)
    await user_service.register_or_update(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    is_valid, msg, discount = await db.validate_promo_code(code, message.from_user.id)

    if is_valid:
        safe_msg = html.escape(msg)
        await message.answer(f"✅ {safe_msg}\nСкидка: {discount}%")
        await state.update_data(promo_code=code, discount_percent=discount)
    else:
        safe_msg = html.escape(msg)
        await message.answer(f"❌ {safe_msg}\nПродолжаем без скидки.")
        await state.update_data(promo_code=None, discount_percent=0)

    await _process_after_promo(message, state, order_service, crypto_api, db)


# ==================== ВВОД АДРЕСА КОШЕЛЬКА И СОЗДАНИЕ ЗАЯВКИ ====================

@router.message(ExchangeStates.entering_wallet)
async def process_wallet_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    crypto_api: CryptoAPI,
    wallet_manager: CryptoWalletManager,
    order_service: OrderService,
    payment_service: PaymentService,
    user_service: UserService
):
    """
    Обработка введённого адреса кошелька.
    Создаёт заявку в БД и в зависимости от настроек отправляет пользователю
    реквизиты для оплаты (автоматически или ожидание ручного ввода).
    Также уведомляет администраторов.
    """
    # Проверка rate limit
    if not rate_limiter.is_allowed(message.from_user.id):
        await message.answer("⏳ Слишком много запросов. Пожалуйста, подождите немного.")
        return

    wallet_address = message.text.strip()
    data = await state.get_data()
    crypto_type = data.get('crypto_type')

    # Валидация адреса
    if not validate_crypto_address(wallet_address, crypto_type):
        await message.answer(f"❌ Некорректный {crypto_type}-адрес. Попробуйте еще раз:")
        return

    # Регистрация пользователя
    await user_service.register_or_update(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Извлекаем данные расчёта
    gross_amount = data.get('gross_amount')
    amount_crypto = data.get('amount_crypto')
    rate = data.get('rate')
    effective_fee = data.get('fee_percent')
    net_amount = data.get('net_amount')

    # Создаём заявку в БД
    order_id = await order_service.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        crypto_type=crypto_type,
        amount_rub=gross_amount,
        amount_crypto=amount_crypto,
        rate=rate,
        fee_percent=effective_fee,
        crypto_address=wallet_address,
        promo_code=data.get('promo_code'),
        discount_percent=data.get('discount_percent', 0)
    )

    await state.update_data(order_id=order_id, wallet_address=wallet_address)

    # Определяем режимы оплаты
    payment_mode = await db.get_payment_mode()
    payment_source = await db.get_manual_payment_source()

    payment_info = await payment_service.get_bank_details_for_order(payment_mode, payment_source)

    if not payment_info['success']:
        await message.answer(f"❌ {payment_info['error']}")
        return

    # --- АВТОМАТИЧЕСКИЙ РЕЖИМ ИЛИ РУЧНОЙ С РЕКВИЗИТАМИ ИЗ БД ---
    if payment_info['auto']:
        safe_card = html.escape(payment_info['card_number'])
        safe_holder = html.escape(payment_info['holder_name'])
        text = (
            f"✅ <b>Заявка #{order_id} создана!</b>\n\n"
            f"💳 <b>Реквизиты для оплаты:</b>\n"
            f"Банк: {payment_info['bank_name']}\n"
            f"Карта: <code>{safe_card}</code>\n"
            f"Получатель: {safe_holder}\n\n"
            f"💰 <b>Сумма к переводу:</b> {gross_amount:,.0f} ₽\n"
            f"💵 <b>Вы получите:</b> {amount_crypto:.8f} {crypto_type} (эквивалент {net_amount:,.0f} ₽)\n\n"
        )
        if data.get('discount_percent', 0) > 0:
            text += f"🎁 Скидка по промокоду: {data.get('discount_percent')}%\n\n"
        text += (
            f"⚠️ <b>Важно!</b> После оплаты нажмите кнопку «Прикрепить чек» и отправьте PDF-файл с чеком.\n\n"
            f"⏱ Заявка будет обработана в течение 5-15 минут после подтверждения оплаты."
        )
        await message.answer(text, reply_markup=receipt_keyboard(order_id), parse_mode="HTML")

        # Уведомление администраторов
        safe_username = html.escape(message.from_user.username) if message.from_user.username else 'N/A'
        safe_address = html.escape(wallet_address)

        admin_text = (
            f"🔔 <b>Новая заявка #{order_id}!</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {message.from_user.id})\n"
            f"Крипта: {crypto_type}\n"
            f"Сумма к оплате: {gross_amount:,.0f} ₽\n"
            f"Сумма к получению: {net_amount:,.0f} ₽ → {amount_crypto:.8f} {crypto_type}\n"
            f"Кошелек: <code>{safe_address}</code>\n"
        )
        if data.get('promo_code'):
            admin_text += f"Промокод: {data.get('promo_code')} (-{data.get('discount_percent')}%)\n"
        admin_text += f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # Добавляем клавиатуру для админов
        admin_markup = admin_order_keyboard(order_id)
        await notify_admins(message.bot, admin_text, reply_markup=admin_markup)

    else:  # --- РУЧНОЙ РЕЖИМ (админ вводит реквизиты) ---
        text = (
            f"✅ <b>Заявка #{order_id} создана!</b>\n\n"
            f"Ожидайте, администратор отправит вам реквизиты для оплаты в ближайшее время.\n\n"
            f"💰 <b>Сумма к переводу:</b> {gross_amount:,.0f} ₽\n"
            f"💵 <b>Вы получите:</b> {amount_crypto:.8f} {crypto_type} (эквивалент {net_amount:,.0f} ₽)\n\n"
        )
        if data.get('discount_percent', 0) > 0:
            text += f"🎁 Скидка по промокоду: {data.get('discount_percent')}%\n\n"
        await message.answer(text, reply_markup=order_info_keyboard(order_id), parse_mode="HTML")

        # ========== ИСПРАВЛЕНИЕ: уведомление админов о новой заявке в ручном режиме ==========
        safe_username = html.escape(message.from_user.username) if message.from_user.username else 'N/A'
        safe_address = html.escape(wallet_address)
        admin_text = (
            f"🔔 <b>Новая заявка #{order_id} (ручной режим)!</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {message.from_user.id})\n"
            f"Крипта: {crypto_type}\n"
            f"Сумма к оплате: {gross_amount:,.0f} ₽\n"
            f"Сумма к получению: {net_amount:,.0f} ₽ → {amount_crypto:.8f} {crypto_type}\n"
            f"Кошелек: <code>{safe_address}</code>\n"
            f"Требуется ввести реквизиты вручную.\n"
            f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        admin_markup = admin_order_keyboard(order_id)
        await notify_admins(message.bot, admin_text, reply_markup=admin_markup)

    await state.set_state(ExchangeStates.waiting_for_payment)


# ==================== ЗАГРУЗКА ЧЕКА ====================

@router.callback_query(F.data.startswith("upload_receipt_"))
async def process_upload_receipt(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь нажал кнопку «Прикрепить чек».
    Переводит в состояние загрузки PDF-файла.
    """
    order_id = int(callback.data.split("_")[2])

    await state.update_data(order_id=order_id)
    await state.set_state(ExchangeStates.uploading_receipt)

    await callback.message.answer(
        "📎 Пожалуйста, отправьте PDF-файл с чеком об оплате.\n\n"
        "На чеке должно быть видно:\n"
        "• Сумму перевода\n"
        "• Дату и время\n"
        "• Номер операции\n\n"
        "Отправьте PDF-документ:"
    )
    await callback.answer()


@router.message(ExchangeStates.uploading_receipt, F.document)
async def process_receipt_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: Database,
    payment_service: PaymentService
):
    """
    Обработка загруженного PDF-чека.
    Сохраняет файл, обновляет статус заявки на 'paid' и уведомляет админов.
    """
    if message.document.mime_type != "application/pdf":
        await message.answer("❌ Пожалуйста, отправьте файл в формате PDF.")
        return

    data = await state.get_data()
    order_id = data.get('order_id')

    document = message.document
    file = await bot.get_file(document.file_id)

    file_path = os.path.join(receipts_dir, f"receipt_{order_id}_{document.file_id}.pdf")
    await bot.download_file(file.file_path, file_path)

    # Сохраняем чек в заявке и меняем статус на 'paid'
    await payment_service.save_receipt(order_id, file_path)

    order = await db.get_order(order_id)

    safe_address = html.escape(order.crypto_address)
    text = (
        f"✅ <b>PDF-чек получен!</b>\n\n"
        f"📋 <b>Заявка #{order.id}</b>\n"
        f"Криптовалюта: {order.crypto_type}\n"
        f"Сумма к оплате: {order.amount_rub:,.0f} ₽\n"
        f"Вы получите: {order.amount_crypto:.8f} {order.crypto_type}\n"
        f"Кошелёк: <code>{safe_address}</code>\n\n"
        f"Заявка передана на проверку.\n"
        f"Ожидайте подтверждения оплаты и отправки криптовалюты.\n\n"
        f"⏱ Обычно это занимает 5-15 минут.\n\n"
        f"Если вы ошиблись, вы можете отменить заявку."
    )

    await message.answer(
        text,
        reply_markup=order_info_keyboard(order_id),
        parse_mode="HTML"
    )

    # Уведомляем админов о получении чека
    await payment_service.notify_admins_about_receipt(
        bot=bot,
        order_id=order_id,
        user_id=message.from_user.id,
        username=message.from_user.username,
        amount_rub=order.amount_rub,
        amount_crypto=order.amount_crypto,
        crypto_type=order.crypto_type,
        crypto_address=order.crypto_address,
        file_path=file_path
    )

    await state.clear()


@router.message(ExchangeStates.uploading_receipt)
async def process_invalid_receipt(message: Message, state: FSMContext):
    """
    Обработка случая, когда пользователь отправил не PDF, а что-то другое.
    """
    await message.answer("❌ Пожалуйста, отправьте PDF-файл с чеком.")


# ==================== ОТМЕНА ЗАЯВКИ ПОЛЬЗОВАТЕЛЕМ ====================

@router.callback_query(F.data.startswith("cancel_order_"))
async def process_cancel_order(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    bot: Bot
):
    """
    Обработка отмены заявки пользователем.
    Меняет статус на 'cancelled' и уведомляет администраторов.
    """
    order_id = int(callback.data.split("_")[2])

    await db.update_order_status(order_id, "cancelled", "Отменено пользователем")

    order = await db.get_order(order_id)
    if order:
        safe_username = html.escape(order.username) if order.username else 'N/A'
        admin_text = (
            f"❌ <b>Заявка #{order.id} отменена пользователем</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {order.user_id})\n"
            f"Криптовалюта: {order.crypto_type}\n"
            f"Сумма к оплате: {order.amount_rub:,.0f} ₽\n"
            f"Сумма к получению: {order.amount_crypto:.8f} {order.crypto_type}\n"
            f"Кошелек: <code>{html.escape(order.crypto_address)}</code>\n"
            f"Время отмены: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await notify_admins(bot, admin_text)

    await callback.message.edit_text(
        f"❌ Заявка #{order_id} отменена.\n\n"
        f"Если у вас возникли вопросы, обратитесь в поддержку."
    )
    await callback.answer("Заявка отменена")

    await state.clear()