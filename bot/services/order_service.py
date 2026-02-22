# bot/services/order_service.py
"""Сервис для работы с заявками на обмен"""

import math
import logging
from typing import Optional, Dict, Any

from bot.services.db import Database
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)


class OrderService:
    """
    Сервис для расчёта и создания заявок.
    Комиссия рассчитывается как максимум между:
    - фиксированной минимальной комиссией (9 USD для BTC, 4.5 USD для LTC)
    - процентом от суммы обмена (процент задаётся в настройках EXCHANGE_FEE)
    Применяется скидка по промокоду (уменьшает итоговую комиссию).
    Может применяться купон (скидка на комиссию или на всю сумму заказа).
    Итоговая сумма к оплате округляется до 100 ₽ вверх.
    """

    MIN_FEE_USD = {
        'BTC': 9.0,
        'LTC': 4.5
    }

    def __init__(self, db: Database, crypto_api):
        self.db = db
        self.crypto_api = crypto_api

    async def calculate_order(
        self,
        crypto_type: str,
        input_type: str,
        amount: float,
        discount_percent: float = 0,
        rate: Optional[float] = None,
        coupon_data: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        logger.info(f"Расчёт заявки: {crypto_type}, {input_type}, amount={amount}, discount={discount_percent}%, coupon={coupon_data}")

        if not rate:
            if crypto_type == "BTC":
                rate = await self.crypto_api.get_btc_price_rub()
            else:
                rate = await self.crypto_api.get_ltc_price_rub()
        if not rate:
            logger.error("Не удалось получить курс криптовалюты")
            return None

        usd_rub = await self.crypto_api.get_usdt_rub()
        if not usd_rub:
            logger.error("Не удалось получить курс USD/RUB")
            return None
        logger.debug(f"Курс USD/RUB: {usd_rub}")

        fee_percent_config = await self.db.get_exchange_fee()
        logger.debug(f"Базовая комиссия (процент): {fee_percent_config}%")

        min_fee_usd = self.MIN_FEE_USD.get(crypto_type, 0)
        if min_fee_usd == 0:
            logger.error(f"Неизвестный тип криптовалюты: {crypto_type}")
            return None

        if input_type == 'rub':
            net_amount_initial = amount
        elif input_type == 'crypto':
            desired_crypto = amount
            net_amount_initial = desired_crypto * rate
        else:
            logger.error(f"Неизвестный input_type: {input_type}")
            return None

        net_amount = net_amount_initial
        if coupon_data and coupon_data.get('discount_on') == 'order':
            if coupon_data['discount_type'] == 'percent':
                net_amount = net_amount_initial * (1 - coupon_data['discount_value'] / 100)
            else:
                net_amount = max(0, net_amount_initial - coupon_data['discount_value'])
            logger.debug(f"После купона на заказ: net_amount = {net_amount:.2f}")

        fee_rub_percent = net_amount * fee_percent_config / 100
        fee_usd_percent = fee_rub_percent / usd_rub
        fee_usd = max(min_fee_usd, fee_usd_percent)
        fee_usd_discounted = fee_usd * (1 - discount_percent / 100)

        target_fee_usd = fee_usd_discounted
        if coupon_data and coupon_data.get('discount_on') == 'commission':
            if coupon_data['discount_type'] == 'percent':
                target_fee_usd = fee_usd_discounted * (1 - coupon_data['discount_value'] / 100)
            else:
                target_fee_rub_initial = fee_usd_discounted * usd_rub
                target_fee_rub = max(0, target_fee_rub_initial - coupon_data['discount_value'])
                target_fee_usd = target_fee_rub / usd_rub
            logger.debug(f"После купона на комиссию: target_fee_usd = {target_fee_usd:.2f}")

        target_fee_rub = target_fee_usd * usd_rub
        logger.debug(f"Комиссия по проценту: {fee_usd_percent:.2f} USD, финальная: {target_fee_usd:.2f} USD, в рублях: {target_fee_rub:.2f}")

        gross_raw = net_amount + target_fee_rub
        gross_rounded = math.ceil(gross_raw / 100) * 100
        amount_crypto = net_amount / rate
        fee_amount = gross_rounded - net_amount

        if net_amount > 0:
            effective_fee_percent = (fee_amount / net_amount) * 100
        else:
            effective_fee_percent = 0

        result = {
            'net_amount': net_amount,
            'gross_amount': gross_rounded,
            'amount_crypto': round(amount_crypto, 8),
            'crypto_type': crypto_type,
            'rate': round(rate, 2),
            'fee_percent': round(effective_fee_percent, 2),
            'fee_amount': round(fee_amount, 2),
            'discount_percent': discount_percent,
            'input_type': input_type,
            'fee_usd': round(target_fee_usd, 2),
            'usd_rub': round(usd_rub, 2)
        }
        logger.info(f"Результат расчёта: {result}")
        return result

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
        discount_percent: float = 0,
        coupon_id: Optional[int] = None
    ) -> int:
        logger.info(f"Создание заявки для пользователя {user_id}, {crypto_type}, сумма {amount_rub} ₽")
        async with self.db.uow() as uow:
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
                discount_percent=discount_percent,
                coupon_id=coupon_id
            )
            logger.info(f"Заявка #{order_id} создана в БД")
            if promo_code:
                promo = await uow.promo.get_promo_code(promo_code)
                if promo:
                    await uow.promo.use_promo_code(promo.id, user_id, order_id)
                    logger.info(f"Промокод {promo_code} применён к заявке #{order_id}")
            await uow.commit()
        return order_id