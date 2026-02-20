# bot/services/exchange_calculator.py
"""Калькулятор обмена криптовалют."""

import math
import logging
from typing import Optional, Dict
from bot.services.crypto_api import crypto_api as default_crypto_api
from bot.config.settings import config

logger = logging.getLogger(__name__)


class ExchangeCalculator:
    """
    Калькулятор для расчёта сумм обмена с учётом комиссии и округления.
    Использует актуальные курсы из CryptoAPI.
    """

    def __init__(self, crypto_api=None):
        """
        :param crypto_api: объект для получения курсов (по умолчанию используется глобальный crypto_api)
        """
        self.crypto_api = crypto_api or default_crypto_api
        logger.debug("ExchangeCalculator инициализирован")

    async def calculate_from_net(self, net_amount: float, crypto_type: str, fee_percent: float = None) -> Optional[Dict]:
        """
        Расчёт на основе желаемой суммы получения (net).
        Возвращает gross (округлённую до 100), amount_crypto и т.д.
        :param net_amount: сумма, которую пользователь хочет получить (в рублях)
        :param crypto_type: 'BTC' или 'LTC'
        :param fee_percent: комиссия в процентах (если None, берётся из настроек)
        """
        logger.info(f"Расчёт from_net: {crypto_type}, net={net_amount}, fee={fee_percent}")

        if fee_percent is None:
            fee_percent = config.EXCHANGE_FEE
            logger.debug(f"Комиссия из конфига: {fee_percent}%")

        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            logger.error(f"Неизвестный тип криптовалюты: {crypto_type}")
            return None

        if not rate:
            logger.error("Не удалось получить курс")
            return None

        gross_raw = net_amount * (1 + fee_percent / 100)
        gross_rounded = math.ceil(gross_raw / 100) * 100
        amount_crypto = net_amount / rate
        fee_amount = gross_rounded - net_amount

        result = {
            "net_amount": net_amount,
            "gross_amount": gross_rounded,
            "amount_crypto": round(amount_crypto, 8),
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }
        logger.info(f"Результат from_net: {result}")
        return result

    async def calculate_exchange(self, amount_rub: float, crypto_type: str) -> Optional[Dict]:
        """
        Обратная совместимость (старая версия расчёта).
        Рассчитывает, сколько крипты получит пользователь за amount_rub с учётом комиссии.
        """
        logger.info(f"Расчёт exchange (старая версия): {crypto_type}, сумма={amount_rub}")
        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            logger.error(f"Неизвестный тип криптовалюты: {crypto_type}")
            return None

        if not rate:
            logger.error("Не удалось получить курс")
            return None

        fee_percent = config.EXCHANGE_FEE
        fee_multiplier = 1 + (fee_percent / 100)
        amount_crypto = amount_rub / (rate * fee_multiplier)
        fee_amount = amount_rub - (amount_rub / fee_multiplier)

        result = {
            "amount_rub": amount_rub,
            "amount_crypto": round(amount_crypto, 8),
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }
        logger.info(f"Результат exchange: {result}")
        return result

    async def calculate_reverse(self, amount_crypto: float, crypto_type: str) -> Optional[Dict]:
        """
        Расчёт, сколько рублей нужно заплатить, чтобы получить указанное количество крипты.
        """
        logger.info(f"Расчёт reverse: {crypto_type}, amount_crypto={amount_crypto}")
        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            logger.error(f"Неизвестный тип криптовалюты: {crypto_type}")
            return None

        if not rate:
            logger.error("Не удалось получить курс")
            return None

        fee_percent = config.EXCHANGE_FEE
        fee_multiplier = 1 + (fee_percent / 100)
        amount_rub = amount_crypto * rate * fee_multiplier
        fee_amount = amount_rub - (amount_rub / fee_multiplier)

        result = {
            "amount_rub": round(amount_rub, 2),
            "amount_crypto": amount_crypto,
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }
        logger.info(f"Результат reverse: {result}")
        return result


# Глобальный экземпляр для обратной совместимости
exchange_calculator = ExchangeCalculator()