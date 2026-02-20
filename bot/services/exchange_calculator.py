"""Калькулятор обмена криптовалют"""

import math
from typing import Optional, Dict
from bot.services.crypto_api import crypto_api as default_crypto_api
from bot.config.settings import config


class ExchangeCalculator:
    """Калькулятор обмена криптовалют"""

    def __init__(self, crypto_api=None):
        """
        :param crypto_api: объект для получения курсов (по умолчанию используется глобальный crypto_api)
        """
        self.crypto_api = crypto_api or default_crypto_api

    async def calculate_from_net(self, net_amount: float, crypto_type: str, fee_percent: float = None) -> Optional[Dict]:
        """
        Расчёт на основе желаемой суммы получения (net).
        Возвращает gross (округлённую до 100), amount_crypto и т.д.
        """
        if fee_percent is None:
            fee_percent = config.EXCHANGE_FEE

        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            return None

        if not rate:
            return None

        gross_raw = net_amount * (1 + fee_percent / 100)
        gross_rounded = math.ceil(gross_raw / 100) * 100
        amount_crypto = net_amount / rate
        fee_amount = gross_rounded - net_amount

        return {
            "net_amount": net_amount,
            "gross_amount": gross_rounded,
            "amount_crypto": round(amount_crypto, 8),
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }

    async def calculate_exchange(self, amount_rub: float, crypto_type: str) -> Optional[Dict]:
        """Обратная совместимость (если где-то используется)"""
        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            return None

        if not rate:
            return None

        fee_percent = config.EXCHANGE_FEE
        fee_multiplier = 1 + (fee_percent / 100)
        amount_crypto = amount_rub / (rate * fee_multiplier)
        fee_amount = amount_rub - (amount_rub / fee_multiplier)

        return {
            "amount_rub": amount_rub,
            "amount_crypto": round(amount_crypto, 8),
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }

    async def calculate_reverse(self, amount_crypto: float, crypto_type: str) -> Optional[Dict]:
        if crypto_type == "BTC":
            rate = await self.crypto_api.get_btc_price_rub()
        elif crypto_type == "LTC":
            rate = await self.crypto_api.get_ltc_price_rub()
        else:
            return None

        if not rate:
            return None

        fee_percent = config.EXCHANGE_FEE
        fee_multiplier = 1 + (fee_percent / 100)
        amount_rub = amount_crypto * rate * fee_multiplier
        fee_amount = amount_rub - (amount_rub / fee_multiplier)

        return {
            "amount_rub": round(amount_rub, 2),
            "amount_crypto": amount_crypto,
            "crypto_type": crypto_type,
            "rate": round(rate, 2),
            "fee_percent": fee_percent,
            "fee_amount": round(fee_amount, 2)
        }


# Глобальный экземпляр для обратной совместимости
exchange_calculator = ExchangeCalculator()