"""Reply-клавиатуры"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню (без кнопки Курсы)"""
    keyboard = [
        [KeyboardButton(text="💰 Купить криптовалюту")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="👤 Личный кабинет")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="💬 Поддержка")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура отмены"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)