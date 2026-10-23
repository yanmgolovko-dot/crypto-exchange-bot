# bot/services/db/order_repository.py
"""Репозиторий для работы с заявками."""

import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from .base import BaseRepository, db_retry
from bot.utils.tx_validator import validate_tx_hash
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
    coupon_id: Optional[int] = None
    public_order_number: Optional[int] = None


# Статусы, в которых разрешён ввод/обновление tx-хеша
_TX_HASH_ALLOWED_STATUSES = {"processing"}


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
                           promo_code: str = None, discount_percent: float = 0,
                           coupon_id: Optional[int] = None) -> int:
        """
        Создаёт новую заявку со статусом 'pending' и присваивает публичный номер из счётчика.
        """
        logger.debug(f"Создание заявки для user_id={user_id}, crypto={crypto_type}, сумма={amount_rub}")
        async with self.lock:
            # Получаем следующий публичный номер
            cursor = await self.conn.execute(
                "SELECT value FROM system_settings WHERE key = 'next_order_number'"
            )
            row = await cursor.fetchone()
            if row:
                public_number = int(row[0])
                logger.info(f"Текущий счётчик next_order_number = {public_number}")
                # Увеличиваем счётчик
                await self.conn.execute(
                    "UPDATE system_settings SET value = ? WHERE key = 'next_order_number'",
                    (str(public_number + 1),)
                )
                logger.info(f"Счётчик увеличен до {public_number + 1}")
            else:
                # Если счётчика нет, начинаем с 1 и создаём запись
                public_number = 1
                await self.conn.execute(
                    "INSERT INTO system_settings (key, value) VALUES ('next_order_number', ?)",
                    (str(public_number + 1),)
                )
                logger.info(f"Счётчик отсутствовал, создан со значением {public_number + 1}")

            # Вставляем заявку с полученным номером
            cursor = await self.conn.execute("""
                INSERT INTO exchange_orders 
                (user_id, username, crypto_type, amount_rub, amount_crypto, rate, 
                 fee_percent, crypto_address, status, promo_code, discount_percent, 
                 reminder_count, coupon_id, public_order_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, 0, ?, ?)
                RETURNING id
            """, (user_id, username, crypto_type, amount_rub, amount_crypto, 
                  rate, fee_percent, crypto_address, promo_code, discount_percent, coupon_id, public_number))
            row = await cursor.fetchone()
            order_id = row[0]
            await self.conn.commit()
            logger.info(f"Заявка #{order_id} создана в БД, публичный номер: {public_number}")
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
    async def get_order_by_public_number(self, number: int) -> Optional[Order]:
        """Находит заявку по публичному номеру."""
        logger.debug(f"Запрос заявки по публичному номеру #{number}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM exchange_orders WHERE public_order_number = ?", (number,)
            )
            row = await cursor.fetchone()
            if row:
                return Order(**dict(row))
            return None

    @db_retry()
    async def update_order_status(self, order_id: int, status: str,
                                   admin_comment: str = None,
                                   admin_id: int = None,
                                   expected_status: Optional[str] = None) -> bool:
        """
        Обновляет статус заявки.

        :param expected_status: если задан — апдейт выполняется только при условии,
            что текущий статус заявки равен expected_status (атомарно, без гонок).
            При несовпадении возвращает False и ничего не меняет.
        :return: True, если строка обновлена (или expected_status не задан).
        """
        logger.info(
            "Обновление статуса заявки #%s на '%s' (expected=%s)",
            order_id, status, expected_status,
        )
        async with self.lock:
            where = "id = ?"
            params_tail: tuple = (order_id,)
            if expected_status is not None:
                where += " AND status = ?"
                params_tail = (order_id, expected_status)

            if status == 'paid':
                cursor = await self.conn.execute(f"""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, paid_at = CURRENT_TIMESTAMP
                    WHERE {where}
                """, (status, admin_comment) + params_tail)
            elif status == 'completed':
                cursor = await self.conn.execute(f"""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?, completed_at = CURRENT_TIMESTAMP,
                        admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                    WHERE {where}
                """, (status, admin_comment, admin_id) + params_tail)
            else:
                cursor = await self.conn.execute(f"""
                    UPDATE exchange_orders 
                    SET status = ?, admin_comment = ?
                    WHERE {where}
                """, (status, admin_comment) + params_tail)

            await self.conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Статус заявки #{order_id} изменён")
            else:
                logger.warning(
                    "Статус заявки #%s НЕ изменён: ожидался '%s', фактический статус другой",
                    order_id, expected_status,
                )
            return updated

    @db_retry()
    async def update_order_tx_hash_checked(
        self, order_id: int, tx_hash: str, admin_id: int
    ) -> Tuple[bool, str]:
        """
        Валидирует и сохраняет хеш транзакции.

        Проверки:
        - заявка существует;
        - статус заявки в _TX_HASH_ALLOWED_STATUSES (processing);
        - формат хеша соответствует валюте заявки.

        :return: (ok, message). При ok=True message == "".
        """
        order = await self.get_order(order_id)
        if order is None:
            return False, f"Заявка #{order_id} не найдена."

        if order.status not in _TX_HASH_ALLOWED_STATUSES:
            return (
                False,
                f"Заявка #{order_id} в статусе '{order.status}'. "
                f"Хеш можно ввести только в статусе: "
                f"{', '.join(sorted(_TX_HASH_ALLOWED_STATUSES))}.",
            )

        ok, err = validate_tx_hash(order.crypto_type, tx_hash)
        if not ok:
            return False, err

        tx_hash = tx_hash.strip()
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_orders 
                SET tx_hash = ?, admin_checked_by = ?, admin_checked_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = ?
            """, (tx_hash, admin_id, order_id, order.status))
            await self.conn.commit()
            logger.info(
                "Хеш сохранён для заявки #%s (валюта=%s, admin=%s)",
                order_id, order.crypto_type, admin_id,
            )
            return True, ""

    @db_retry()
    async def update_order_tx_hash(self, order_id: int, tx_hash: str, admin_id: int) -> bool:
        """
        Совместимая обёртка над update_order_tx_hash_checked.
        Возвращает только bool — для старых вызовов.
        Новый код должен использовать update_order_tx_hash_checked.
        """
        ok, err = await self.update_order_tx_hash_checked(order_id, tx_hash, admin_id)
        if not ok:
            logger.warning(
                "update_order_tx_hash отклонён для #%s: %s", order_id, err
            )
        return ok

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