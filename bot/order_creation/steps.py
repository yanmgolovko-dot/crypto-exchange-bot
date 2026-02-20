# bot/order_creation/steps.py
"""
Модуль содержит классы, реализующие каждый шаг процесса создания заявки.
Каждый шаг наследуется от абстрактного базового класса OrderCreationStep.
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
    main_menu_keyboard
)
from bot.config.settings import config
from bot.admin.main import notify_admins
import html

logger = logging.getLogger(__name__)


class OrderCreationStep(ABC):
    """
    Абстрактный базовый класс для всех шагов создания заявки.
    Определяет интерфейс для обработки сообщений и колбэков,
    а также для получения следующего шага.
    """

    def __init__(self, data: OrderCreationData, state: FSMContext):
        self.data = data
        self.state = state

    @abstractmethod
    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        """Обрабатывает входящее текстовое сообщение. Возвращает True, если шаг завершён."""
        pass

    @abstractmethod
    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        """Обрабатывает нажатие на инлайн-кнопку. Возвращает True, если шаг завершён."""
        pass

    @abstractmethod
    async def get_next_step(self) -> Optional['OrderCreationStep']:
        """Возвращает экземпляр следующего шага или None, если процесс завершён."""
        pass

    async def display(self, message: Message, services: Dict[str, Any]):
        """Опциональный метод для отображения интерфейса шага."""
        pass


class SelectCryptoStep(OrderCreationStep):
    """Шаг 1: выбор криптовалюты."""

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
            logger.info(f"[{self.data.user_id}] Выбрана криптовалюта: {crypto_type}")
            await callback.answer()
            return True
        elif callback.data == "back_to_main":
            logger.info(f"[{self.data.user_id}] Возврат в главное меню")
            # Удаляем текущее сообщение с инлайн-клавиатурой
            await callback.message.delete()
            # Отправляем новое сообщение с главным меню (reply-клавиатура)
            await callback.message.answer(
                "Главное меню:",
                reply_markup=main_menu_keyboard()
            )
            await callback.answer()
            # Завершаем процесс, следующий шаг не нужен
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.crypto_type:
            return SelectCurrencyStep(self.data, self.state)
        return None


class SelectCurrencyStep(OrderCreationStep):
    """Шаг 2: выбор валюты ввода (рубли или криптовалюта)."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага SelectCurrencyStep")
        text = f"Выберите, в чём вы хотите ввести сумму для {self.data.crypto_type}:"
        await message.edit_text(text, reply_markup=currency_choice_keyboard(self.data.crypto_type))

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        return False

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге SelectCurrencyStep")
        if callback.data.startswith("currency_rub_"):
            self.data.input_type = 'rub'
            logger.info(f"[{self.data.user_id}] Выбраны рубли")
            await callback.answer()
            return True
        elif callback.data.startswith("currency_crypto_"):
            self.data.input_type = 'crypto'
            logger.info(f"[{self.data.user_id}] Выбрана криптовалюта")
            await callback.answer()
            return True
        elif callback.data == "back_to_crypto":
            logger.info(f"[{self.data.user_id}] Возврат к выбору криптовалюты")
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
    """Шаг 3: ввод суммы в рублях (предустановленные или своя)."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага EnterAmountRubStep")
        crypto_api = services['crypto_api']
        db = services['db']

        rate = await crypto_api.get_btc_price_rub() if self.data.crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
        self.data.rate = rate
        logger.debug(f"[{self.data.user_id}] Текущий курс {self.data.crypto_type}: {rate}")

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
        logger.info(f"[{self.data.user_id}] Ввод своей суммы в рублях: {message.text}")
        try:
            amount = float(message.text.replace(",", "."))
            if amount <= 0:
                raise ValueError
        except ValueError:
            logger.warning(f"[{self.data.user_id}] Некорректный ввод числа: {message.text}")
            await message.answer("❌ Введите корректное положительное число.")
            return False

        db = services['db']
        is_valid, error_msg = await validate_amount_rub(amount, db)
        if not is_valid:
            logger.warning(f"[{self.data.user_id}] Сумма {amount} не прошла валидацию: {error_msg}")
            await message.answer(f"❌ {error_msg}")
            return False

        self.data.amount = amount
        logger.info(f"[{self.data.user_id}] Сумма {amount} принята.")
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге EnterAmountRubStep")
        if callback.data.startswith("amount_"):
            amount = int(callback.data.split("_")[2])
            db = services['db']
            is_valid, error_msg = await validate_amount_rub(amount, db)
            if not is_valid:
                logger.warning(f"[{self.data.user_id}] Предустановленная сумма {amount} не прошла валидацию: {error_msg}")
                await callback.answer(f"❌ {error_msg}", show_alert=True)
                return False
            self.data.amount = amount
            logger.info(f"[{self.data.user_id}] Выбрана предустановленная сумма: {amount}")
            await callback.answer()
            return True
        elif callback.data.startswith("custom_amount_"):
            logger.info(f"[{self.data.user_id}] Переход к ручному вводу суммы")
            min_net = float(await services['db'].get_setting('min_amount', str(config.MIN_AMOUNT)))
            max_net = float(await services['db'].get_setting('max_amount', str(config.MAX_AMOUNT)))
            text = (
                f"✏️ Введите желаемую сумму получения в рублях\n\n"
                f"Минимум: {min_net:,.0f} ₽\n"
                f"Максимум: {max_net:,.0f} ₽\n\n"
                f"Введите целое число:"
            )
            await callback.message.edit_text(text)
            await callback.answer()
            return False
        elif callback.data == "back_to_currency":
            logger.info(f"[{self.data.user_id}] Возврат к выбору валюты")
            self.data.back_to_currency = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_currency:
            self.data.back_to_currency = False
            return SelectCurrencyStep(self.data, self.state)
        if self.data.amount is not None:
            return PromoCodeStep(self.data, self.state)
        return None


class EnterAmountCryptoStep(OrderCreationStep):
    """Шаг 3': ввод количества криптовалюты."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага EnterAmountCryptoStep")
        crypto_api = services['crypto_api']
        rate = await crypto_api.get_btc_price_rub() if self.data.crypto_type == "BTC" else await crypto_api.get_ltc_price_rub()
        self.data.rate = rate
        logger.debug(f"[{self.data.user_id}] Текущий курс {self.data.crypto_type}: {rate}")
        text = (
            f"💰 Покупка {self.data.crypto_type}\n\n"
            f"Текущий курс: {rate:,.0f} ₽\n\n"
            f"Введите количество {self.data.crypto_type}, которое хотите получить (например, 0.001):"
        )
        await message.edit_text(text)

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Ввод количества криптовалюты: {message.text}")
        try:
            crypto_amount = float(message.text.replace(",", "."))
            if crypto_amount <= 0:
                raise ValueError
        except ValueError:
            logger.warning(f"[{self.data.user_id}] Некорректный ввод числа: {message.text}")
            await message.answer("❌ Введите корректное положительное число.")
            return False

        net_equivalent = crypto_amount * self.data.rate
        net_equivalent = round(net_equivalent, 2)
        logger.debug(f"[{self.data.user_id}] Эквивалент в рублях: {net_equivalent}")

        db = services['db']
        is_valid, error_msg = await validate_amount_rub(net_equivalent, db)
        if not is_valid:
            logger.warning(f"[{self.data.user_id}] Сумма {crypto_amount} {self.data.crypto_type} не прошла валидацию: {error_msg}")
            await message.answer(f"❌ Сумма в рублях эквивалентна {net_equivalent:,.0f} ₽. {error_msg}")
            return False

        self.data.amount = crypto_amount
        self.data.net_equivalent = net_equivalent
        logger.info(f"[{self.data.user_id}] Количество {crypto_amount} {self.data.crypto_type} принято.")
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.debug(f"[{self.data.user_id}] Получен callback на шаге EnterAmountCryptoStep")
        if callback.data == "back_to_currency":
            logger.info(f"[{self.data.user_id}] Возврат к выбору валюты")
            self.data.back_to_currency = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_currency:
            self.data.back_to_currency = False
            return SelectCurrencyStep(self.data, self.state)
        if self.data.amount is not None:
            return PromoCodeStep(self.data, self.state)
        return None


class PromoCodeStep(OrderCreationStep):
    """Шаг 4: ввод промокода (опционально)."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага PromoCodeStep")
        text = (
            f"🎁 <b>Промокод</b>\n\n"
            f"У вас есть промокод?\n"
            f"Введите код для получения скидки или нажмите «Пропустить»:"
        )
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="⏩ Пропустить", callback_data="skip_promo")
        keyboard.button(text="🔙 Назад", callback_data="back_to_amount")
        keyboard.adjust(1)
        await message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        code = message.text.strip()
        logger.info(f"[{self.data.user_id}] Ввод промокода: {code}")
        if not validate_promo_code_format(code):
            logger.warning(f"[{self.data.user_id}] Некорректный формат промокода: {code}")
            await message.answer("❌ Некорректный формат промокода. Попробуйте ещё раз или нажмите «Пропустить».")
            return False

        db = services['db']
        is_valid, msg, discount = await db.validate_promo_code(code, self.data.user_id)
        if is_valid:
            self.data.promo_code = code
            self.data.discount_percent = discount
            logger.info(f"[{self.data.user_id}] Промокод {code} применён, скидка {discount}%")
            await message.answer(f"✅ {html.escape(msg)} Скидка: {discount}%")
        else:
            logger.info(f"[{self.data.user_id}] Промокод {code} недействителен: {msg}")
            await message.answer(f"❌ {html.escape(msg)} Продолжаем без скидки.")
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге PromoCodeStep")
        if callback.data == "skip_promo":
            logger.info(f"[{self.data.user_id}] Пропуск промокода")
            await callback.answer()
            return True
        elif callback.data == "back_to_amount":
            logger.info(f"[{self.data.user_id}] Возврат к выбору суммы")
            self.data.back_to_amount = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_amount:
            self.data.back_to_amount = False
            if self.data.input_type == 'rub':
                return EnterAmountRubStep(self.data, self.state)
            else:
                return EnterAmountCryptoStep(self.data, self.state)
        # После промокода всегда переходим к вводу адреса
        return EnterWalletStep(self.data, self.state)


class EnterWalletStep(OrderCreationStep):
    """Шаг 5: ввод адреса кошелька."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага EnterWalletStep")
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="❌ Отменить", callback_data="cancel_order_creation")
        keyboard.button(text="🔙 Назад", callback_data="back_to_promo")
        keyboard.adjust(1)
        await message.answer(
            f"Введите адрес вашего {self.data.crypto_type}-кошелька:",
            reply_markup=keyboard.as_markup()
        )

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        address = message.text.strip()
        logger.info(f"[{self.data.user_id}] Ввод адреса кошелька: {address}")
        is_valid, error_msg = await validate_crypto_address_for_type(address, self.data.crypto_type)
        if not is_valid:
            logger.warning(f"[{self.data.user_id}] Некорректный адрес {address}: {error_msg}")
            await message.answer(f"❌ {error_msg}. Попробуйте ещё раз:")
            return False
        self.data.wallet_address = address
        logger.info(f"[{self.data.user_id}] Адрес {address} принят.")
        return True

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.debug(f"[{self.data.user_id}] Получен callback на шаге EnterWalletStep")
        if callback.data == "back_to_promo":
            logger.info(f"[{self.data.user_id}] Возврат к вводу промокода")
            self.data.back_to_promo = True
            await callback.answer()
            return True
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        if self.data.back_to_promo:
            self.data.back_to_promo = False
            return PromoCodeStep(self.data, self.state)
        if self.data.wallet_address:
            return ConfirmationStep(self.data, self.state)
        return None


class ConfirmationStep(OrderCreationStep):
    """Шаг 6: подтверждение, расчёт и создание заявки."""

    async def display(self, message: Message, services: Dict[str, Any]):
        logger.info(f"[{self.data.user_id}] Отображение шага ConfirmationStep")
        order_service = services['order_service']
        calc_result = await order_service.calculate_order(
            crypto_type=self.data.crypto_type,
            input_type=self.data.input_type,
            amount=self.data.amount,
            discount_percent=self.data.discount_percent,
            rate=self.data.rate
        )
        if not calc_result:
            logger.error(f"[{self.data.user_id}] Не удалось рассчитать заявку")
            raise StepError("Не удалось рассчитать заявку. Попробуйте позже.")

        self.data.gross_amount = calc_result['gross_amount']
        self.data.net_amount = calc_result['net_amount']
        self.data.amount_crypto = calc_result['amount_crypto']
        self.data.fee_percent = calc_result['fee_percent']
        logger.debug(f"[{self.data.user_id}] Расчёт: gross={self.data.gross_amount}, net={self.data.net_amount}, crypto={self.data.amount_crypto}")

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
        text += "Подтвердите создание заявки:"

        await message.answer(text, reply_markup=confirm_order_keyboard(0))

    async def process_callback(self, callback: CallbackQuery, services: Dict[str, Any]) -> bool:
        logger.info(f"[{self.data.user_id}] Обработка callback {callback.data} на шаге ConfirmationStep")
        if callback.data.startswith("confirm_order_"):
            order_service = services['order_service']
            order_id = await order_service.create_order(
                user_id=self.data.user_id,
                username=self.data.username,
                crypto_type=self.data.crypto_type,
                amount_rub=self.data.gross_amount,
                amount_crypto=self.data.amount_crypto,
                rate=self.data.rate,
                fee_percent=self.data.fee_percent,
                crypto_address=self.data.wallet_address,
                promo_code=self.data.promo_code,
                discount_percent=self.data.discount_percent
            )
            self.data.order_id = order_id
            logger.info(f"[{self.data.user_id}] Заявка #{order_id} создана")
            await self._send_payment_info(callback, services)
            await callback.answer()
            return True
        elif callback.data.startswith("cancel_order_"):
            logger.info(f"[{self.data.user_id}] Отмена создания заявки")
            await callback.message.edit_text("❌ Создание заявки отменено.")
            await callback.answer()
            return True
        return False

    async def process_message(self, message: Message, services: Dict[str, Any]) -> bool:
        logger.debug(f"[{self.data.user_id}] Получено сообщение на шаге ConfirmationStep (игнорируется)")
        return False

    async def get_next_step(self) -> Optional[OrderCreationStep]:
        return None

    async def _send_payment_info(self, callback: CallbackQuery, services: Dict[str, Any]):
        """
        Внутренний метод для отправки пользователю реквизитов и уведомления админов.
        Использует разные клавиатуры в зависимости от режима оплаты.
        """
        logger.info(f"[{self.data.user_id}] Отправка платёжной информации по заявке #{self.data.order_id}")
        bot = services['bot']
        db = services['db']
        payment_service = services['payment_service']

        payment_mode = await db.get_payment_mode()
        payment_source = await db.get_manual_payment_source()
        logger.debug(f"Режим оплаты: {payment_mode}, источник: {payment_source}")

        payment_info = await payment_service.get_bank_details_for_order(payment_mode, payment_source)

        if not payment_info['success']:
            logger.error(f"Ошибка получения реквизитов: {payment_info.get('error')}")
            await callback.message.answer(f"❌ {payment_info['error']}")
            return

        if payment_info['auto']:
            # Автоматический режим (реквизиты из БД)
            safe_card = html.escape(payment_info['card_number'])
            safe_holder = html.escape(payment_info['holder_name'])
            text = (
                f"✅ <b>Заявка #{self.data.order_id} создана!</b>\n\n"
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
            logger.info(f"[{self.data.user_id}] Пользователю отправлены автоматические реквизиты")

            # Уведомление админов для автоматического режима
            safe_username = html.escape(self.data.username) if self.data.username else 'N/A'
            safe_address = html.escape(self.data.wallet_address)
            admin_text = (
                f"🔔 <b>Новая заявка #{self.data.order_id}!</b>\n\n"
                f"Пользователь: @{safe_username} (ID: {self.data.user_id})\n"
                f"Крипта: {self.data.crypto_type}\n"
                f"Сумма к оплате: {self.data.gross_amount:,.0f} ₽\n"
                f"Сумма к получению: {self.data.net_amount:,.0f} ₽ → {self.data.amount_crypto:.8f} {self.data.crypto_type}\n"
                f"Кошелек: <code>{safe_address}</code>\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if self.data.promo_code:
                admin_text += f"\nПромокод: {self.data.promo_code} (-{self.data.discount_percent}%)"
            await notify_admins(bot, admin_text, reply_markup=auto_pending_keyboard(self.data.order_id))
            logger.info(f"Администраторы уведомлены о новой заявке #{self.data.order_id} (авторежим)")

        else:
            # Ручной режим (реквизиты вводятся админом)
            text = (
                f"✅ <b>Заявка #{self.data.order_id} создана!</b>\n\n"
                f"Ожидайте, администратор отправит вам реквизиты для оплаты в ближайшее время.\n\n"
                f"💰 <b>Сумма к переводу:</b> {self.data.gross_amount:,.0f} ₽\n"
                f"💵 <b>Вы получите:</b> {self.data.amount_crypto:.8f} {self.data.crypto_type} "
                f"(эквивалент {self.data.net_amount:,.0f} ₽)\n\n"
            )
            await callback.message.answer(text, reply_markup=order_info_keyboard(self.data.order_id), parse_mode="HTML")
            logger.info(f"[{self.data.user_id}] Пользователю отправлено сообщение об ожидании реквизитов")

            # Уведомление админов для ручного режима
            safe_username = html.escape(self.data.username) if self.data.username else 'N/A'
            safe_address = html.escape(self.data.wallet_address)
            admin_text = (
                f"🔔 <b>Новая заявка #{self.data.order_id} (ручной режим)!</b>\n\n"
                f"Пользователь: @{safe_username} (ID: {self.data.user_id})\n"
                f"Крипта: {self.data.crypto_type}\n"
                f"Сумма к оплате: {self.data.gross_amount:,.0f} ₽\n"
                f"Сумма к получению: {self.data.net_amount:,.0f} ₽ → {self.data.amount_crypto:.8f} {self.data.crypto_type}\n"
                f"Кошелек: <code>{safe_address}</code>\n"
                f"Требуется ввести реквизиты вручную.\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await notify_admins(bot, admin_text, reply_markup=manual_pending_keyboard(self.data.order_id))
            logger.info(f"Администраторы уведомлены о новой заявке #{self.data.order_id} (ручной режим)")