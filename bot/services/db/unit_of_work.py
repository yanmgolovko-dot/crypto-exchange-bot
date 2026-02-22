# bot/services/db/unit_of_work.py
"""Unit of Work для управления транзакциями."""

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
from bot.services.db.coupon_repository import CouponRepository
from bot.services.db.activity_award_repository import ActivityAwardRepository
from bot.services.db.ticket_repository import TicketRepository
from bot.services.db.review_repository import ReviewRepository

logger = logging.getLogger(__name__)


class UnitOfWork:
    """
    Класс для группировки операций с БД в единую транзакцию.
    Предоставляет доступ ко всем репозиториям и управляет commit/rollback.
    Используется в сервисах для атомарных операций.
    """

    def __init__(self, connection: DatabaseConnection):
        self._connection = connection
        self.users = UserRepository(connection)
        self.orders = OrderRepository(connection)
        self.wallets = WalletRepository(connection)
        self.bank = BankRepository(connection)
        self.promo = PromoRepository(connection)
        self.finance = FinanceRepository(connection)
        self.settings = SettingsRepository(connection)
        self.coupons = CouponRepository(connection)
        # НОВЫЕ РЕПОЗИТОРИИ
        self.activity_awards = ActivityAwardRepository(connection)
        self.tickets = TicketRepository(connection)
        self.reviews = ReviewRepository(connection)
        logger.debug("UnitOfWork инициализирован")

    async def __aenter__(self):
        """Вход в контекстный менеджер – начало транзакции (логически)."""
        logger.debug("Начало транзакции (UnitOfWork)")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Выход из контекстного менеджера.
        Если было исключение – откат, иначе транзакция должна быть закоммичена явно.
        """
        if exc_type is not None:
            await self.rollback()
            logger.error(f"Транзакция откачена из-за {exc_type.__name__}: {exc_val}")
        else:
            # Если нет исключения, но commit не был вызван, можно выполнить rollback по умолчанию?
            # Лучше требовать явный commit.
            logger.debug("Выход из UnitOfWork без commit – предполагается явный commit до выхода")

    async def commit(self):
        """Фиксация транзакции."""
        await self._connection.conn.commit()
        logger.debug("Транзакция закоммичена")

    async def rollback(self):
        """Откат транзакции."""
        await self._connection.conn.rollback()
        logger.debug("Транзакция откачена")