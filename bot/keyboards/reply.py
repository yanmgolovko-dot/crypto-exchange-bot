# bot/keyboards/reply.py
"""Reply-клавиатуры для главного меню и отмены."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="💰 Купить криптовалюту")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="🎰 Колесо Фортуны")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="💬 Поддержка")],
        [KeyboardButton(text="📝 Отзывы")],
        [KeyboardButton(text="🔄 Сменить режим")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def exchange_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🔴 Купить (Обмен)"), KeyboardButton(text="🟢 Продать (Обмен)")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="🎰 Колесо Фортуны")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="💬 Поддержка")],
        [KeyboardButton(text="📝 Отзывы")],
        [KeyboardButton(text="🔄 Сменить режим")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)