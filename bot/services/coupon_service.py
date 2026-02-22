# bot/services/coupon_service.py
"""Сервис для управления выдачей купонов (приветственных, за активность)."""

import logging
import json
from typing import Optional, Dict, Any

from bot.services.db import db
from bot.services.db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class CouponService:
    """Отвечает за выдачу купонов при определённых событиях."""

    async def give_welcome_coupon(self, user_id: int) -> bool:
        """
        Выдаёт приветственный купон, если он включён в настройках.
        Проверяет, не был ли уже выдан.
        """
        logger.info(f"Попытка выдачи приветственного купона пользователю {user_id}")
        config = await db.settings.get_json_setting('welcome_coupon_config')
        if not config.get('enabled'):
            logger.debug("Приветственные купоны отключены")
            return False

        # Проверяем, не выдавался ли уже купон этого типа
        async with db.uow() as uow:
            cursor = await uow._connection.conn.execute(
                "SELECT id FROM coupons WHERE owner_id = ? AND coupon_type = 'welcome'",
                (user_id,)
            )
            existing = await cursor.fetchone()
            if existing:
                logger.info(f"Приветственный купон уже выдавался пользователю {user_id}")
                return False

            # Создаём купон
            coupon_id = await uow.coupons.create_coupon(
                code=f"WELCOME{user_id}",
                discount_type=config['discount_type'],
                discount_value=config['discount_value'],
                discount_on=config['discount_on'],
                valid_days=config['valid_days'],
                description=config.get('description', 'Приветственный купон'),
                owner_id=user_id,
                coupon_type='welcome'
            )
            await uow.commit()
            logger.info(f"Приветственный купон #{coupon_id} выдан пользователю {user_id}")
            return True

    async def check_and_give_activity_coupons(self, user_id: int) -> bool:
        """
        Проверяет количество завершённых заявок пользователя и выдаёт купоны
        за активность, если они включены и пороги достигнуты.
        """
        logger.info(f"Проверка купонов за активность для пользователя {user_id}")
        config = await db.settings.get_json_setting('activity_coupon_config')
        if not config.get('enabled'):
            logger.debug("Купоны за активность отключены")
            return False

        # Получаем количество завершённых заявок пользователя
        stats = await db.get_user_stats(user_id)
        completed_orders = stats.get('total_orders', 0)

        thresholds = config.get('thresholds', [])
        given_any = False

        async with db.uow() as uow:
            for threshold in thresholds:
                required_orders = threshold['orders']
                if completed_orders < required_orders:
                    continue

                award_type = f"coupon_{required_orders}_orders"
                existing = await uow.activity_awards.get_award(user_id, award_type)
                if existing:
                    continue

                try:
                    coupon_id = await uow.coupons.create_coupon(
                        code=f"ACT{required_orders}_{user_id}_{threshold['discount_type']}{threshold['discount_value']}",
                        discount_type=threshold['discount_type'],
                        discount_value=threshold['discount_value'],
                        discount_on=threshold['discount_on'],
                        valid_days=threshold['valid_days'],
                        description=f"За {required_orders} заявок",
                        owner_id=user_id,
                        coupon_type='activity'
                    )
                    await uow.activity_awards.add_award(
                        user_id=user_id,
                        award_type=award_type,
                        threshold=required_orders,
                        coupon_id=coupon_id
                    )
                    given_any = True
                    logger.info(f"Выдан купон за активность #{coupon_id} пользователю {user_id} (порог {required_orders})")
                except Exception as e:
                    logger.error(f"Ошибка при выдаче купона за активность: {e}")

            await uow.commit()
            return given_any

    async def get_user_coupons(self, user_id: int) -> list:
        """
        Возвращает список купонов, доступных пользователю:
        - личные купоны (owner_id = user_id)
        - общие купоны (owner_id IS NULL)
        с учётом активности, срока действия и лимитов использований.
        """
        logger.info(f"Запрос доступных купонов для пользователя {user_id}")
        return await db.coupons.get_user_coupons(user_id)


# Глобальный экземпляр
coupon_service = CouponService()