# bot/handlers/p2p.py
"""
P2P-обмен: покупка и продажа USDT, TRX, BTC, LTC по ручным курсам.
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.services.validator import validate_crypto_address
from bot.keyboards import (
    exchange_input_currency_keyboard,
    exchange_menu_keyboard,
    order_info_keyboard,
    receipt_keyboard,
    manual_pending_keyboard,
    auto_pending_keyboard,
)
from bot.admin.main import notify_admins
from bot.utils.helpers import safe_edit_message, escape_html

logger = logging.getLogger(__name__)
router = Router()

COIN_NETWORKS = {
    'USDT': 'TRC20',
    'TRX': 'TRC20',
    'BTC': 'BTC',
    'LTC': 'LTC',
}

COIN_NAMES = {
    'USDT': '💵 USDT',
    'TRX': '⚡ TRX',
    'BTC': '₿ BTC',
    'LTC': 'Ł LTC',
}


class P2PStates(StatesGroup):
    entering_amount = State()
    entering_wallet = State()
    entering_payment_details = State()
    entering_client_tx_hash = State()  # Клиент вводит хеш после отправки крипты


def _fmt_rub(val) -> str:
    try:
        return f"{int(round(float(val))):,}".replace(',', ' ')
    except (ValueError, TypeError):
        return str(val)


def _fmt_crypto(val) -> str:
    try:
        return f"{float(val):,.8f}".replace(',', ' ')
    except (ValueError, TypeError):
        return str(val)


def _validate_address(address: str, coin: str) -> bool:
    a = (address or '').strip()
    if not a:
        return False
    if coin in ('USDT', 'TRX'):
        return a.startswith('T') and len(a) == 34
    try:
        return validate_crypto_address(a, coin)
    except Exception:
        return False


async def _get_rate(coin: str, action: str) -> float:
    key = f"rate_{coin.lower()}_{action}"
    val = await db.get_setting(key, "0")
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


@router.callback_query(F.data.regexp(r"^exch_(buy|sell)_(USDT|TRX|BTC|LTC)$"))
async def p2p_coin_selected(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    action, coin = parts[1], parts[2]

    rate = await _get_rate(coin, action)
    if rate <= 0:
        await callback.answer(
            f"⚠️ Курс для {COIN_NAMES[coin]} ({action}) не настроен. Обратитесь в поддержку.",
            show_alert=True,
        )
        return

    await state.update_data(p2p_action=action, p2p_coin=coin, p2p_rate=rate)

    verb = "купить" if action == "buy" else "продать"
    text = (
        f"{COIN_NAMES[coin]} — <b>{verb}</b>\n\n"
        f"Текущий курс: <b>{_fmt_rub(rate)} ₽</b> за 1 {coin}\n"
        f"Сеть: <b>{COIN_NETWORKS[coin]}</b>\n\n"
        f"В чём вы хотите ввести сумму?"
    )
    await safe_edit_message(
        callback.message,
        text,
        reply_markup=exchange_input_currency_keyboard(action, coin),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^exch_input_(buy|sell)_(USDT|TRX|BTC|LTC)_(rub|crypto)$"))
async def p2p_input_type_selected(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    action, coin, input_type = parts[2], parts[3], parts[4]

    rate = await _get_rate(coin, action)
    if rate <= 0:
        await callback.answer("⚠️ Курс не настроен", show_alert=True)
        return

    await state.update_data(
        p2p_action=action,
        p2p_coin=coin,
        p2p_rate=rate,
        p2p_input_type=input_type,
    )
    await state.set_state(P2PStates.entering_amount)

    if input_type == 'rub':
        prompt = "💰 Введите сумму в <b>рублях</b> (например, 1000 или 5000.50):"
    else:
        prompt = f"🪙 Введите количество <b>{coin}</b> (например, 10 или 0.001):"

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="p2p_cancel")

    await safe_edit_message(
        callback.message,
        f"{COIN_NAMES[coin]} — {'покупка' if action == 'buy' else 'продажа'}\n"
        f"Курс: {_fmt_rub(rate)} ₽\n\n{prompt}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(P2PStates.entering_amount)
async def p2p_amount_received(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Введите число текстом.")
        return

    try:
        amount = float(message.text.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число (например, 1000 или 10.5).")
        return

    data = await state.get_data()
    action = data.get('p2p_action')
    coin = data.get('p2p_coin')
    rate = data.get('p2p_rate')
    input_type = data.get('p2p_input_type')

    if not all([action, coin, rate, input_type]):
        await message.answer("❌ Ошибка: данные потеряны. Начните заново через меню.")
        await state.clear()
        return

    if input_type == 'rub':
        amount_rub = amount
        amount_crypto = amount_rub / rate
    else:
        amount_crypto = amount
        amount_rub = amount_crypto * rate

    await state.update_data(
        p2p_amount_rub=round(amount_rub, 2),
        p2p_amount_crypto=round(amount_crypto, 8),
    )

    network = COIN_NETWORKS.get(coin, '')
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="p2p_cancel")

    if action == 'buy':
        prompt = (
            f"📋 <b>Заявка на покупку {coin}</b>\n\n"
            f"Сумма к оплате: <b>{_fmt_rub(amount_rub)} ₽</b>\n"
            f"Вы получите: <b>{_fmt_crypto(amount_crypto)} {coin}</b>\n"
            f"Курс: {_fmt_rub(rate)} ₽\n"
            f"Сеть: <b>{network}</b>\n\n"
            f"Введите адрес вашего <b>{coin}</b>-кошелька:"
        )
        await state.set_state(P2PStates.entering_wallet)
    else:
        prompt = (
            f"📋 <b>Заявка на продажу {coin}</b>\n\n"
            f"Вы отправите: <b>{_fmt_crypto(amount_crypto)} {coin}</b>\n"
            f"Вы получите: <b>{_fmt_rub(amount_rub)} ₽</b>\n"
            f"Курс: {_fmt_rub(rate)} ₽\n"
            f"Сеть: <b>{network}</b>\n\n"
            f"Введите реквизиты для получения рублей:\n"
            f"<i>(номер карты / телефон / банк — например: 2200 1234 5678 9012, Сбер)</i>"
        )
        await state.set_state(P2PStates.entering_payment_details)

    await message.answer(prompt, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.message(P2PStates.entering_wallet)
async def p2p_wallet_received(
    message: Message,
    state: FSMContext,
    bot: Bot,
    payment_service: PaymentService,
    user_service: UserService,
):
    address = (message.text or '').strip()
    data = await state.get_data()
    coin = data.get('p2p_coin')
    network = COIN_NETWORKS.get(coin, '')

    if not _validate_address(address, coin):
        await message.answer(
            f"❌ Похоже, это не валидный {coin}-адрес ({network}).\n"
            f"Проверьте и отправьте ещё раз."
        )
        return

    await user_service.register_or_update(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    await _create_p2p_order(
        message=message,
        state=state,
        bot=bot,
        payment_service=payment_service,
        crypto_address=address,
        user_payment_details=None,
    )


@router.message(P2PStates.entering_payment_details)
async def p2p_details_received(
    message: Message,
    state: FSMContext,
    bot: Bot,
    payment_service: PaymentService,
    user_service: UserService,
):
    details = (message.text or '').strip()
    if len(details) < 5:
        await message.answer("❌ Реквизиты слишком короткие. Введите подробнее (карта, банк).")
        return

    await user_service.register_or_update(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    await _create_p2p_order(
        message=message,
        state=state,
        bot=bot,
        payment_service=payment_service,
        crypto_address='N/A',
        user_payment_details=details,
    )


async def _create_p2p_order(
    message: Message,
    state: FSMContext,
    bot: Bot,
    payment_service: PaymentService,
    crypto_address: str,
    user_payment_details,
):
    data = await state.get_data()
    action = data.get('p2p_action')
    coin = data.get('p2p_coin')
    rate = data.get('p2p_rate')
    amount_rub = data.get('p2p_amount_rub')
    amount_crypto = data.get('p2p_amount_crypto')
    network = COIN_NETWORKS.get(coin, '')

    if not all([action, coin, rate, amount_rub, amount_crypto]):
        await message.answer("❌ Ошибка: данные потеряны. Начните заново через меню.")
        await state.clear()
        return

    order_type = 'p2p_buy' if action == 'buy' else 'p2p_sell'
    username = message.from_user.username

    try:
        order_id = await db.create_order(
            user_id=message.from_user.id,
            username=username,
            crypto_type=coin,
            amount_rub=amount_rub,
            amount_crypto=amount_crypto,
            rate=rate,
            fee_percent=0,
            crypto_address=crypto_address,
            promo_code=None,
            discount_percent=0,
            coupon_id=None,
            order_type=order_type,
            network=network,
            user_payment_details=user_payment_details,
        )
    except Exception as e:
        logger.exception("Ошибка создания P2P-заявки: %s", e)
        await message.answer("❌ Не удалось создать заявку. Попробуйте позже.")
        await state.clear()
        return

    order = await db.get_order(order_id)
    public_number = order.public_order_number if order and order.public_order_number else order_id
    safe_username = escape_html(username) if username else 'N/A'

    if action == 'buy':
        payment_mode = await db.get_payment_mode()
        payment_source = await db.get_manual_payment_source()
        payment_info = await payment_service.get_bank_details_for_order(payment_mode, payment_source)

        if payment_info.get('success') and payment_info.get('auto'):
            text = (
                f"✅ <b>Заявка #{public_number} создана!</b>\n\n"
                f"💳 <b>Реквизиты для оплаты:</b>\n"
                f"Банк: {escape_html(payment_info['bank_name'])}\n"
                f"Карта: <code>{escape_html(payment_info['card_number'])}</code>\n"
                f"Получатель: {escape_html(payment_info['holder_name'])}\n\n"
                f"💰 <b>Сумма к переводу:</b> {_fmt_rub(amount_rub)} ₽\n"
                f"💵 <b>Вы получите:</b> {_fmt_crypto(amount_crypto)} {coin}\n"
                f"📬 На адрес: <code>{escape_html(crypto_address)}</code>\n\n"
                f"⚠️ После оплаты нажмите «Прикрепить чек» и отправьте PDF."
            )
            await message.answer(text, reply_markup=receipt_keyboard(order_id), parse_mode="HTML")
        else:
            text = (
                f"✅ <b>Заявка #{public_number} создана!</b>\n\n"
                f"Ожидайте — администратор пришлёт реквизиты для оплаты.\n\n"
                f"💰 Сумма: {_fmt_rub(amount_rub)} ₽\n"
                f"💵 Получите: {_fmt_crypto(amount_crypto)} {coin}\n"
            )
            await message.answer(text, reply_markup=order_info_keyboard(order_id), parse_mode="HTML")

        admin_text = (
            f"🔔 <b>P2P-покупка #{public_number}</b>\n\n"
            f"👤 @{safe_username} (ID: {message.from_user.id})\n"
            f"🪙 {coin} ({network})\n"
            f"💰 Оплата: {_fmt_rub(amount_rub)} ₽\n"
            f"💵 Получит: {_fmt_crypto(amount_crypto)} {coin}\n"
            f"📬 Адрес: <code>{escape_html(crypto_address)}</code>\n"
            f"💱 Курс: {_fmt_rub(rate)} ₽\n"
        )
        await notify_admins(
            bot,
            admin_text,
            reply_markup=(
                auto_pending_keyboard(order_id)
                if payment_info.get('auto')
                else manual_pending_keyboard(order_id)
            ),
        )
    else:
        text = (
            f"✅ <b>Заявка #{public_number} создана!</b>\n\n"
            f"Вы продаёте: <b>{_fmt_crypto(amount_crypto)} {coin}</b>\n"
            f"Вы получите: <b>{_fmt_rub(amount_rub)} ₽</b> на реквизиты:\n"
            f"<code>{escape_html(user_payment_details)}</code>\n\n"
            f"⏳ Ожидайте — администратор пришлёт вам адрес <b>{network}</b> для отправки криптовалюты."
        )
        await message.answer(text, reply_markup=order_info_keyboard(order_id), parse_mode="HTML")

        admin_text = (
            f"🔔 <b>P2P-продажа #{public_number}</b>\n\n"
            f"👤 @{safe_username} (ID: {message.from_user.id})\n"
            f"🪙 {coin} ({network})\n"
            f"💵 Клиент отправит: {_fmt_crypto(amount_crypto)} {coin}\n"
            f"💰 Клиент получит: {_fmt_rub(amount_rub)} ₽\n"
            f"📬 Реквизиты клиента: <code>{escape_html(user_payment_details)}</code>\n"
            f"💱 Курс: {_fmt_rub(rate)} ₽\n\n"
            f"⚠️ Отправьте клиенту адрес для приёма крипты через кнопку «🏦 Отправить адрес для крипты»."
        )
        
        # ИСПРАВЛЕНИЕ: Генерируем правильную клавиатуру для P2P Sell
        kb_sell = InlineKeyboardBuilder()
        kb_sell.button(text="🏦 Отправить адрес для крипты", callback_data=f"admin_p2p_address_{order_id}")
        kb_sell.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
        kb_sell.adjust(1)
        
        await notify_admins(bot, admin_text, reply_markup=kb_sell.as_markup())

    await state.clear()


# ==================== КЛИЕНТ ВВОДИТ ХЕШ ТРАНЗАКЦИИ (P2P SELL) ====================

@router.callback_query(F.data.startswith("p2p_client_confirm_tx_"))
async def p2p_client_confirm_tx_start(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[4])
    order = await db.get_order(order_id)

    if not order or order.user_id != callback.from_user.id:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return

    if order.status != 'pending':
        await callback.answer("❌ Эта заявка уже обрабатывается или закрыта.", show_alert=True)
        return

    await state.update_data(p2p_tx_order_id=order_id)
    await state.set_state(P2PStates.entering_client_tx_hash)

    await callback.message.answer(
        f"✏️ Введите <b>хеш транзакции</b> (TX Hash), подтверждающий отправку криптовалюты.\n"
        f"Для отмены введите /cancel.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(P2PStates.entering_client_tx_hash)
async def p2p_client_tx_hash_received(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Ввод хеша отменён.")
        return

    tx_hash = message.text.strip()
    if len(tx_hash) < 10:
        await message.answer("❌ Хеш слишком короткий. Скопируйте его из кошелька и попробуйте снова.")
        return

    data = await state.get_data()
    order_id = data.get('p2p_tx_order_id')
    order = await db.get_order(order_id)

    if not order:
        await message.answer("❌ Заявка не найдена.")
        await state.clear()
        return

    # Сохраняем хеш и меняем статус на 'paid' (ожидает проверки админом)
    await db.update_order_tx_hash(order_id, tx_hash, admin_id=0) # admin_id=0 значит сделал клиент
    await db.update_order_status(order_id, 'paid', admin_comment="Клиент отправил крипту, хеш прикреплён", expected_status='pending')

    await message.answer(
        f"✅ Хеш транзакции принят! Заявка #{order.public_order_number} переведена в статус «На проверке».\n"
        f"Ожидайте, администратор проверит поступление средств и переведёт вам рубли."
    )

    admin_text = (
        f"🔔 <b>Клиент прислал хеш по заявке #{order.public_order_number} (Продажа)</b>\n\n"
        f"👤 @{escape_html(order.username or 'N/A')}\n"
        f"🪙 {order.crypto_type} ({order.network})\n"
        f"🔗 Хеш: <code>{escape_html(tx_hash)}</code>\n\n"
        f"Проверьте поступление крипты и подтвердите заявку в разделе «Заявки»."
    )
    await notify_admins(bot, admin_text)
    await state.clear()


@router.callback_query(F.data == "p2p_cancel")
async def p2p_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_message(callback.message, "❌ Создание P2P-заявки отменено.")
    await callback.message.answer(
        "Выберите действие в меню 👇",
        reply_markup=exchange_menu_keyboard(),
    )
    await callback.answer()