"""Inline-клавиатуры для бота"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def crypto_select_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="₿ Bitcoin (BTC)", callback_data="buy_BTC")
    keyboard.button(text="Ł Litecoin (LTC)", callback_data="buy_LTC")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def currency_choice_keyboard(crypto_type: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇷🇺 В рублях", callback_data=f"currency_rub_{crypto_type}")
    keyboard.button(text="₿ В крипте", callback_data=f"currency_crypto_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_crypto")
    keyboard.adjust(2, 1)
    return keyboard.as_markup()


def amount_select_keyboard(crypto_type: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    amounts = [1000, 3000, 5000, 10000, 20000, 50000, 100000]
    for amount in amounts:
        keyboard.button(
            text=f"{amount:,} ₽".replace(",", " "),
            callback_data=f"amount_{crypto_type}_{amount}"
        )
    keyboard.button(text="✏️ Ввести свою сумму", callback_data=f"custom_amount_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_currency")
    keyboard.adjust(2, 2, 2, 1, 1)
    return keyboard.as_markup()


def confirm_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить", callback_data=f"confirm_order_{order_id}")
    keyboard.button(text="❌ Отменить", callback_data=f"cancel_order_{order_id}")
    keyboard.adjust(2)
    return keyboard.as_markup()


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить оплату", callback_data=f"admin_approve_{order_id}")
    keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(2, 1)
    return keyboard.as_markup()


def receipt_keyboard(order_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📎 Прикрепить чек", callback_data=f"upload_receipt_{order_id}")
    keyboard.button(text="❌ Отменить заявку", callback_data=f"cancel_order_{order_id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def order_info_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены для отображения информации о заявке"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отменить заявку", callback_data=f"cancel_order_{order_id}")
    return keyboard.as_markup()


def help_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📝 Как купить", callback_data="help_how_to_buy")
    keyboard.button(text="⏱ Время обработки", callback_data="help_processing_time")
    keyboard.button(text="💳 Способы оплаты", callback_data="help_payment_methods")
    keyboard.button(text="🔐 Безопасность", callback_data="help_security")
    keyboard.adjust(1)
    return keyboard.as_markup()