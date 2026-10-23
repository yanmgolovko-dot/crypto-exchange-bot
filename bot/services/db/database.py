# bot/services/db/database.py
"""Основной класс базы данных, объединяющий все репозитории"""

from .connection import DatabaseConnection
from .user_repository import UserRepository
from .order_repository import OrderRepository
from .wallet_repository import WalletRepository
from .bank_repository import BankRepository
from .promo_repository import PromoRepository
from .finance_repository import FinanceRepository
from .settings_repository import SettingsRepository
from .coupon_repository import CouponRepository
from .activity_award_repository import ActivityAwardRepository
from .ticket_repository import TicketRepository
from .review_repository import ReviewRepository
from .partner_repository import PartnerRepository
from .admins_repository import AdminsRepository
from .unit_of_work import UnitOfWork
from .base import db_retry

import logging
import shutil
import os
from datetime import datetime


class Database:
    """Единый класс для доступа ко всем репозиториям с обратной совместимостью"""

    def __init__(self):
        self._connection = DatabaseConnection()
        self.users = UserRepository(self._connection)
        self.orders = OrderRepository(self._connection)
        self.wallets = WalletRepository(self._connection)
        self.bank = BankRepository(self._connection)
        self.promo = PromoRepository(self._connection)
        self.finance = FinanceRepository(self._connection)
        self.settings = SettingsRepository(self._connection)
        self.coupons = CouponRepository(self._connection)
        self.activity_awards = ActivityAwardRepository(self._connection)
        self.tickets = TicketRepository(self._connection)
        self.reviews = ReviewRepository(self._connection)
        self.partners = PartnerRepository(self._connection)
        self.admins = AdminsRepository(self._connection)

        # Пользователи
        self.add_or_update_user = self.users.add_or_update_user
        self.set_referrer = self.users.set_referrer
        self.get_user = self.users.get_user
        self.get_user_by_username = self.users.get_user_by_username
        self.get_user_by_referral_code = self.users.get_user_by_referral_code
        self.set_user_referral_code = self.users.set_user_referral_code
        self.get_all_users = self.users.get_all_users
        self.ban_user = self.users.ban_user
        self.unban_user = self.users.unban_user
        self.is_user_banned = self.users.is_user_banned
        self.get_user_stats = self.users.get_user_stats
        self.set_user_notifications = self.users.set_user_notifications
        self.add_referral_earning = self.users.add_referral_earning
        self.get_referral_earnings = self.users.get_referral_earnings
        self.create_session = self.users.create_session
        self.update_session_activity = self.users.update_session_activity
        self.get_online_users = self.users.get_online_users
        self.update_last_activity = self.users.update_last_activity
        self.increment_total_exchanges = self.users.increment_total_exchanges
        self.add_spin = self.users.add_spin
        self.use_spin = self.users.use_spin
        self.get_available_spins = self.users.get_available_spins
        self.add_bonus_balance = self.users.add_bonus_balance

        # Заявки
        self.create_order = self.orders.create_order
        self.get_order = self.orders.get_order
        self.update_order_status = self.orders.update_order_status
        self.add_bank_receipt = self.orders.add_bank_receipt
        self.get_user_orders = self.orders.get_user_orders
        self.get_pending_orders = self.orders.get_pending_orders
        self.get_all_orders = self.orders.get_all_orders
        self.set_order_manual_payment_details = self.orders.set_order_manual_payment_details
        self.update_order_tx_hash = self.orders.update_order_tx_hash

        # Кошельки
        self.add_wallet = self.wallets.add_wallet
        self.get_wallet = self.wallets.get_wallet
        self.get_all_wallets = self.wallets.get_all_wallets
        self.update_wallet_balance = self.wallets.update_wallet_balance
        self.delete_wallet = self.wallets.delete_wallet
        self.deactivate_wallet = self.wallets.deactivate_wallet
        self.create_crypto_transaction = self.wallets.create_crypto_transaction
        self.update_crypto_transaction = self.wallets.update_crypto_transaction
        self.get_transaction = self.wallets.get_transaction
        self.get_transactions_by_order = self.wallets.get_transactions_by_order
        self.get_pending_transactions = self.wallets.get_pending_transactions
        self.get_recent_crypto_transactions = self.wallets.get_recent_crypto_transactions

        # Банковские реквизиты
        self.add_bank_details = self.bank.add_bank_details
        self.get_bank_details = self.bank.get_bank_details
        self.get_all_bank_details = self.bank.get_all_bank_details
        self.update_bank_details = self.bank.update_bank_details
        self.delete_bank_details = self.bank.delete_bank_details
        self.set_default_bank_details = self.bank.set_default_bank_details

        # Промокоды
        self.create_promo_code = self.promo.create_promo_code
        self.get_promo_code = self.promo.get_promo_code
        self.validate_promo_code = self.promo.validate_promo_code
        self.use_promo_code = self.promo.use_promo_code
        self.get_all_promo_codes = self.promo.get_all_promo_codes
        self.toggle_promo_code = self.promo.toggle_promo_code
        self.get_user_used_promo_ids = self.promo.get_user_used_promo_ids

        # Финансы
        self.add_financial_record = self.finance.add_financial_record
        self.get_financial_stats = self.finance.get_financial_stats
        self.get_recent_financial_records = self.finance.get_recent_financial_records
        self.get_daily_stats = self.finance.get_daily_stats
        self.get_dashboard_stats = self.finance.get_dashboard_stats

        # Настройки
        self.get_setting = self.settings.get_setting
        self.set_setting = self.settings.set_setting
        self.get_exchange_fee = self.settings.get_exchange_fee
        self.set_exchange_fee = self.settings.set_exchange_fee
        self.get_payment_mode = self.settings.get_payment_mode
        self.set_payment_mode = self.settings.set_payment_mode
        self.get_bot_version = self.settings.get_bot_version
        self.increment_bot_version = self.settings.increment_bot_version
        self.get_manual_payment_source = self.settings.get_manual_payment_source
        self.set_manual_payment_source = self.settings.set_manual_payment_source
        self.get_log_level = self.settings.get_log_level
        self.set_log_level = self.settings.set_log_level

        # Купоны
        self.create_coupon = self.coupons.create_coupon
        self.get_coupon = self.coupons.get_coupon
        self.validate_coupon = self.coupons.validate_coupon
        self.use_coupon = self.coupons.use_coupon
        self.get_all_coupons = self.coupons.get_all_coupons
        self.toggle_coupon = self.coupons.toggle_coupon
        self.get_user_coupons = self.coupons.get_user_coupons  # <-- НОВЫЙ ПРОКСИ

        # Дополнительные методы
        self._backup_db = self._backup_db
        self.clear_all_orders = self.clear_all_orders

    def uow(self) -> UnitOfWork:
        return UnitOfWork(self._connection)

    async def connect(self):
        await self._connection.connect()

    async def close(self):
        await self._connection.close()

    @db_retry()
    async def clear_all_orders(self) -> bool:
        await self._backup_db()
        async with self._connection.lock:
            await self._connection.conn.execute("UPDATE financial_records SET order_id = NULL WHERE order_id IS NOT NULL")
            await self._connection.conn.execute("DELETE FROM crypto_transactions")
            await self._connection.conn.execute("DELETE FROM promo_usage WHERE order_id IS NOT NULL")
            await self._connection.conn.execute("DELETE FROM referral_earnings WHERE order_id IS NOT NULL")
            await self._connection.conn.execute("DELETE FROM exchange_orders")
            await self._connection.conn.commit()
            return True

    async def _backup_db(self):
        try:
            db_path = self._connection.db_path
            if not os.path.exists(db_path):
                self.logger.warning("Файл БД не найден, резервное копирование невозможно")
                return
            backup_dir = os.path.join(os.path.dirname(db_path), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"exchange_backup_{timestamp}.db")
            shutil.copy2(db_path, backup_path)
            self.logger.info(f"Резервная копия БД создана: {backup_path}")
        except Exception as e:
            self.logger.error(f"Ошибка при создании резервной копии БД: {e}")

    @property
    def logger(self):
        return logging.getLogger(__name__)