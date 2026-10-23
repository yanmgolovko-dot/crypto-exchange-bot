# bot/keyboards/inline.py
"""Inline-клавиатуры для бота"""

from typing import List
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def exchange_input_currency_keyboard(action: str, coin: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты ввода (рубли или крипта) для P2P"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇷🇺 В рублях", callback_data=f"exch_input_{action}_{coin}_rub")
    keyboard.button(text=f"🪙 В {coin}", callback_data=f"exch_input_{action}_{coin}_crypto")
    keyboard.button(text="🔙 Отмена", callback_data="mode_exchange")
    keyboard.adjust(2, 1)
    return keyboard.as_markup()


def exchange_crypto_select_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора монеты для Обмена (Buy/Sell)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💵 USDT", callback_data=f"exch_{action}_USDT")
    keyboard.button(text="⚡ TRX", callback_data=f"exch_{action}_TRX")
    keyboard.button(text="₿ BTC", callback_data=f"exch_{action}_BTC")
    keyboard.button(text="Ł LTC", callback_data=f"exch_{action}_LTC")
    keyboard.button(text="🔙 Назад в меню", callback_data="mode_exchange")
    keyboard.adjust(2, 2, 1)
    return keyboard.as_markup()


def crypto_select_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора криптовалюты (BTC/LTC) для Шопа"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="₿ Bitcoin (BTC)", callback_data="buy_BTC")
    keyboard.button(text="Ł Litecoin (LTC)", callback_data="buy_LTC")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def currency_choice_keyboard(crypto_type: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты ввода (рубли/крипта) для Шопа"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇷🇺 В рублях", callback_data=f"currency_rub_{crypto_type}")
    keyboard.button(text="₿ В крипте", callback_data=f"currency_crypto_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_crypto")
    keyboard.adjust(2, 1)
    return keyboard.as_markup()


def amount_select_keyboard(crypto_type: str, amounts: List[int]) -> InlineKeyboardMarkup:
    """Клавиатура выбора предустановленных сумм в рублях."""
    keyboard = InlineKeyboardBuilder()
    for amount in amounts:
        keyboard.button(
            text=f"{amount:,} ₽".replace(",", " "),
            callback_data=f"amount_{crypto_type}_{amount}"
        )
    keyboard.button(text="✏️ Ввести свою сумму", callback_data=f"custom_amount_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_currency")
    rows = [2] * (len(amounts) // 2) + ([1] if len(amounts) % 2 else []) + [1, 1]
    keyboard.adjust(*rows)
    return keyboard.as_markup()


def coupons_selection_keyboard(coupons: list, skip_cb: str = "skip_promo") -> InlineKeyboardMarkup:
    """Клавиатура со списком доступных купонов пользователя."""
    kb = InlineKeyboardBuilder()
    for c in coupons:
        on_str = "на сумму" if c.discount_on == 'order' else "на комиссию"
        if c.discount_type == 'percent':
            val = f"{c.discount_value}%"
        else:
            val = f"{c.discount_value:,.0f} ₽"
        kb.button(text=f"🎫 {c.code} (-{val} {on_str})", callback_data=f"apply_coupon_{c.code}")
    
    kb.button(text="✏️ Ввести промокод вручную", callback_data="promo_manual")
    kb.button(text="⏩ Пропустить", callback_data=skip_cb)
    kb.adjust(1)
    return kb.as_markup()


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
    keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order_id}")
    keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(2, 2, 1)
    return keyboard.as_markup()


def manual_pending_keyboard(order_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def auto_pending_keyboard(order_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def receipt_received_keyboard(order_id: int) -> InlineKeyboardMarkup:
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


def cancel_creation_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отменить", callback_data="cancel_order_creation")
    return keyboard.as_markup()