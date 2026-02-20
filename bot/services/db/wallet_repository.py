"""Репозиторий для работы с крипто-кошельками и транзакциями"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from .base import BaseRepository, db_retry
import aiosqlite

from ...utils.encryption import encrypt_private_key, decrypt_private_key


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

    @db_retry()
    async def add_wallet(self, crypto_type: str, address: str, private_key: str, label: str = None) -> int:
        if not private_key:
            raise ValueError("Приватный ключ не может быть пустым")
        encrypted_key = encrypt_private_key(private_key)
        async with self.lock:
            cursor = await self.conn.execute(
                "SELECT COUNT(*) FROM exchange_wallets WHERE crypto_type = ?",
                (crypto_type,)
            )
            count = (await cursor.fetchone())[0]
            is_default = count == 0

            cursor = await self.conn.execute("""
                INSERT INTO exchange_wallets 
                (crypto_type, address, private_key, label, is_default)
                VALUES (?, ?, ?, ?, ?)
            """, (crypto_type, address, encrypted_key, label, is_default))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def get_wallet(self, wallet_id: int = None, crypto_type: str = None, include_inactive: bool = False) -> Optional[Wallet]:
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
                return None
            row = await cursor.fetchone()
            if row:
                return Wallet(**dict(row))
            return None

    @db_retry()
    async def get_all_wallets(self, crypto_type: str = None, include_inactive: bool = False) -> List[Wallet]:
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
            return [Wallet(**dict(row)) for row in rows]

    @db_retry()
    async def update_wallet_balance(self, wallet_id: int, balance: float, pending_balance: float) -> bool:
        async with self.lock:
            await self.conn.execute("""
                UPDATE exchange_wallets 
                SET balance = ?, pending_balance = ?, last_balance_check = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (balance, pending_balance, wallet_id))
            await self.conn.commit()
            return True

    @db_retry()
    async def deactivate_wallet(self, wallet_id: int) -> bool:
        """Мягкое удаление кошелька (установка is_active = 0)"""
        async with self.lock:
            await self.conn.execute(
                "UPDATE exchange_wallets SET is_active = 0 WHERE id = ?",
                (wallet_id,)
            )
            await self.conn.commit()
            return True

    @db_retry()
    async def hard_delete_wallet(self, wallet_id: int) -> bool:
        """Полностью удаляет кошелёк из базы данных (безвозвратно)."""
        async with self.lock:
            await self.conn.execute("DELETE FROM exchange_wallets WHERE id = ?", (wallet_id,))
            await self.conn.commit()
            return True

    @db_retry()
    async def delete_wallet(self, wallet_id: int) -> bool:
        """Для совместимости вызывает deactivate_wallet"""
        return await self.deactivate_wallet(wallet_id)

    @db_retry()
    async def create_crypto_transaction(self, order_id: int, wallet_id: int,
                                        crypto_type: str, to_address: str, amount: float) -> int:
        async with self.lock:
            cursor = await self.conn.execute("""
                INSERT INTO crypto_transactions 
                (order_id, wallet_id, crypto_type, to_address, amount, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (order_id, wallet_id, crypto_type, to_address, amount))
            await self.conn.commit()
            return cursor.lastrowid

    @db_retry()
    async def update_crypto_transaction(self, tx_id: int, **kwargs) -> bool:
        allowed = ['status', 'tx_hash', 'confirmations', 'fee_paid', 'error_message',
                   'broadcasted_at', 'confirmed_at']
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [tx_id]
        async with self.lock:
            await self.conn.execute(f"UPDATE crypto_transactions SET {set_clause} WHERE id = ?", values)
            await self.conn.commit()
            return True

    @db_retry()
    async def get_transaction(self, tx_id: int) -> Optional[CryptoTransaction]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE id = ?", (tx_id,)
            )
            row = await cursor.fetchone()
            if row:
                return CryptoTransaction(**dict(row))
            return None

    @db_retry()
    async def get_transactions_by_order(self, order_id: int) -> List[CryptoTransaction]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE order_id = ? ORDER BY created_at DESC",
                (order_id,)
            )
            rows = await cursor.fetchall()
            return [CryptoTransaction(**dict(row)) for row in rows]

    @db_retry()
    async def get_pending_transactions(self) -> List[CryptoTransaction]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute(
                "SELECT * FROM crypto_transactions WHERE status IN ('pending', 'broadcasted')"
            )
            rows = await cursor.fetchall()
            return [CryptoTransaction(**dict(row)) for row in rows] if rows else []

    @db_retry()
    async def get_recent_crypto_transactions(self, limit: int = 20) -> List[CryptoTransaction]:
        async with self.lock:
            self.conn.row_factory = aiosqlite.Row
            cursor = await self.conn.execute("""
                SELECT * FROM crypto_transactions 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            return [CryptoTransaction(**dict(row)) for row in rows] if rows else []