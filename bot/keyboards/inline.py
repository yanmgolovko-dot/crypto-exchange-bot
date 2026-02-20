# bot/keyboards/inline.py
"""Inline-клавиатуры для бота"""

from typing import List
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def crypto_select_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора криптовалюты (BTC/LTC)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="₿ Bitcoin (BTC)", callback_data="buy_BTC")
    keyboard.button(text="Ł Litecoin (LTC)", callback_data="buy_LTC")
    keyboard.button(text="🔙 Назад", callback_data="back_to_main")
    keyboard.adjust(1)
    return keyboard.as_markup()


def currency_choice_keyboard(crypto_type: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты ввода (рубли/крипта)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇷🇺 В рублях", callback_data=f"currency_rub_{crypto_type}")
    keyboard.button(text="₿ В крипте", callback_data=f"currency_crypto_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_crypto")
    keyboard.adjust(2, 1)
    return keyboard.as_markup()


def amount_select_keyboard(crypto_type: str, amounts: List[int]) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора предустановленных сумм в рублях.
    :param crypto_type: 'BTC' или 'LTC'
    :param amounts: список сумм для отображения (целые числа)
    """
    keyboard = InlineKeyboardBuilder()
    for amount in amounts:
        keyboard.button(
            text=f"{amount:,} ₽".replace(",", " "),
            callback_data=f"amount_{crypto_type}_{amount}"
        )
    keyboard.button(text="✏️ Ввести свою сумму", callback_data=f"custom_amount_{crypto_type}")
    keyboard.button(text="🔙 Назад", callback_data="back_to_currency")
    # Располагаем кнопки: по 2 в ряд для сумм, затем отдельно кнопки "своя сумма" и "назад"
    rows = [2] * (len(amounts) // 2) + ([1] if len(amounts) % 2 else []) + [1, 1]
    keyboard.adjust(*rows)
    return keyboard.as_markup()


def confirm_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания заявки"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить", callback_data=f"confirm_order_{order_id}")
    keyboard.button(text="❌ Отменить", callback_data=f"cancel_order_{order_id}")
    keyboard.adjust(2)
    return keyboard.as_markup()


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Полная клавиатура для админа (используется в меню управления заявкой).
    Содержит все возможные действия.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить оплату", callback_data=f"admin_approve_{order_id}")
    keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order_id}")
    keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order_id}")
    keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(2, 2, 1)  # 2+2+1
    return keyboard.as_markup()


def manual_pending_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для администратора при создании заявки в ручном режиме.
    Показывает только кнопки, актуальные на этапе ожидания ввода реквизитов.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Ввести реквизиты", callback_data=f"admin_enter_payment_details_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def auto_pending_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для администратора при создании заявки в автоматическом режиме.
    Показывает кнопки: запросить чек, написать клиенту.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📎 Запросить чек", callback_data=f"admin_request_receipt_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(1)
    return keyboard.as_markup()


def receipt_received_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для администратора при получении чека от пользователя.
    Позволяет подтвердить оплату, отклонить или написать клиенту.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить оплату", callback_data=f"admin_approve_{order_id}")
    keyboard.button(text="❌ Отклонить", callback_data=f"admin_reject_{order_id}")
    keyboard.button(text="💬 Написать клиенту", callback_data=f"admin_msg_{order_id}")
    keyboard.adjust(2, 1)  # первые две в ряд, третья отдельно
    return keyboard.as_markup()


def receipt_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для пользователя после получения реквизитов (кнопка загрузки чека)"""
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
    """Клавиатура раздела помощи"""
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📝 Как купить", callback_data="help_how_to_buy")
    keyboard.button(text="⏱ Время обработки", callback_data="help_processing_time")
    keyboard.button(text="💳 Способы оплаты", callback_data="help_payment_methods")
    keyboard.button(text="🔐 Безопасность", callback_data="help_security")
    keyboard.adjust(1)
    return keyboard.as_markup()


def cancel_creation_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой отмены создания заявки.
    Используется на этапе ввода адреса кошелька.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="❌ Отменить", callback_data="cancel_order_creation")
    return keyboard.as_markup()