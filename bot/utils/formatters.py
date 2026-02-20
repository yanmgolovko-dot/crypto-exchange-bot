# bot/utils/formatters.py
"""Функции форматирования данных для вывода пользователю."""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


def format_number(num: float, decimals: int = 0) -> str:
    """
    Форматирование числа с разделителями тысяч.
    :param num: число
    :param decimals: количество знаков после запятой
    :return: строка вида "1 234 567" или "1 234 567,89"
    """
    logger.debug(f"Форматирование числа: {num}, decimals={decimals}")
    if decimals > 0:
        result = f"{num:,.{decimals}f}".replace(",", " ").replace(".", ",")
    else:
        result = f"{num:,.0f}".replace(",", " ")
    logger.debug(f"Результат: {result}")
    return result


def format_crypto(amount: float, crypto_type: str) -> str:
    """
    Форматирование суммы криптовалюты (8 знаков после запятой).
    :param amount: количество криптовалюты
    :param crypto_type: 'BTC' или 'LTC'
    :return: строка с 8 знаками
    """
    logger.debug(f"Форматирование крипто-суммы: {amount} {crypto_type}")
    result = f"{amount:.8f}"
    logger.debug(f"Результат: {result}")
    return result


def mask_card_number(card_number: str) -> str:
    """
    Маскирование номера карты.
    Если длина номера меньше 16, возвращаем как есть (короткие номера не маскируем).
    Иначе возвращаем в формате "1234 **** **** 5678".
    """
    logger.debug(f"Маскирование номера карты: {card_number[:4]}...{card_number[-4:] if len(card_number) > 4 else ''}")
    if len(card_number) < 16:
        logger.debug("Слишком короткий номер, возвращаем без изменений")
        return card_number
    result = f"{card_number[:4]} **** **** {card_number[-4:]}"
    logger.debug(f"Результат: {result}")
    return result


def format_datetime(dt_str: str) -> str:
    """
    Форматирование даты и времени из ISO строки в формат ДД.ММ.ГГГГ ЧЧ:ММ.
    """
    logger.debug(f"Форматирование даты: {dt_str}")
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        result = dt.strftime("%d.%m.%Y %H:%M")
        logger.debug(f"Результат: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка парсинга даты '{dt_str}': {e}", exc_info=True)
        return dt_str


def get_time_ago(dt_str: str) -> str:
    """
    Получение строки вида "N минут назад", "N часов назад", "N дней назад".
    """
    logger.debug(f"Вычисление времени от {dt_str}")
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        now = datetime.now()
        diff = now - dt
        if diff.days > 0:
            result = f"{diff.days} дн. назад"
        elif diff.seconds >= 3600:
            result = f"{diff.seconds // 3600} ч. назад"
        elif diff.seconds >= 60:
            result = f"{diff.seconds // 60} мин. назад"
        else:
            result = "только что"
        logger.debug(f"Результат: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка вычисления времени от '{dt_str}': {e}", exc_info=True)
        return dt_str


def truncate_string(s: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Обрезка строки до максимальной длины с добавлением суффикса.
    """
    logger.debug(f"Обрезка строки длиной {len(s)} до {max_length} символов")
    if len(s) <= max_length:
        return s
    result = s[:max_length - len(suffix)] + suffix
    logger.debug(f"Результат: {result}")
    return result


def format_percent(value: float) -> str:
    """
    Форматирование процента: целое число выводится без десятых.
    """
    logger.debug(f"Форматирование процента: {value}")
    if value == int(value):
        result = f"{int(value)}%"
    else:
        result = f"{value:.1f}%"
    logger.debug(f"Результат: {result}")
    return result


def get_status_emoji(status: str) -> str:
    """
    Возвращает эмодзи для статуса заявки.
    """
    logger.debug(f"Получение эмодзи для статуса: {status}")
    emojis = {
        'pending': '⏳',
        'paid': '💳',
        'completed': '✅',
        'cancelled': '❌',
        'rejected': '🚫'
    }
    result = emojis.get(status, '❓')
    logger.debug(f"Результат: {result}")
    return result


def get_status_text(status: str) -> str:
    """
    Возвращает текстовое описание статуса заявки.
    """
    logger.debug(f"Получение текста для статуса: {status}")
    texts = {
        'pending': 'Ожидает оплаты',
        'paid': 'На проверке',
        'completed': 'Выполнена',
        'cancelled': 'Отменена',
        'rejected': 'Отклонена'
    }
    result = texts.get(status, 'Неизвестно')
    logger.debug(f"Результат: {result}")
    return result