# bot/order_creation/steps.py
"""
Модуль содержит классы, реализующие каждый шаг процесса создания заявки.
"""

import logging
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .dto import OrderCreationData
from .exceptions import ValidationError, StepError
from .validators import validate_amount_rub, validate_crypto_address_for_type, validate_promo_code_format
from bot.keyboards import (
    crypto_select_keyboard,
    currency_choice_keyboard,
    amount_select_keyboard,
    confirm_order_keyboard,
    cancel_creation_keyboard,
    receipt_keyboard,
    order_info_keyboard,
    admin_order_keyboard,
    manual_pending_keyboard,
    auto_pending_keyboard,
    receipt_received_keyboard,
    main_menu_keyboard,
    coupons_selection_keyboard
)
from bot.config.settings import config
from bot.admin.main import notify_admins
import html

logger = logging.getLogger(__name__)


class OrderCreationStep(ABC):
    def __init__(self, data: OrderCreationData, state: FSMContext):
        self.data = data
        self.state = state

    @abstractmethod
    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def get_next_step(self) -> Optional['OrderCreationStep']:
        pass

    async def display(self, message: Message, services: Dict[str, Any]):
        pass


class SelectCryptoStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага SelectCryptoStep")
        crypto_api = services['crypto_api']
        prices = await crypto_api.get_all_prices()
        text = "📊 Актуальные курсы:\n"
        if prices["BTC"]:
            text += f"• ₿ BTC: {prices['BTC']:,.0f} ₽\n"
        if prices["LTC"]:
            text += f"• Ł LTC: {prices['LTC']:,.0f} ₽\n"
        text += "\nВыберите криптовалюту для покупки:"
        await message.answer(text, reply_markup=crypto_select_keyboard())

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        return False

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге SelectCryptoStep")
        if callback.data.startswith("buy_"):
            crypto_type = callback.data.split("_")[1]
            self.data.crypto_type = crypto_type
            await callback.answer()
            return True
        elif callback.data == "back_to_main":
            await callback.message.delete()
            await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.crypto_type:
            return SelectCurrencyStep(self.data, self.state)
        return None


class SelectCurrencyStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        text = f"Выберите, в чём вы хотите ввести сумму для {self.data.crypto_type}:"
        await message.edit_text(text, reply_markup=currency_choice_keyboard(self.data.crypto_type))

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        return False

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data.startswith("currency_rub_"):
            self.data.input_type = 'rub'
            await callback.answer()
            return True
        elif callback.data.startswith("currency_crypto_"):
            self.data.input_type = 'crypto'
            await callback.answer()
            return True
        elif callback.data == "back_to_crypto":
            self.data.back_to_crypto = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_crypto:
            self.data.back_to_crypto = False
            return SelectCryptoStep(self.data, self.state)
        if self.data.input_type == 'rub':
            return EnterAmountRubStep(self.data, self.state)
        elif self.data.input_type == 'crypto':
            return EnterAmountCryptoStep(self.data, self.state)
        return None


class EnterAmountRubStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        crypto_api = services['crypto_api']
        db = services['db']
        rate = await crypto_api.get_btc_price_rub() if self.data.crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
        self.data.rate = rate
        min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
        max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
        standard_amounts = [1000, 3000, 5000, 10000, 20000, 50000, 100000, 200000, 500000]
        amounts = [a for a in standard_amounts if min_net <= a <= max_net]
        if not amounts:
            amounts = [int(min_net), int(max_net)]
            amounts = sorted(set(amounts))
        text = (
            f"💰 Покупка {self.data.crypto_type}\n\n"
            f"Текущий курс: {rate:,.0f} ₽\n\n"
            f"Выберите сумму, которую хотите получить (в рублях):"
        )
        await message.edit_text(text, reply_markup=amount_select_keyboard(self.data.crypto_type, amounts))

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        try:
            amount = float(message.text.replace(",", "."))
            if amount <= 0: raise ValueError
        except ValueError:
            await message.answer("❌ Введите корректное положительное число.")
            return False
        is_valid, error_msg = await validate_amount_rub(amount, services['db'])
        if not is_valid:
            await message.answer(f"❌ {error_msg}")
            return False
        self.data.amount = amount
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data.startswith("amount_"):
            amount = int(callback.data.split("_")[2])
            is_valid, error_msg = await validate_amount_rub(amount, services['db'])
            if not is_valid:
                await callback.answer(f"❌ {error_msg}", show_alert=True)
                return False
            self.data.amount = amount
            await callback.answer()
            return True
        elif callback.data.startswith("custom_amount_"):
            min_net = float(await services['db'].get_setting('min_amount', str(config.MIN_AMOUNT)))
            max_net = float(await services['db'].get_setting('max_amount', str(config.MAX_AMOUNT)))
            text = f"✏️ Введите желаемую сумму получения в рублях\n\nМинимум: {min_net:,.0f} ₽\nМаксимум: {max_net:,.0f} ₽\n\nВведите целое число:"
            await callback.message.edit_text(text)
            await callback.answer()
            return False
        elif callback.data == "back_to_currency":
            self.data.back_to_currency = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_currency:
            self.data.back_to_currency = False
            return SelectCurrencyStep(self.data, self.state)
        if self.data.amount is not None:
            return PromoOrCouponStep(self.data, self.state)
        return None


class EnterAmountCryptoStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        crypto_api = services['crypto_api']
        rate = await crypto_api.get_btc_price_rub() if self.data.crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
        self.data.rate = rate
        text = f"💰 Покупка {self.data.crypto_type}\n\nТекущий курс: {rate:,.0f} ₽\n\nВведите количество {self.data.crypto_type}, которое хотите получить (например, 0.001):"
        await message.edit_text(text)

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        try:
            crypto_amount = float(message.text.replace(",", "."))
            if crypto_amount <= 0: raise ValueError
        except ValueError:
            await message.answer("❌ Введите корректное положительное число.")
            return False
        net_equivalent = round(crypto_amount * self.data.rate, 2)
        is_valid, error_msg = await validate_amount_rub(net_equivalent, services['db'])
        if not is_valid:
            await message.answer(f"❌ Сумма в рублях эквивалентна {net_equivalent:,.0f} ₽. {error_msg}")
            return False
        self.data.amount = crypto_amount
        self.data.net_equivalent = net_equivalent
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data == "back_to_currency":
            self.data.back_to_currency = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_currency:
            self.data.back_to_currency = False
            return SelectCurrencyStep(self.data, self.state)
        if self.data.amount is not None:
            return PromoOrCouponStep(self.data, self.state)
        return None


class PromoOrCouponStep(OrderCreationStep):
    async def _get_order_amount(self) -> float:
        if self.data.input_type == 'rub': return self.data.amount or 0
        elif self.data.input_type == 'crypto': return (self.data.amount or 0) * (self.data.rate or 0)
        return 0

    async def display(self, message: Message, services: Dict[str, Any]):
        db = services['db']
        order_amount = await self._get_order_amount()
        coupons = await db.get_user_coupons(self.data.user_id)
        valid_coupons = []
        for c in coupons:
            ok, _, _ = await db.validate_coupon(c.code, self.data.user_id, order_amount)
            if ok: valid_coupons.append(c)
        if valid_coupons:
            text = f"🎁 <b>У вас есть купоны!</b>\n\nВыберите купон для скидки или пропустите этот шаг.\n\nСумма заявки: {order_amount:,.0f} ₽"
            keyboard = coupons_selection_keyboard(valid_coupons, skip_cb="skip_promo_or_coupon")
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            text = f"🎁 <b>Промокод или купон</b>\n\nЕсли у вас есть промокод или купон, введите его ниже.\nИли нажмите «Пропустить», чтобы продолжить без скидки."
            keyboard = InlineKeyboardBuilder().button(text="⏩ Пропустить", callback_data="skip_promo_or_coupon").button(text="🔙 Назад", callback_data="back_to_amount").as_markup()
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        code = message.text.strip()
        db = services['db']
        is_valid_promo, promo_msg, discount = await db.validate_promo_code(code, self.data.user_id)
        if is_valid_promo:
            self.data.promo_code = code
            self.data.discount_percent = discount
            await message.answer(f"✅ {html.escape(promo_msg)} Скидка: {discount}%")
            return True
        order_amount = await self._get_order_amount()
        is_valid_coupon, coupon_msg, coupon = await db.coupons.validate_coupon(code, self.data.user_id, order_amount)
        if is_valid_coupon and coupon:
            self.data.coupon_id = coupon.id
            self.data.coupon_code = coupon.code
            self.data.coupon_discount_type = coupon.discount_type
            self.data.coupon_discount_value = coupon.discount_value
            self.data.coupon_discount_on = coupon.discount_on
            await message.answer(f"✅ {coupon_msg}\nСкидка: {coupon.discount_value}{'%' if coupon.discount_type == 'percent' else '₽'} на {'всю сумму' if coupon.discount_on == 'order' else 'комиссию'}")
            return True
        await message.answer("❌ Код не найден или не может быть применён. Попробуйте ещё раз или нажмите «Пропустить».")
        return False

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data == "skip_promo_or_coupon":
            await callback.answer()
            return True
        elif callback.data == "back_to_amount":
            self.data.back_to_amount = True
            await callback.answer()
            return True
        elif callback.data.startswith("apply_coupon_"):
            code = callback.data.split("_")[2]
            order_amount = await self._get_order_amount()
            is_valid, msg, coupon = await services['db'].validate_coupon(code, self.data.user_id, order_amount)
            if is_valid:
                self.data.coupon_id = coupon.id
                self.data.coupon_code = coupon.code
                self.data.coupon_discount_type = coupon.discount_type
                self.data.coupon_discount_value = coupon.discount_value
                self.data.coupon_discount_on = coupon.discount_on
                await callback.message.answer(f"✅ Купон {code} применён!\nСкидка: {coupon.discount_value}{'%' if coupon.discount_type == 'percent' else '₽'} на {'всю сумму' if coupon.discount_on == 'order' else 'комиссию'}")
                await callback.answer()
                return True
            else:
                await callback.answer(f"❌ {msg}", show_alert=True)
                return False
        elif callback.data == "promo_manual":
            await callback.message.answer("🎁 <b>Промокод</b>\n\nВведите код промокода или нажмите «Пропустить»:", reply_markup=InlineKeyboardBuilder().button(text="⏩ Пропустить", callback_data="skip_promo_or_coupon").as_markup())
            await callback.answer()
            return False
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_amount:
            self.data.back_to_amount = False
            return EnterAmountRubStep(self.data, self.state) if self.data.input_type == 'rub' else EnterAmountCryptoStep(self.data, self.state)
        return EnterWalletStep(self.data, self.state)


class EnterWalletStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        keyboard = InlineKeyboardBuilder().button(text="❌ Отменить", callback_data="cancel_order_creation").button(text="🔙 Назад", callback_data="back_to_promo").adjust(1)
        await message.answer(f"Введите адрес вашего {self.data.crypto_type}-кошелька:", reply_markup=keyboard.as_markup())

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        address = message.text.strip()
        is_valid, error_msg = await validate_crypto_address_for_type(address, self.data.crypto_type)
        if not is_valid:
            await message.answer(f"❌ {error_msg}. Попробуйте ещё раз:")
            return False
        self.data.wallet_address = address
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data == "back_to_promo":
            self.data.back_to_promo = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_promo:
            self.data.back_to_promo = False
            return PromoOrCouponStep(self.data, self.state)
        if self.data.wallet_address:
            return ConfirmationStep(self.data, self.state)
        return None


class ConfirmationStep(OrderCreationStep):
    async def display(self, message: Message, services: Dict[str, Any]):
        order_service = services['order_service']
        calc_result = await order_service.calculate_order(
            crypto_type=self.data.crypto_type,
            input_type=self.data.input_type,
            amount=self.data.amount,
            discount_percent=self.data.discount_percent,
            rate=self.data.rate,
            coupon_data={'discount_type': self.data.coupon_discount_type, 'discount_value': self.data.coupon_discount_value, 'discount_on': self.data.coupon_discount_on} if self.data.coupon_id else None
        )
        if not calc_result:
            raise StepError("Не удалось рассчитать заявку. Попробуйте позже.")

        self.data.gross_amount = calc_result['gross_amount']
        self.data.net_amount = calc_result['net_amount']
        self.data.amount_crypto = calc_result['amount_crypto']
        self.data.fee_percent = calc_result['fee_percent']

        # СКРЫТАЯ КОМИССИЯ: клиент видит только сумму к получению и сумму к оплате
        text = (
            f"📋 <b>Подтверждение заявки</b>\n\n"
            f"Криптовалюта: {self.data.crypto_type}\n"
            f"💵 <b>Сумма к получению:</b> {self.data.net_amount:,.0f} ₽\n"
            f"💳 <b>Сумма к оплате:</b> {self.data.gross_amount:,.0f} ₽\n"
            f"Вы получите: {self.data.amount_crypto:.8f} {self.data.crypto_type}\n"
            f"Курс: {self.data.rate:,.0f} ₽\n\n"
        )
        if self.data.discount_percent:
            text += f"🎁 Скидка по промокоду: {self.data.discount_percent}%\n\n"
        if self.data.coupon_code:
            text += f"🎫 Купон {self.data.coupon_code} применён\n\n"
        text += "Подтвердите создание заявки:"

        await message.answer(text, reply_markup=confirm_order_keyboard(0))

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        if callback.data.startswith("confirm_order_"):
            if self.data.order_id:
                await callback.answer("Заявка уже создана.", show_alert=True)
                return True

            user_service = services.get('user_service')
            if user_service:
                try:
                    await user_service.register_or_update(self.data.user_id, self.data.username, None, None, bot=callback.bot)
                except Exception as e:
                    await callback.answer("Ошибка регистрации пользователя.", show_alert=True)
                    return True

            order_id = await services['order_service'].create_order(
                user_id=self.data.user_id, username=self.data.username, crypto_type=self.data.crypto_type,
                amount_rub=self.data.gross_amount, amount_crypto=self.data.amount_crypto, rate=self.data.rate,
                fee_percent=self.data.fee_percent, crypto_address=self.data.wallet_address, promo_code=self.data.promo_code,
                discount_percent=self.data.discount_percent, coupon_id=self.data.coupon_id
            )
            db = services['db']
            order = await db.get_order(order_id)
            self.data.public_order_number = order.public_order_number if order and order.public_order_number else order_id
            self.data.order_id = order_id
            if self.data.coupon_id:
                await db.coupons.use_coupon(self.data.coupon_id, self.data.user_id, order_id)
            await self._send_payment_info(callback, services)
            await callback.answer()
            return True
        elif callback.data.startswith("cancel_order_"):
            await callback.message.edit_text("❌ Создание заявки отменено.")
            await callback.answer()
            return True
        return False

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        return None

    async def _send_payment_info(self, callback: CallbackQuery, services: Dict[str, Any]):
        bot = services['bot']
        db = services['db']
        payment_service = services['payment_service']

        payment_mode = await db.get_payment_mode()
        payment_source = await db.get_manual_payment_source()
        payment_info = await payment_service.get_bank_details_for_order(payment_mode, payment_source)

        if not payment_info['success']:
            await callback.message.answer(f"❌ {payment_info['error']}")
            return

        display_order_number = self.data.public_order_number or self.data.order_id

        if payment_info['auto']:
            safe_card = html.escape(payment_info['card_number'])
            safe_holder = html.escape(payment_info['holder_name'])
            text = (
                f"✅ <b>Заявка #{display_order_number} создана!</b>\n\n"
                f"💳 <b>Реквизиты для оплаты:</b>\n"
                f"Банк: {payment_info['bank_name']}\n"
                f"Карта: <code>{safe_card}</code>\n"
                f"Получатель: {safe_holder}\n\n"
                f"💰 <b>Сумма к переводу:</b> {self.data.gross_amount:,.0f} ₽\n"
                f"💵 <b>Вы получите:</b> {self.data.amount_crypto:.8f} {self.data.crypto_type} "
                f"(эквивалент {self.data.net_amount:,.0f} ₽)\n\n"
                f"⚠️ <b>Важно!</b> После оплаты нажмите кнопку «Прикрепить чек» и отправьте PDF-файл с чеком.\n\n"
                f"⏱ Заявка будет обработана в течение 5-15 минут."
            )
            await callback.message.answer(text, reply_markup=receipt_keyboard(self.data.order_id), parse_mode="HTML")

            safe_username = html.escape(self.data.username) if self.data.username else 'N/A'
            safe_address = html.escape(self.data.wallet_address)
            admin_text = (
                f"🔔 <b>Новая заявка #{display_order_number}!</b>\n\n"
                f"Пользователь: @{safe_username} (ID: {self.data.user_id})\n"
                f"Крипта: {self.data.crypto_type}\n"
                f"Сумма к оплате: {self.data.gross_amount:,.0f} ₽\n"
                f"Сумма к получению: {self.data.net_amount:,.0f} ₽ → {self.data.amount_crypto:.8f} {self.data.crypto_type}\n"
                f"Кошелек: <code>{safe_address}</code>\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if self.data.promo_code: admin_text += f"\nПромокод: {self.data.promo_code} (-{self.data.discount_percent}%)"
            await notify_admins(bot, admin_text, reply_markup=auto_pending_keyboard(self.data.order_id))

        else:
            text = (
                f"✅ <b>Заявка #{display_order_number} создана!</b>\n\n"
                f"Ожидайте, администратор отправит вам реквизиты для оплаты в ближайшее время.\n\n"
                f"💰 <b>Сумма к переводу:</b> {self.data.gross_amount:,.0f} ₽\n"
                f"💵 <b>Вы получите:</b> {self.data.amount_crypto:.8f} {self.data.crypto_type} "
                f"(эквивалент {self.data.net_amount:,.0f} ₽)\n\n"
            )
            await callback.message.answer(text, reply_markup=order_info_keyboard(self.data.order_id), parse_mode="HTML")

            safe_username = html.escape(self.data.username) if self.data.username else 'N/A'
            safe_address = html.escape(self.data.wallet_address)
            admin_text = (
                f"🔔 <b>Новая заявка #{display_order_number} (ручной режим)!</b>\n\n"
                f"Пользователь: @{safe_username} (ID: {self.data.user_id})\n"
                f"Крипта: {self.data.crypto_type}\n"
                f"Сумма к оплате: {self.data.gross_amount:,.0f} ₽\n"
                f"Сумма к получению: {self.data.net_amount:,.0f} ₽ → {self.data.amount_crypto:.8f} {self.data.crypto_type}\n"
                f"Кошелек: <code>{safe_address}</code>\n"
                f"Требуется ввести реквизиты вручную.\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await notify_admins(bot, admin_text, reply_markup=manual_pending_keyboard(self.data.order_id))