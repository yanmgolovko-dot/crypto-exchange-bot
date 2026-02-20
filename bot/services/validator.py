# bot/services/validator.py
"""
Модуль для валидации криптовалютных адресов.
Поддерживает проверку адресов Bitcoin и Litecoin в различных форматах.
"""

import re
import logging

logger = logging.getLogger(__name__)


def validate_btc_address(address: str) -> bool:
    """
    Проверяет, является ли строка корректным Bitcoin-адресом.
    Поддерживаемые форматы:
    - Legacy (P2PKH): начинается с 1, длина 34 символа
    - P2SH: начинается с 3, длина 34 символа
    - Bech32: начинается с bc1, длина от 42 до 62 символов
    """
    if not address:
        logger.debug("Передан пустой адрес для валидации BTC")
        return False

    logger.debug(f"Валидация BTC адреса: {address}")

    # Legacy addresses (1...)
    if address.startswith('1') and len(address) == 34:
        result = bool(re.match(r'^[1][a-zA-Z0-9]{33}$', address))
        logger.debug(f"Legacy адрес BTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    # P2SH addresses (3...)
    if address.startswith('3') and len(address) == 34:
        result = bool(re.match(r'^[3][a-zA-Z0-9]{33}$', address))
        logger.debug(f"P2SH адрес BTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    # Bech32 addresses (bc1...)
    if address.startswith('bc1') and 42 <= len(address) <= 62:
        result = bool(re.match(r'^bc1[a-zA-Z0-9]{39,59}$', address))
        logger.debug(f"Bech32 адрес BTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    logger.debug(f"Адрес BTC не соответствует ни одному известному формату: {address}")
    return False


def validate_ltc_address(address: str) -> bool:
    """
    Проверяет, является ли строка корректным Litecoin-адресом.
    Поддерживаемые форматы:
    - Legacy (P2PKH): начинается с L, длина 34 символа
    - P2SH: начинается с M, длина 34 символа
    - Bech32: начинается с ltc1, длина от 42 до 62 символов
    """
    if not address:
        logger.debug("Передан пустой адрес для валидации LTC")
        return False

    logger.debug(f"Валидация LTC адреса: {address}")

    # Legacy addresses (L...)
    if address.startswith('L') and len(address) == 34:
        result = bool(re.match(r'^[L][a-zA-Z0-9]{33}$', address))
        logger.debug(f"Legacy адрес LTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    # P2SH addresses (M...)
    if address.startswith('M') and len(address) == 34:
        result = bool(re.match(r'^[M][a-zA-Z0-9]{33}$', address))
        logger.debug(f"P2SH адрес LTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    # Bech32 addresses (ltc1...)
    if address.startswith('ltc1') and 42 <= len(address) <= 62:
        result = bool(re.match(r'^ltc1[a-zA-Z0-9]{39,59}$', address))
        logger.debug(f"Bech32 адрес LTC: {address} -> {'корректен' if result else 'некорректен'}")
        return result

    logger.debug(f"Адрес LTC не соответствует ни одному известному формату: {address}")
    return False


def validate_crypto_address(address: str, crypto_type: str) -> bool:
    """
    Универсальная функция валидации адреса в зависимости от типа криптовалюты.
    :param address: строка с адресом
    :param crypto_type: 'BTC' или 'LTC'
    :return: True если адрес корректен для указанного типа
    """
    logger.debug(f"Запрос валидации адреса {address} для типа {crypto_type}")
    if crypto_type == "BTC":
        result = validate_btc_address(address)
    elif crypto_type == "LTC":
        result = validate_ltc_address(address)
    else:
        logger.warning(f"Попытка валидации для неизвестного типа криптовалюты: {crypto_type}")
        result = False

    if result:
        logger.debug(f"Адрес {address} корректен для {crypto_type}")
    else:
        logger.debug(f"Адрес {address} НЕ корректен для {crypto_type}")
    return result