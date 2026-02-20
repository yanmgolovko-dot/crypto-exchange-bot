"""Unit of Work для управления транзакциями"""

from typing import Optional
import logging

from bot.services.db.connection import DatabaseConnection
from bot.services.db.user_repository import UserRepository
from bot.services.db.order_repository import OrderRepository
from bot.services.db.wallet_repository import WalletRepository
from bot.services.db.bank_repository import BankRepository
from bot.services.db.promo_repository import PromoRepository
from bot.services.db.finance_repository import FinanceRepository
from bot.services.db.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


class UnitOfWork:
    def __init__(self, connection: DatabaseConnection):
        self._connection = connection
        self.users = UserRepository(connection)
        self.orders = OrderRepository(connection)
        self.wallets = WalletRepository(connection)
        self.bank = BankRepository(connection)
        self.promo = PromoRepository(connection)
        self.finance = FinanceRepository(connection)
        self.settings = SettingsRepository(connection)

    async def __aenter__(self):
        logger.debug("Starting transaction")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
            logger.error(f"Transaction rolled back due to {exc_type.__name__}: {exc_val}")

    async def commit(self):
        await self._connection.conn.commit()
        logger.debug("Transaction committed")

    async def rollback(self):
        await self._connection.conn.rollback()
        logger.debug("Transaction rolled back")