"""Сервис для админ-операций с кошельками"""

import logging
from typing import List, Optional, Dict, Any

from bot.services.db import Database
from bot.services.crypto_wallets import CryptoWalletManager

logger = logging.getLogger(__name__)


class AdminWalletService:
    def __init__(self, db: Database, wallet_manager: CryptoWalletManager):
        self.db = db
        self.wallet_manager = wallet_manager

    async def add_wallet(
        self,
        crypto_type: str,
        address: str,
        private_key: str,
        label: Optional[str] = None
    ) -> int:
        """Добавить новый кошелёк"""
        return await self.db.add_wallet(crypto_type, address, private_key, label)

    async def get_wallets(self, include_inactive: bool = False) -> List:
        """Получить список кошельков"""
        return await self.db.get_all_wallets(include_inactive=include_inactive)

    async def deactivate_wallet(self, wallet_id: int) -> bool:
        """Деактивировать кошелёк (мягкое удаление)"""
        return await self.db.deactivate_wallet(wallet_id)

    async def hard_delete_wallet(self, wallet_id: int) -> bool:
        """Полностью удалить кошелёк из БД (безвозвратно)"""
        return await self.db.wallets.hard_delete_wallet(wallet_id)

    async def refresh_balances(self) -> Dict[str, float]:
        """Обновить балансы всех кошельков и вернуть суммарные балансы по типам"""
        wallets = await self.db.get_all_wallets()
        btc_balance = 0.0
        ltc_balance = 0.0
        for wallet in wallets:
            result = await self.wallet_manager.update_balance(wallet.id)
            if result['success']:
                if wallet.crypto_type == 'BTC':
                    btc_balance += result['balance']
                elif wallet.crypto_type == 'LTC':
                    ltc_balance += result['balance']
        return {'BTC': btc_balance, 'LTC': ltc_balance}