# bot/keyboards/__init__.py
"""
Ре-экспорт всех клавиатур бота для удобного импорта:
    from bot.keyboards import main_menu_keyboard, coupons_selection_keyboard
"""

# Reply-клавиатуры
from .reply import (
    main_menu_keyboard,
    exchange_menu_keyboard,
    cancel_keyboard,
)

# Inline-клавиатуры
from .inline import (
    exchange_input_currency_keyboard,
    exchange_crypto_select_keyboard,
    crypto_select_keyboard,
    currency_choice_keyboard,
    amount_select_keyboard,
    coupons_selection_keyboard,
    confirm_order_keyboard,
    admin_order_keyboard,
    manual_pending_keyboard,
    auto_pending_keyboard,
    receipt_received_keyboard,
    receipt_keyboard,
    order_info_keyboard,
    help_keyboard,
    cancel_creation_keyboard,
)

__all__ = [
    # reply
    "main_menu_keyboard",
    "exchange_menu_keyboard",
    "cancel_keyboard",
    # inline
    "exchange_input_currency_keyboard",
    "exchange_crypto_select_keyboard",
    "crypto_select_keyboard",
    "currency_choice_keyboard",
    "amount_select_keyboard",
    "coupons_selection_keyboard",
    "confirm_order_keyboard",
    "admin_order_keyboard",
    "manual_pending_keyboard",
    "auto_pending_keyboard",
    "receipt_received_keyboard",
    "receipt_keyboard",
    "order_info_keyboard",
    "help_keyboard",
    "cancel_creation_keyboard",
]