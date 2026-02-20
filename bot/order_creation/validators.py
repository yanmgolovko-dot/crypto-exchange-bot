# bot/order_creation/validators.py
"""
Набор функций для валидации данных, вводимых пользователем на разных шагах.
"""

from bot.services.validator import validate_crypto_address
from bot.config.settings import config


async def validate_amount_rub(amount: float, db) -> tuple[bool, str]:
    """
    Проверяет, что сумма в рублях находится в допустимых пределах.
    Возвращает (True, "") если всё ок, иначе (False, сообщение об ошибке).
    """
    min_net = float(await db.get_setting('min_amount', str(config.MIN_AMOUNT)))
    max_net = float(await db.get_setting('max_amount', str(config.MAX_AMOUNT)))
    if amount < min_net or amount > max_net:
        return False, f"Сумма должна быть от {min_net:,.0f} до {max_net:,.0f} ₽"
    return True, ""


async def validate_crypto_address_for_type(address: str, crypto_type: str) -> tuple[bool, str]:
    """
    Проверяет, что адрес соответствует выбранному типу криптовалюты.
    """
    if not validate_crypto_address(address, crypto_type):
        return False, f"Некорректный {crypto_type}-адрес"
    return True, ""


def validate_promo_code_format(code: str) -> bool:
    """Проверяет, что промокод не пустой и имеет допустимую длину."""
    return bool(code) and len(code) <= 50