# bot/services/expire_service.py
"""
Сервис автоотмены просроченных заявок.

Ищет заявки в статусе 'pending', созданные более N часов назад,
и переводит их в 'cancelled' с комментарием «истёк срок оплаты».
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from aiogram import Bot

from bot.services.db import Database

logger = logging.getLogger(__name__)

# Значение по умолчанию, если настройка order_ttl_hours не задана
DEFAULT_ORDER_TTL_HOURS = 24

# Комментарий, который пишется в admin_comment при автоотмене
EXPIRED_STATUS_COMMENT = "Автоматическая отмена: истёк срок оплаты"


class ExpireService:
    """Автоотмена просроченных заявок."""

    def __init__(self, db: Database):
        self.db = db

    async def get_ttl_hours(self) -> int:
        """Читает настройку order_ttl_hours из БД. При ошибке — default."""
        try:
            raw = await self.db.get_setting(
                "order_ttl_hours", str(DEFAULT_ORDER_TTL_HOURS)
            )
            ttl = int(raw)
            if ttl <= 0:
                logger.warning(
                    "order_ttl_hours=%s некорректно, использую %s",
                    ttl, DEFAULT_ORDER_TTL_HOURS,
                )
                return DEFAULT_ORDER_TTL_HOURS
            return ttl
        except Exception as e:
            logger.warning(
                "Не удалось прочитать order_ttl_hours: %s. Использую %s",
                e, DEFAULT_ORDER_TTL_HOURS,
            )
            return DEFAULT_ORDER_TTL_HOURS

    async def find_stale_order_ids(self, ttl_hours: int) -> List[int]:
        """Возвращает id pending-заявок старше ttl_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        async with self.db.uow() as uow:
            cursor = await uow._connection.conn.execute(
                """
                SELECT id FROM exchange_orders
                WHERE status = 'pending' AND created_at < ?
                """,
                (cutoff_str,),
            )
            rows = await cursor.fetchall()
        return [int(r[0]) for r in rows]

    async def expire_order(self, order_id: int) -> bool:
        """
        Атомарно переводит pending → cancelled.
        Если статус уже сменился (пользователь оплатил, админ подтвердил),
        возвращает False и ничего не трогает.
        """
        ok = await self.db.orders.update_order_status(
            order_id,
            "cancelled",
            EXPIRED_STATUS_COMMENT,
            expected_status="pending",
        )
        return ok

    async def expire_and_notify(self, bot: Bot) -> int:
        """
        Один проход: находит просроченные заявки, отменяет их и уведомляет пользователей.
        :return: количество успешно отменённых заявок.
        """
        ttl_hours = await self.get_ttl_hours()
        stale_ids = await self.find_stale_order_ids(ttl_hours)
        if not stale_ids:
            return 0

        logger.info(
            "Автоотмена: найдено %s pending-заявок старше %s ч",
            len(stale_ids), ttl_hours,
        )
        cancelled = 0
        for order_id in stale_ids:
            order = await self.db.get_order(order_id)
            if not order:
                continue

            ok = await self.expire_order(order_id)
            if not ok:
                logger.info(
                    "Автоотмена: заявка #%s уже не в pending, пропускаю", order_id
                )
                continue

            cancelled += 1
            display_number = order.public_order_number or order.id
            try:
                await bot.send_message(
                    order.user_id,
                    f"⏱ <b>Заявка #{display_number} отменена</b>\n\n"
                    f"Срок оплаты истёк ({ttl_hours} ч).\n"
                    f"Если вы всё ещё хотите совершить обмен — создайте новую заявку.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(
                    "Автоотмена: не удалось уведомить пользователя %s: %s",
                    order.user_id, e,
                )

        logger.info("Автоотмена: отменено %s из %s", cancelled, len(stale_ids))
        return cancelled