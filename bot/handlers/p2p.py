# bot/handlers/p2p.py
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.order_service import OrderService
from bot.admin.main import notify_admins
from bot.keyboards import exchange_input_currency_keyboard
from bot.config.settings import config

logger = logging.getLogger(__name__)
router = Router()

class P2PStates(StatesGroup):
    waiting_amount = State()
    waiting_wallet_address = State()
    waiting_payment_details = State()

# 1. ВЫБОР МОНЕТЫ
@router.callback_query(F.data.startswith("exch_") & ~F.data.startswith("exch_input_"))
async def process_exchange_action(callback: CallbackQuery):
    parts = callback.data.split("_")
    action, coin = parts[1], parts[2]
    action_text = "купить" if action == "buy" else "продать"
    
    text = f"Вы хотите <b>{action_text} {coin}</b>.\n\nВ какой валюте вы хотите указать сумму?"
    
    try:
        await callback.message.edit_text(text, reply_markup=exchange_input_currency_keyboard(action, coin), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=exchange_input_currency_keyboard(action, coin), parse_mode="HTML")
    await callback.answer()

# 2. ВЫБОР ВАЛЮТЫ ВВОДА
@router.callback_query(F.data.startswith("exch_input_"))
async def process_exchange_input_currency(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    action, coin, currency = parts[2], parts[3], parts[4]

    await state.update_data(p2p_action=action, p2p_coin=coin, p2p_currency=currency)
    await state.set_state(P2PStates.waiting_amount)

    text = f"Введите сумму в {'рублях' if currency == 'rub' else coin}:"
    try:
        await callback.message.edit_text(text)
    except Exception:
        await callback.message.answer(text)
    await callback.answer()

# 3. ВВОД СУММЫ
@router.message(P2PStates.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0: raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную сумму (число больше нуля):")
        return

    data = await state.get_data()
    action, coin, currency = data.get('p2p_action'), data.get('p2p_coin'), data.get('p2p_currency')

    rate_key = f"rate_{coin.lower()}_{action}"
    rate_str = await db.get_setting(rate_key, "0")
    rate = float(rate_str)

    if rate <= 0:
        await message.answer("❌ Курс для этой операции временно не установлен.")
        await state.clear()
        return

    if action == "buy":
        rub_amount = amount if currency == "rub" else amount * rate
        crypto_amount = amount / rate if currency == "rub" else amount
        text = (
            f"📊 <b>Расчет:</b>\nВы платите: {rub_amount:,.2f} ₽\n"
            f"Вы получаете: {crypto_amount:.4f} {coin}\nКурс: {rate:,.2f} ₽\n\n"
            f"Введите адрес вашего кошелька <b>{coin}</b> для получения:"
        )
        await state.update_data(p2p_amount=rub_amount, p2p_crypto=crypto_amount)
        await state.set_state(P2PStates.waiting_wallet_address)
    else:
        crypto_amount = amount if currency == "crypto" else amount / rate
        rub_amount = amount * rate if currency == "crypto" else amount
        text = (
            f"📊 <b>Расчет:</b>\nВы продаете: {crypto_amount:.4f} {coin}\n"
            f"Вы получаете: {rub_amount:,.2f} ₽\nКурс: {rate:,.2f} ₽\n\n"
            f"Введите реквизиты карты (или номер телефона СБП):"
        )
        await state.update_data(p2p_amount=crypto_amount, p2p_rub=rub_amount)
        await state.set_state(P2PStates.waiting_payment_details)

    await message.answer(text, parse_mode="HTML")

# 4. ПОКУПКА: ВВОД АДРЕСА И СОХРАНЕНИЕ
@router.message(P2PStates.waiting_wallet_address)
async def process_buy_wallet(message: Message, state: FSMContext, bot: Bot, order_service: OrderService):
    wallet = message.text.strip()
    data = await state.get_data()
    await state.update_data(p2p_wallet=wallet)
    
    # СОХРАНЯЕМ В БАЗУ
    order_id = await order_service.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        crypto_type=data['p2p_coin'],
        amount_rub=data['p2p_amount'],
        amount_crypto=data['p2p_crypto'],
        rate=0, fee_percent=0,
        crypto_address=wallet,
        order_type='exch_buy',
        network="TRC20" if data['p2p_coin'] in ["USDT", "TRX"] else "Native"
    )
    
    text = (
        f"✅ <b>Заявка #{order_id} создана!</b>\n\n"
        f"Сумма к оплате: <b>{data['p2p_amount']:,.2f} ₽</b>\n"
        f"Вы получите: <b>{data['p2p_crypto']:.4f} {data['p2p_coin']}</b>\n\n"
        f"⚠️ Ожидайте, администратор отправит реквизиты для оплаты."
    )
    await message.answer(text, parse_mode="HTML")
    await state.clear()
    
    # Кнопка для админа
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order_id}")
    kb.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    kb.adjust(1)

    admin_text = (
        f"🔔 <b>Новая P2P заявка #{order_id} (Покупка)</b>\n"
        f"Клиент: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Валюта: {data['p2p_coin']}\nСумма: {data['p2p_amount']:,.2f} ₽\n"
        f"К получению: {data['p2p_crypto']:.4f} {data['p2p_coin']}\n"
        f"Кошелек: <code>{wallet}</code>"
    )
    
    # Отправляем всем админам с кнопками
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")

# 5. ПРОДАЖА: ВВОД РЕКВИЗИТОВ И СОХРАНЕНИЕ
@router.message(P2PStates.waiting_payment_details)
async def process_sell_details(message: Message, state: FSMContext, bot: Bot, order_service: OrderService):
    details = message.text.strip()
    data = await state.get_data()
    await state.update_data(p2p_details=details)
    
    wallet_to_pay = "TXYZ... (Адрес вашего кошелька USDT TRC20)" 
    if data['p2p_coin'] == 'BTC': wallet_to_pay = "bc1q..."
    
    # СОХРАНЯЕМ В БАЗУ
    order_id = await order_service.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        crypto_type=data['p2p_coin'],
        amount_rub=data['p2p_rub'],
        amount_crypto=data['p2p_amount'],
        rate=0, fee_percent=0,
        crypto_address=wallet_to_pay,
        order_type='exch_sell',
        network="TRC20" if data['p2p_coin'] in ["USDT", "TRX"] else "Native",
        user_payment_details=details
    )
    
    text = (
        f"✅ <b>Заявка #{order_id} создана!</b>\n\n"
        f"Вы продаете: <b>{data['p2p_amount']:.4f} {data['p2p_coin']}</b>\n"
        f"Вы получите: <b>{data['p2p_rub']:,.2f} ₽</b>\n"
        f"Реквизиты: <code>{details}</code>\n\n"
        f"⚠️ Переведите <b>{data['p2p_amount']:.4f} {data['p2p_coin']}</b> на адрес:\n"
        f"<code>{wallet_to_pay}</code>\n\n"
        f"После перевода пришлите ХЕШ транзакции в этот чат."
    )
    await message.answer(text, parse_mode="HTML")
    await state.clear()
    
    # Кнопки для админа
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить оплату", callback_data=f"admin_approve_{order_id}")
    kb.button(text="❌ Отклонить", callback_data=f"admin_reject_{order_id}")
    kb.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    kb.adjust(2, 1)

    admin_text = (
        f"🔔 <b>Новая P2P заявка #{order_id} (Продажа)</b>\n"
        f"Клиент: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Валюта: {data['p2p_coin']}\nСумма: {data['p2p_amount']:.4f} {data['p2p_coin']}\n"
        f"К выплате: {data['p2p_rub']:,.2f} ₽\n"
        f"Реквизиты: <code>{details}</code>"
    )
    
    # Отправляем всем админам с кнопками
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")