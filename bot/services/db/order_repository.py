# bot/services/db/order_repository.py
"""Репозиторий для работы с заявками."""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .base import BaseRepository, db_retry
import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Order:
    id: int
    user_id: int
    username: Optional[str]
    crypto_type: str
    amount_rub: float
    amount_crypto: float
    rate: float
    fee_percent: float
    status: str
    bank_receipt: Optional[str]
    crypto_address: str
    created_at: str
    paid_at: Optional[str]
    completed_at: Optional[str]
    admin_comment: Optional[str]
    promo_code: Optional[str]
    discount_percent: float
    admin_checked_by: Optional[int]
    admin_checked_at: Optional[str]
    manual_payment_details: Optional[str] = None
    tx_hash: Optional[str] = None
    reminder_count: int = 0
    last_reminder_at: Optional[str] = None


class OrderRepository(BaseRepository):
    """
    Репозиторий для работы с таблицей exchange_orders.
    Содержит методы для создания, получения, обновления заявок,
    а также для работы с напоминаниями.
    """

    @db_retry()
    async def create_order(self, user_id: int, username: str, crypto_type: str,
                           amount_rub: float, amount_crypto: float, rate: float,
                           fee_percent: float, crypto_address: str,
                           promo_code: str = None, discount_percent: float = 0) -> int:
        """
        Создаёт новую заявку со статусом 'pending'.
        :return: ID созданной заявки
        """
        logger.debug(f"Создание заявки для user_id={user_id}, crypto={crypto_type}, сумма={amount_rub}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO exchange_orders 
                (user_id, username, crypto_type, amount_rub, amount_crypto, rate, 
                 fee_percent, crypto_address, status, promo_code, discount_percent, reminder_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0)
            """, (user_id, username, crypto_type, amount_rub, amount_crypto, 
                  rate, fee_percent, crypto_address, promo_code, discount_percent))
            await self.conn.commit()
            order_id = cursor.lastrowid
            logger.info(f"Заявка #{order_id} создана в БД")
            return order_id

    @db_retry()
    async def get_order(self, order_id: int) -> Optional[Order]:
        """Получает заявку по ID."""
        logger.debug(f"Запрос заявки #{order_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM exchange_orders WHERE id = ?", (order_id,)
            )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Заявка #{order_id} найдена")
                return Order(**dict(row))
            logger.debug(f"Заявка #{order_id} не найдена")
            return None

    @db_retry()
    async def update_order_status(self, order_id: int, status: str, 
                                   admin_comment: str = None,
                                   admin_id: int = None) -> bool:
        """
        Обновляет статус заявки.
        Для статусов 'paid' и 'completed' автоматически заполняет соответствующие временные метки.
        """
        logger.info(f"Обновление статуса заявки #{order_id} на '{status}'")
        async with self.lock:
            if status == 'paid':
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, paid_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, admin_comment, order_id))
                logger.debug(f"Установлено paid_at для заявки #{order_id}")
            elif status == 'completed':
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, completed_at = CURRENT_TIMESTAMP,
                        admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, admin_comment, admin_id, order_id))
                logger.debug(f"Установлено completed_at и admin_checked для заявки #{order_id}")
            else:
                await self.conn.execute("""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?
                    WHERE id = ?
                """, (status, admin_comment, order_id))
            await self.conn.commit()
            logger.info(f"Статус заявки #{order_id} изменён")
            return True

    @db_retry()
    async def update_order_tx_hash(self, order_id: int, tx_hash: str, admin_id: int) -> bool:
        """Сохраняет хеш транзакции и отмечает администратора."""
        logger.info(f"Сохранение хеша транзакции для заявки #{order_id}: {tx_hash}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders 
                SET tx_hash = ?, admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (tx_hash, admin_id, order_id))
            await self.conn.commit()
            logger.debug(f"Хеш сохранён, admin_checked_by={admin_id}")
            return True

    @db_retry()
    async def add_bank_receipt(self, order_id: int, receipt_path: str) -> bool:
        """Сохраняет путь к PDF-чеку в заявке."""
        logger.info(f"Добавление чека для заявки #{order_id}: {receipt_path}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE exchange_orders SET bank_receipt = ? WHERE id = ?",
                (receipt_path, order_id)
            )
            await self.conn.commit()
            logger.debug(f"Путь к чеку сохранён")
            return True

    @db_retry()
    async def get_user_orders(self, user_id: int, limit: int = 10) -> List[Order]:
        """Возвращает последние заявки пользователя."""
        logger.debug(f"Запрос последних {limit} заявок пользователя {user_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            rows = await cursor.fetchall()
            orders = [Order(**dict(row)) for row in rows]
            logger.debug(f"Найдено {len(orders)} заявок")
            return orders

    @db_retry()
    async def get_pending_orders(self) -> List[Order]:
        """Возвращает все заявки со статусом 'pending' или 'paid' (ожидающие/на проверке)."""
        logger.debug("Запрос всех ожидающих и оплаченных заявок")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                WHERE status IN ('pending', 'paid') 
                ORDER BY created_at DESC
            """)
            rows = await cursor.fetchall()
            orders = [Order(**dict(row)) for row in rows]
            logger.debug(f"Найдено {len(orders)} заявок со статусом pending/paid")
            return orders

    @db_retry()
    async def get_all_orders(self, limit: int = 50, offset: int = 0) -> List[Order]:
        """Возвращает последние заявки с пагинацией."""
        logger.debug(f"Запрос всех заявок (limit={limit}, offset={offset})")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = await cursor.fetchall()
            orders = [Order(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(orders)} заявок")
            return orders

    @db_retry()
    async def set_order_manual_payment_details(self, order_id: int, details: str) -> bool:
        """Сохраняет введённые администратором реквизиты для ручного режима."""
        logger.info(f"Сохранение ручных реквизитов для заявки #{order_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders 
                SET manual_payment_details = ? 
                WHERE id = ?
            """, (details, order_id))
            await self.conn.commit()
            logger.debug(f"Реквизиты сохранены")
            return True

    # ==================== МЕТОДЫ ДЛЯ НАПОМИНАНИЙ ====================

    @db_retry()
    async def get_pending_orders_for_reminder(self, minutes: int = 5, max_reminders: int = 3) -> List[Order]:
        """
        Возвращает заявки со статусом 'pending', созданные более minutes минут назад,
        у которых количество напоминаний меньше max_reminders.
        """
        logger.debug(f"Запрос заявок для напоминаний (минут={minutes}, макс_напоминаний={max_reminders})")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM exchange_orders
                WHERE status = 'pending'
                AND (julianday('now') - julianday(created_at)) * 24 * 60 >= ?
                AND reminder_count < ?
            """, (minutes, max_reminders))
            rows = await cursor.fetchall()
            orders = [Order(**dict(row)) for row in rows]
            logger.debug(f"Найдено {len(orders)} заявок для напоминаний")
            return orders

    @db_retry()
    async def increment_reminder_count(self, order_id: int) -> bool:
        """
        Увеличивает счётчик напоминаний и обновляет время последнего напоминания.
        """
        logger.debug(f"Увеличение счётчика напоминаний для заявки #{order_id}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders
                SET reminder_count = reminder_count + 1,
                    last_reminder_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (order_id,))
            await self.conn.commit()
            logger.debug(f"Счётчик напоминаний увеличен")
            return True