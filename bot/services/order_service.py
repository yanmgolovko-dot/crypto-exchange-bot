"""Сервис для работы с заявками на обмен"""

import math
import logging
from typing import Optional, Dict, Any

from bot.services.db import Database
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, db: Database, crypto_api):
        self.db = db
        self.crypto_api = crypto_api

    async def calculate_order(
        self,
        crypto_type: str,
        input_type: str,
        amount: float,
        discount_percent: float = 0,
        rate: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Рассчитывает параметры заявки:
        - net_amount (сумма получения в рублях)
        - gross_amount (сумма к оплате)
        - amount_crypto (количество крипты)
        - fee_amount (комиссия)
        - effective_fee (итоговая комиссия с учётом скидки)
        """
        base_fee = await self.db.get_exchange_fee()
        effective_fee = base_fee * (1 - discount_percent / 100)

        if not rate:
            if crypto_type == "BTC":
                rate = await self.crypto_api.get_btc_price_rub()
            else:
                rate = await self.crypto_api.get_ltc_price_rub()

        if not rate:
            logger.error("Не удалось получить курс")
            return None

        if input_type == 'rub':
            net_amount = amount
            gross_raw = net_amount * (1 + effective_fee / 100)
            gross_rounded = math.ceil(gross_raw / 100) * 100
            amount_crypto = net_amount / rate
            fee_amount = gross_rounded - net_amount
            return {
                'net_amount': net_amount,
                'gross_amount': gross_rounded,
                'amount_crypto': round(amount_crypto, 8),
                'crypto_type': crypto_type,
                'rate': round(rate, 2),
                'fee_percent': effective_fee,
                'fee_amount': round(fee_amount, 2),
                'discount_percent': discount_percent,
                'input_type': 'rub'
            }
        else:  # input_type == 'crypto'
            desired_crypto = amount
            net_equivalent = desired_crypto * rate
            gross_raw = desired_crypto * rate * (1 + effective_fee / 100)
            gross_rounded = math.ceil(gross_raw / 100) * 100
            fee_amount = gross_rounded - net_equivalent
            return {
                'net_amount': round(net_equivalent, 2),
                'gross_amount': gross_rounded,
                'amount_crypto': round(desired_crypto, 8),
                'crypto_type': crypto_type,
                'rate': round(rate, 2),
                'fee_percent': effective_fee,
                'fee_amount': round(fee_amount, 2),
                'discount_percent': discount_percent,
                'input_type': 'crypto'
            }

    async def create_order(
        self,
        user_id: int,
        username: Optional[str],
        crypto_type: str,
        amount_rub: float,
        amount_crypto: float,
        rate: float,
        fee_percent: float,
        crypto_address: str,
        promo_code: Optional[str] = None,
        discount_percent: float = 0
    ) -> int:
        """Создаёт заявку в БД и применяет промокод в одной транзакции."""
        async with self.db.uow() as uow:
            # Создаём заказ
            order_id = await uow.orders.create_order(
                user_id=user_id,
                username=username,
                crypto_type=crypto_type,
                amount_rub=amount_rub,
                amount_crypto=amount_crypto,
                rate=rate,
                fee_percent=fee_percent,
                crypto_address=crypto_address,
                promo_code=promo_code,
                discount_percent=discount_percent
            )
            # Если есть промокод, применяем его
            if promo_code:
                promo = await uow.promo.get_promo_code(promo_code)
                if promo:
                    await uow.promo.use_promo_code(promo.id, user_id, order_id)
            # Здесь можно добавить начисление реферальных бонусов (тоже в транзакции)
            await uow.commit()
        return order_id