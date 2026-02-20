# bot/services/admin_wallet_service.py
"""
Сервис для админ-операций с крипто-кошельками.
Предоставляет методы для добавления, просмотра, деактивации кошельков,
обновления балансов и получения истории транзакций.
"""

import logging
from typing import List, Optional, Dict, Any

from bot.services.db import Database
from bot.services.crypto_wallets import CryptoWalletManager

logger = logging.getLogger(__name__)


class AdminWalletService:
    """
    Сервис для административных операций с кошельками:
    - добавление нового кошелька (с шифрованием приватного ключа)
    - получение списка кошельков (активных/всех)
    - деактивация и полное удаление кошельков
    - обновление балансов всех кошельков
    - получение истории транзакций
    """

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
        """
        Добавить новый кошелёк.
        :param crypto_type: 'BTC' или 'LTC'
        :param address: публичный адрес кошелька
        :param private_key: приватный ключ в формате WIF (будет зашифрован)
        :param label: метка (например, 'Основной BTC')
        :return: ID созданного кошелька или 0 при ошибке
        """
        logger.info(f"Добавление нового кошелька: {crypto_type}, адрес {address}, метка {label}")
        try:
            wallet_id = await self.db.add_wallet(crypto_type, address, private_key, label)
            logger.info(f"Кошелёк добавлен, ID: {wallet_id}")
            return wallet_id
        except Exception as e:
            logger.error(f"Ошибка при добавлении кошелька: {e}", exc_info=True)
            return 0

    async def get_wallets(self, include_inactive: bool = False) -> List:
        """
        Получить список кошельков.
        :param include_inactive: если True, включать неактивные кошельки
        """
        logger.info(f"Запрос списка кошельков (include_inactive={include_inactive})")
        try:
            wallets = await self.db.get_all_wallets(include_inactive=include_inactive)
            logger.debug(f"Получено {len(wallets)} кошельков")
            return wallets
        except Exception as e:
            logger.error(f"Ошибка при получении списка кошельков: {e}", exc_info=True)
            return []

    async def deactivate_wallet(self, wallet_id: int) -> bool:
        """
        Деактивировать кошелёк (мягкое удаление, is_active = False).
        """
        logger.info(f"Деактивация кошелька #{wallet_id}")
        try:
            result = await self.db.deactivate_wallet(wallet_id)
            if result:
                logger.info(f"Кошелёк #{wallet_id} деактивирован")
            else:
                logger.warning(f"Не удалось деактивировать кошелёк #{wallet_id} (возможно, не существует)")
            return result
        except Exception as e:
            logger.error(f"Ошибка при деактивации кошелька #{wallet_id}: {e}", exc_info=True)
            return False

    async def hard_delete_wallet(self, wallet_id: int) -> bool:
        """
        Полностью удалить кошелёк из БД (безвозвратно).
        """
        logger.warning(f"Полное удаление кошелька #{wallet_id}")
        try:
            result = await self.db.wallets.hard_delete_wallet(wallet_id)
            if result:
                logger.info(f"Кошелёк #{wallet_id} полностью удалён")
            else:
                logger.warning(f"Не удалось удалить кошелёк #{wallet_id} (возможно, не существует)")
            return result
        except Exception as e:
            logger.error(f"Ошибка при полном удалении кошелька #{wallet_id}: {e}", exc_info=True)
            return False

    async def refresh_balances(self) -> Dict[str, float]:
        """
        Обновить балансы всех кошельков и вернуть суммарные балансы по типам.
        """
        logger.info("Обновление балансов всех кошельков")
        wallets = await self.db.get_all_wallets()
        btc_balance = 0.0
        ltc_balance = 0.0
        updated_count = 0
        for wallet in wallets:
            try:
                result = await self.wallet_manager.update_balance(wallet.id)
                if result['success']:
                    updated_count += 1
                    if wallet.crypto_type == 'BTC':
                        btc_balance += result['balance']
                    elif wallet.crypto_type == 'LTC':
                        ltc_balance += result['balance']
                else:
                    logger.warning(f"Не удалось обновить баланс кошелька #{wallet.id}: {result.get('error')}")
            except Exception as e:
                logger.error(f"Ошибка при обновлении баланса кошелька #{wallet.id}: {e}", exc_info=True)

        logger.info(f"Обновлено балансов: {updated_count} из {len(wallets)}. BTC: {btc_balance}, LTC: {ltc_balance}")
        return {'BTC': btc_balance, 'LTC': ltc_balance}