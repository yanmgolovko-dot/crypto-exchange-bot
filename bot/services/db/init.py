# bot/services/db/init.py
"""Синхронная инициализация базы данных (создание таблиц и обновление схемы)."""

import sqlite3
import os
import logging
from bot.config.settings import config

logger = logging.getLogger(__name__)


def init_db_sync():
    """
    Создаёт таблицы, если их нет, и добавляет недостающие колонки (вызывается при запуске).
    Выполняется синхронно в отдельном потоке при старте бота.
    """
    logger.info("Синхронная инициализация базы данных")
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    c = conn.cursor()
    logger.debug("Подключение к БД для инициализации установлено")

    # Таблица users
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_exchanges INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            ban_reason TEXT,
            ban_date TIMESTAMP,
            banned_by INTEGER,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            bonus_balance REAL DEFAULT 0,
            language TEXT DEFAULT 'ru',
            notifications_enabled BOOLEAN DEFAULT 1
        )
    """)
    logger.debug("Таблица users проверена/создана")

    # Таблица exchange_orders
    c.execute("""
        CREATE TABLE IF NOT EXISTS exchange_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            crypto_type TEXT NOT NULL,
            amount_rub REAL NOT NULL,
            amount_crypto REAL NOT NULL,
            rate REAL NOT NULL,
            fee_percent REAL NOT NULL,
            discount_percent REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            bank_receipt TEXT,
            crypto_address TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            completed_at TIMESTAMP,
            admin_comment TEXT,
            promo_code TEXT,
            admin_checked_by INTEGER,
            admin_checked_at TIMESTAMP,
            manual_payment_details TEXT,
            tx_hash TEXT,
            reminder_count INTEGER DEFAULT 0,
            last_reminder_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    logger.debug("Таблица exchange_orders проверена/создана")

    # Таблица bank_details
    c.execute("""
        CREATE TABLE IF NOT EXISTS bank_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_number TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            holder_name TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            is_default BOOLEAN DEFAULT 0,
            daily_limit REAL DEFAULT 1000000,
            daily_used REAL DEFAULT 0,
            last_reset_date DATE DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            added_by INTEGER
        )
    """)
    logger.debug("Таблица bank_details проверена/создана")

    # Таблица promo_codes
    c.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_percent REAL NOT NULL,
            max_uses INTEGER DEFAULT 100,
            used_count INTEGER DEFAULT 0,
            valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_to TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)
    logger.debug("Таблица promo_codes проверена/создана")

    # Таблица promo_usage
    c.execute("""
        CREATE TABLE IF NOT EXISTS promo_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (promo_id) REFERENCES promo_codes(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(promo_id, user_id)
        )
    """)
    logger.debug("Таблица promo_usage проверена/создана")

    # Таблица financial_records
    c.execute("""
        CREATE TABLE IF NOT EXISTS financial_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'RUB',
            description TEXT,
            order_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES exchange_orders(id)
        )
    """)
    logger.debug("Таблица financial_records проверена/создана")

    # Таблица system_settings
    c.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)
    # Вставляем начальную запись для payment_mode, если её нет
    c.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('payment_mode', 'auto')")
    logger.debug("Таблица system_settings проверена/создана, добавлен payment_mode по умолчанию")

    # Таблица user_sessions
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            user_agent TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    logger.debug("Таблица user_sessions проверена/создана")

    # Таблица referral_earnings
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            percent REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_paid BOOLEAN DEFAULT 0,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id),
            FOREIGN KEY (order_id) REFERENCES exchange_orders(id)
        )
    """)
    logger.debug("Таблица referral_earnings проверена/создана")

    # Таблица exchange_wallets
    c.execute("""
        CREATE TABLE IF NOT EXISTS exchange_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crypto_type TEXT NOT NULL,
            address TEXT UNIQUE NOT NULL,
            private_key TEXT NOT NULL,
            balance REAL DEFAULT 0,
            pending_balance REAL DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            is_default BOOLEAN DEFAULT 0,
            label TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_balance_check TIMESTAMP,
            total_sent REAL DEFAULT 0,
            total_received REAL DEFAULT 0
        )
    """)
    logger.debug("Таблица exchange_wallets проверена/создана")

    # Таблица crypto_transactions
    c.execute("""
        CREATE TABLE IF NOT EXISTS crypto_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            wallet_id INTEGER NOT NULL,
            crypto_type TEXT NOT NULL,
            to_address TEXT NOT NULL,
            amount REAL NOT NULL,
            fee REAL,
            fee_paid REAL,
            tx_hash TEXT,
            status TEXT DEFAULT 'pending',
            confirmations INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            broadcasted_at TIMESTAMP,
            confirmed_at TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES exchange_orders(id),
            FOREIGN KEY (wallet_id) REFERENCES exchange_wallets(id)
        )
    """)
    logger.debug("Таблица crypto_transactions проверена/создана")

    # Индексы для ускорения запросов
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_id ON exchange_orders(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON exchange_orders(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON exchange_orders(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_financial_type ON financial_records(record_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_financial_date ON financial_records(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_promo_code ON promo_codes(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_crypto_tx_order ON crypto_transactions(order_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_crypto_tx_status ON crypto_transactions(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wallets_type ON exchange_wallets(crypto_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wallets_active ON exchange_wallets(is_active)")
    logger.debug("Индексы проверены/созданы")

    # Добавляем недостающие колонки (миграция для reminder_count и last_reminder_at)
    # Эти колонки могли быть добавлены позже, поэтому используем try-except
    try:
        c.execute("ALTER TABLE exchange_orders ADD COLUMN reminder_count INTEGER DEFAULT 0")
        logger.info("Колонка reminder_count добавлена в exchange_orders")
    except sqlite3.OperationalError:
        # колонка уже существует
        logger.debug("Колонка reminder_count уже существует")

    try:
        c.execute("ALTER TABLE exchange_orders ADD COLUMN last_reminder_at TIMESTAMP")
        logger.info("Колонка last_reminder_at добавлена в exchange_orders")
    except sqlite3.OperationalError:
        logger.debug("Колонка last_reminder_at уже существует")

    conn.commit()
    conn.close()
    logger.info("Инициализация БД завершена")