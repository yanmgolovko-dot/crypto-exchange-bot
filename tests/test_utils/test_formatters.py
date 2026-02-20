"""Функции форматирования данных"""

import re
from datetime import datetime

def format_number(num: float, decimals: int = 0) -> str:
    """Форматирование числа с разделителями тысяч"""
    if decimals > 0:
        return f"{num:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{num:,.0f}".replace(",", " ")

def format_crypto(amount: float, crypto_type: str) -> str:
    """Форматирование суммы криптовалюты"""
    return f"{amount:.8f}"

def mask_card_number(card_number: str) -> str:
    """
    Маскирование номера карты.
    Если длина номера меньше 16, возвращаем как есть (короткие номера не маскируем).
    Иначе возвращаем в формате "1234 **** **** 5678".
    """
    if len(card_number) < 16:
        return card_number
    return f"{card_number[:4]} **** **** {card_number[-4:]}"

def format_datetime(dt_str: str) -> str:
    """Форматирование даты и времени"""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return dt_str

def get_time_ago(dt_str: str) -> str:
    """Получение строки 'N минут назад'"""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        now = datetime.now()
        diff = now - dt
        if diff.days > 0:
            return f"{diff.days} дн. назад"
        elif diff.seconds >= 3600:
            return f"{diff.seconds // 3600} ч. назад"
        elif diff.seconds >= 60:
            return f"{diff.seconds // 60} мин. назад"
        else:
            return "только что"
    except:
        return dt_str

def truncate_string(s: str, max_length: int = 50, suffix: str = "...") -> str:
    """Обрезка строки"""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix

def format_percent(value: float) -> str:
    if value == int(value):
        return f"{int(value)}%"
    return f"{value:.1f}%"

def get_status_emoji(status: str) -> str:
    emojis = {
        'pending': '⏳',
        'paid': '💳',
        'completed': '✅',
        'cancelled': '❌',
        'rejected': '🚫'
    }
    return emojis.get(status, '❓')

def get_status_text(status: str) -> str:
    texts = {
        'pending': 'Ожидает оплаты',
        'paid': 'На проверке',
        'completed': 'Выполнена',
        'cancelled': 'Отменена',
        'rejected': 'Отклонена'
    }
    return texts.get(status, 'Неизвестно')