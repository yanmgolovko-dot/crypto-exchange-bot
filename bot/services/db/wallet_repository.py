# bot/services/db/wallet_repository.py
"""Репозиторий для работы с крипто-кошельками и транзакциями."""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .base import BaseRepository, db_retry
import aiosqlite

from ...utils.encryption import encrypt_private_key, decrypt_private_key

logger = logging.getLogger(__name__)


@dataclass
class Wallet:
    id: int
    crypto_type: str
    address: str
    private_key: str
    balance: float
    pending_balance: float
    is_active: bool
    is_default: bool
    label: Optional[str]
    created_at: str
    last_balance_check: Optional[str]
    total_sent: float
    total_received: float


@dataclass
class CryptoTransaction:
    id: int
    order_id: int
    wallet_id: int
    crypto_type: str
    to_address: str
    amount: float
    fee: Optional[float]
    fee_paid: Optional[float]
    tx_hash: Optional[str]
    status: str
    confirmations: int
    error_message: Optional[str]
    created_at: str
    broadcasted_at: Optional[str]
    confirmed_at: Optional[str]


class WalletRepository(BaseRepository):
    """
    Репозиторий для работы с таблицами exchange_wallets и crypto_transactions.
    Содержит методы для добавления, получения, обновления кошельков,
    а также для создания и отслеживания крипто-транзакций.
    """

    @db_retry()
    async def add_wallet(self, crypto_type: str, address: str, private_key: str, label: str = None) -> int:
        """
        Добавляет новый кошелёк. Приватный ключ автоматически шифруется.
        Если это первый кошелёк данного типа, он становится is_default = True.
        """
        if not private_key:
            logger.error("Попытка добавить кошелёк с пустым приватным ключом")
            raise ValueError("Приватный ключ не может быть пустым")

        encrypted_key = encrypt_private_key(private_key)
        logger.info(f"Добавление кошелька: {crypto_type}, адрес {address}, метка {label}")

        async with self.lock:
            # Проверяем, есть ли уже кошельки этого типа
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_wallets WHERE crypto_type = ?",
                (crypto_type,)
            )
            count = (await cursor.fetchone())[0]
            is_default = count == 0
            logger.debug(f"Первый кошелёк типа {crypto_type}? {is_default}")

            cursor = await self.conn.execute("""
                INSERT INTO exchange_wallets 
                (crypto_type, address, private_key, label, is_default)
                VALUES (?, ?, ?, ?, ?)
            """, (crypto_type, address, encrypted_key, label, is_default))
            await self.conn.commit()
            wallet_id = cursor.lastrowid
            logger.info(f"Кошелёк добавлен, ID: {wallet_id}")
            return wallet_id

    @db_retry()
    async def get_wallet(self, wallet_id: int = None, crypto_type: str = None, include_inactive: bool = False) -> Optional[Wallet]:
        """
        Получает кошелёк по ID или по типу (возвращает активный по умолчанию).
        :param wallet_id: ID кошелька
        :param crypto_type: тип криптовалюты (BTC/LTC)
        :param include_inactive: если True, включать неактивные кошельки
        """
        logger.debug(f"Запрос кошелька: wallet_id={wallet_id}, crypto_type={crypto_type}, include_inactive={include_inactive}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            if wallet_id:
                query = "SELECT * FROM exchange_wallets WHERE id = ?"
                params = (wallet_id,)
                if not include_inactive:
                    query += " AND is_active = 1"
                cursor = await self.conn.execute(query, params)
            elif crypto_type:
                query = "SELECT * FROM exchange_wallets WHERE crypto_type = ? AND is_active = 1 AND is_default = 1"
                cursor = await self.conn.execute(query, (crypto_type,))
            else:
                logger.warning("Не указаны параметры для получения кошелька")
                return None

            row = await cursor.fetchone()
            if row:
                logger.debug(f"Кошелёк найден: ID {row['id']}")
                return Wallet(**dict(row))
            logger.debug("Кошелёк не найден")
            return None

    @db_retry()
    async def get_all_wallets(self, crypto_type: str = None, include_inactive: bool = False) -> List[Wallet]:
        """
        Возвращает все кошельки (опционально отфильтрованные по типу).
        :param crypto_type: 'BTC' или 'LTC'
        :param include_inactive: включать ли неактивные
        """
        logger.debug(f"Запрос всех кошельков: crypto_type={crypto_type}, include_inactive={include_inactive}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            if crypto_type:
                query = "SELECT * FROM exchange_wallets WHERE crypto_type = ?"
                params = (crypto_type,)
                if not include_inactive:
                    query += " AND is_active = 1"
                query += " ORDER BY is_default DESC"
                cursor = await self.conn.execute(query, params)
            else:
                query = "SELECT * FROM exchange_wallets"
                if not include_inactive:
                    query += " WHERE is_active = 1"
                query += " ORDER BY crypto_type, is_default DESC"
                cursor = await self.conn.execute(query)

            rows = await cursor.fetchall()
            wallets = [Wallet(**dict(row)) for row in rows]
            logger.debug(f"Получено {len(wallets)} кошельков")
            return wallets

    @db_retry()
    async def update_wallet_balance(self, wallet_id: int, balance: float, pending_balance: float) -> bool:
        """
        Обновляет баланс кошелька и время последней проверки.
        """
        logger.info(f"Обновление баланса кошелька #{wallet_id}: balance={balance}, pending={pending_balance}")
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_wallets 
                SET balance = ?, pending_balance = ?, last_balance_check = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (balance, pending_balance, wallet_id))
            await self.conn.commit()
            logger.debug(f"Баланс кошелька #{wallet_id} обновлён")
            return True

    @db_retry()
    async def deactivate_wallet(self, wallet_id: int) -> bool:
        """
        Мягкое удаление кошелька (установка is_active = 0).
        """
        logger.info(f"Деактивация кошелька #{wallet_id}")
        async with self.lock:
            await self.conn.execute(
                "UPDATE exchange_wallets SET is_active = 0 WHERE id = ?",
                (wallet_id,)
            )
            await self.conn.commit()
            logger.info(f"Кошелёк #{wallet_id} деактивирован")
            return True

    @db_retry()
    async def hard_delete_wallet(self, wallet_id: int) -> bool:
        """
        Полностью удаляет кошелёк из базы данных (безвозвратно).
        """
        logger.warning(f"Полное удаление кошелька #{wallet_id}")
        async with self.lock:
            await self.conn.execute("DELETE FROM exchange_wallets WHERE id = ?", (wallet_id,))
            await self.conn.commit()
            logger.info(f"Кошелёк #{wallet_id} полностью удалён")
            return True

    @db_retry()
    async def delete_wallet(self, wallet_id: int) -> bool:
        """Для совместимости вызывает deactivate_wallet (мягкое удаление)."""
        logger.info(f"Удаление (деактивация) кошелька #{wallet_id} (мягкое)")
        return await self.deactivate_wallet(wallet_id)

    @db_retry()
    async def create_crypto_transaction(self, order_id: int, wallet_id: int,
                                        crypto_type: str, to_address: str, amount: float) -> int:
        """
        Создаёт запись о крипто-транзакции со статусом 'pending'.
        Возвращает ID созданной транзакции.
        """
        logger.info(f"Создание записи о транзакции: order #{order_id}, wallet #{wallet_id}, {crypto_type}, сумма {amount}")
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO crypto_transactions 
                (order_id, wallet_id, crypto_type, to_address, amount, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (order_id, wallet_id, crypto_type, to_address, amount))
            await self.conn.commit()
            tx_id = cursor.lastrowid
            logger.info(f"Транзакция #{tx_id} создана")
            return tx_id

    @db_retry()
    async def update_crypto_transaction(self, tx_id: int, **kwargs) -> bool:
        """
        Обновляет поля транзакции.
        Допустимые поля: status, tx_hash, confirmations, fee_paid, error_message,
                        broadcasted_at, confirmed_at.
        """
        allowed = ['status', 'tx_hash', 'confirmations', 'fee_paid', 'error_message',
                   'broadcasted_at', 'confirmed_at']
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            logger.warning(f"Нет допустимых полей для обновления транзакции #{tx_id}")
            return False

        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [tx_id]
        logger.info(f"Обновление транзакции #{tx_id}: {updates}")
        async with self.lock:
            await self.conn.execute(f"UPDATE crypto_transactions SET {set_clause} WHERE id = ?", values)
            await self.conn.commit()
            logger.info(f"Транзакция #{tx_id} обновлена")
            return True

    @db_retry()
    async def get_transaction(self, tx_id: int) -> Optional[CryptoTransaction]:
        """Получает транзакцию по ID."""
        logger.debug(f"Запрос транзакции #{tx_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE id = ?", (tx_id,)
            )
            row = await cursor.fetchone()
            if row:
                logger.debug(f"Транзакция #{tx_id} найдена")
                return CryptoTransaction(**dict(row))
            logger.debug(f"Транзакция #{tx_id} не найдена")
            return None

    @db_retry()
    async def get_transactions_by_order(self, order_id: int) -> List[CryptoTransaction]:
        """Возвращает все транзакции, связанные с заказом."""
        logger.debug(f"Запрос транзакций по заказу #{order_id}")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE order_id = ? ORDER BY created_at DESC",
                (order_id,)
            )
            rows = await cursor.fetchall()
            txs = [CryptoTransaction(**dict(row)) for row in rows]
            logger.debug(f"Найдено {len(txs)} транзакций")
            return txs

    @db_retry()
    async def get_pending_transactions(self) -> List[CryptoTransaction]:
        """Возвращает все транзакции со статусом 'pending' или 'broadcasted'."""
        logger.debug("Запрос ожидающих и отправленных транзакций")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE status IN ('pending', 'broadcasted')"
            )
            rows = await cursor.fetchall()
            txs = [CryptoTransaction(**dict(row)) for row in rows] if rows else []
            logger.debug(f"Найдено {len(txs)} ожидающих/отправленных транзакций")
            return txs

    @db_retry()
    async def get_recent_crypto_transactions(self, limit: int = 20) -> List[CryptoTransaction]:
        """Возвращает последние крипто-транзакции (независимо от статуса)."""
        logger.debug(f"Запрос последних {limit} крипто-транзакций")
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM crypto_transactions 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            txs = [CryptoTransaction(**dict(row)) for row in rows] if rows else []
            logger.debug(f"Получено {len(txs)} транзакций")
            return txs