# bot/keyboards/reply.py
"""Reply-клавиатуры для главного меню и отмены."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Главное меню бота.
    Содержит кнопки для основных разделов.
    """
    keyboard = [
        [KeyboardButton(text="💰 Купить криптовалюту")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="💬 Поддержка")],
        [KeyboardButton(text="📝 Отзывы")],  # кнопка для публичных отзывов
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура с одной кнопкой "❌ Отменить".
    Используется для отмены действий в состояниях FSM.
    """
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)