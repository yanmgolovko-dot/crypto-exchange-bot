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
    Итоговая сумма к оплате округляется до 100 ₽ вверх.
    """

    # Минимальная комиссия в долларах для каждого типа
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
        rate: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Рассчитывает параметры заявки.
        :param crypto_type: 'BTC' или 'LTC'
        :param input_type: 'rub' или 'crypto'
        :param amount: сумма (в рублях или количество крипты)
        :param discount_percent: скидка по промокоду (0-100)
        :param rate: курс криптовалюты к рублю (если известен)
        :return: словарь с результатами или None при ошибке
        """
        logger.info(f"Расчёт заявки: {crypto_type}, {input_type}, amount={amount}, discount={discount_percent}%")

        # Получаем курс криптовалюты к рублю, если не передан
        if not rate:
            if crypto_type == "BTC":
                rate = await self.crypto_api.get_btc_price_rub()
            else:
                rate = await self.crypto_api.get_ltc_price_rub()
        if not rate:
            logger.error("Не удалось получить курс криптовалюты")
            return None

        # Получаем курс USD/RUB
        usd_rub = await self.crypto_api.get_usdt_rub()
        if not usd_rub:
            logger.error("Не удалось получить курс USD/RUB")
            return None
        logger.debug(f"Курс USD/RUB: {usd_rub}")

        # Получаем процент комиссии из настроек
        fee_percent_config = await self.db.get_exchange_fee()
        logger.debug(f"Базовая комиссия (процент): {fee_percent_config}%")

        # Минимальная комиссия в USD для данного типа
        min_fee_usd = self.MIN_FEE_USD.get(crypto_type, 0)
        if min_fee_usd == 0:
            logger.error(f"Неизвестный тип криптовалюты: {crypto_type}")
            return None

        # Определяем сумму, которую получит пользователь, в рублях (net_amount)
        if input_type == 'rub':
            net_amount = amount
        elif input_type == 'crypto':
            desired_crypto = amount
            net_amount = desired_crypto * rate
        else:
            logger.error(f"Неизвестный input_type: {input_type}")
            return None

        # Комиссия по проценту в рублях
        fee_rub_percent = net_amount * fee_percent_config / 100
        # Переводим процентную комиссию в USD
        fee_usd_percent = fee_rub_percent / usd_rub
        # Итоговая комиссия в USD = максимум между минимальной и процентной
        fee_usd = max(min_fee_usd, fee_usd_percent)
        # Применяем скидку по промокоду
        fee_usd_discounted = fee_usd * (1 - discount_percent / 100)
        # Целевая комиссия в рублях
        target_fee_rub = fee_usd_discounted * usd_rub

        logger.debug(f"Комиссия по проценту: {fee_usd_percent:.2f} USD, "
                     f"финальная: {fee_usd_discounted:.2f} USD, в рублях: {target_fee_rub:.2f}")

        # Рассчитываем итоговые суммы
        gross_raw = net_amount + target_fee_rub
        gross_rounded = math.ceil(gross_raw / 100) * 100
        amount_crypto = net_amount / rate
        fee_amount = gross_rounded - net_amount

        # Эффективный процент (для записи в БД)
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
            'fee_usd': round(fee_usd_discounted, 2),
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
        discount_percent: float = 0
    ) -> int:
        """
        Создаёт заявку в БД.
        :param user_id: ID пользователя
        :param username: username (может быть None)
        :param crypto_type: 'BTC' или 'LTC'
        :param amount_rub: сумма к оплате (gross_amount)
        :param amount_crypto: количество крипты
        :param rate: курс на момент создания
        :param fee_percent: эффективный процент комиссии (рассчитанный в calculate_order)
        :param crypto_address: адрес кошелька пользователя
        :param promo_code: применённый промокод (если есть)
        :param discount_percent: скидка по промокоду
        :return: ID созданной заявки
        """
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
                discount_percent=discount_percent
            )
            logger.info(f"Заявка #{order_id} создана в БД")

            if promo_code:
                promo = await uow.promo.get_promo_code(promo_code)
                if promo:
                    await uow.promo.use_promo_code(promo.id, user_id, order_id)
                    logger.info(f"Промокод {promo_code} применён к заявке #{order_id}")

            await uow.commit()
        return order_id