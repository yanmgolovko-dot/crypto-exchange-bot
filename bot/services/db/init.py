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

    # ===== СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ (без изменений, но с IF NOT EXISTS) =====
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)
    c.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('payment_mode', 'auto')")
    logger.debug("Таблица system_settings проверена/создана, добавлен payment_mode по умолчанию")

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

    # ===== ТАБЛИЦЫ КУПОНОВ (уже есть, добавим недостающие колонки) =====
    c.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value REAL NOT NULL,
            discount_on TEXT NOT NULL,
            max_uses_total INTEGER,
            max_uses_per_user INTEGER,
            used_count INTEGER DEFAULT 0,
            min_order_amount REAL DEFAULT 0,
            valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_to TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)
    logger.debug("Таблица coupons проверена/создана")

    # Добавляем новые колонки в coupons, если их нет
    try:
        c.execute("ALTER TABLE coupons ADD COLUMN owner_id INTEGER NULL REFERENCES users(user_id)")
        logger.info("Колонка owner_id добавлена в coupons")
    except sqlite3.OperationalError:
        logger.debug("Колонка owner_id уже существует")

    try:
        c.execute("ALTER TABLE coupons ADD COLUMN coupon_type TEXT DEFAULT 'generic'")
        logger.info("Колонка coupon_type добавлена в coupons")
    except sqlite3.OperationalError:
        logger.debug("Колонка coupon_type уже существует")

    c.execute("""
        CREATE TABLE IF NOT EXISTS coupon_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coupon_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (coupon_id) REFERENCES coupons(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(coupon_id, user_id, order_id)
        )
    """)
    logger.debug("Таблица coupon_usage проверена/создана")

    # ===== НОВЫЕ ТАБЛИЦЫ =====

    # Таблица наград за активность
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            award_type TEXT NOT NULL,
            threshold INTEGER NOT NULL,
            awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            coupon_id INTEGER NULL REFERENCES coupons(id),
            UNIQUE(user_id, award_type)
        )
    """)
    logger.debug("Таблица activity_awards проверена/создана")

    # Таблица тикетов
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            status TEXT DEFAULT 'open',
            subject TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_by INTEGER,
            closed_at TIMESTAMP
        )
    """)
    logger.debug("Таблица tickets проверена/создана")

    # Таблица сообщений тикетов
    c.execute("""
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL,
            is_admin BOOLEAN DEFAULT 0,
            message TEXT NOT NULL,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("Таблица ticket_messages проверена/создана")

    # Таблица отзывов
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id),
            order_id INTEGER NOT NULL REFERENCES exchange_orders(id),
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_approved BOOLEAN DEFAULT 0,
            admin_reply TEXT,
            replied_at TIMESTAMP
        )
    """)
    logger.debug("Таблица reviews проверена/создана")

    # ===== ИНДЕКСЫ (добавляем новые и проверяем старые) =====
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_coupon_code ON coupons(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_coupon_usage_user ON coupon_usage(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_coupon_usage_coupon ON coupon_usage(coupon_id)")

    # Индексы для новых таблиц
    c.execute("CREATE INDEX IF NOT EXISTS idx_activity_awards_user ON activity_awards(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ticket_messages_ticket ON ticket_messages(ticket_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_order ON reviews(order_id)")
    logger.debug("Индексы проверены/созданы")

    # ===== ДОБАВЛЕНИЕ НЕДОСТАЮЩИХ КОЛОНОК В СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ =====
    # reminder_count и last_reminder_at уже должны быть, но проверим
    try:
        c.execute("ALTER TABLE exchange_orders ADD COLUMN reminder_count INTEGER DEFAULT 0")
        logger.info("Колонка reminder_count добавлена в exchange_orders")
    except sqlite3.OperationalError:
        logger.debug("Колонка reminder_count уже существует")

    try:
        c.execute("ALTER TABLE exchange_orders ADD COLUMN last_reminder_at TIMESTAMP")
        logger.info("Колонка last_reminder_at добавлена в exchange_orders")
    except sqlite3.OperationalError:
        logger.debug("Колонка last_reminder_at уже существует")

    try:
        c.execute("ALTER TABLE exchange_orders ADD COLUMN coupon_id INTEGER REFERENCES coupons(id)")
        logger.info("Колонка coupon_id добавлена в exchange_orders")
    except sqlite3.OperationalError:
        logger.debug("Колонка coupon_id уже существует")

    conn.commit()
    conn.close()
    logger.info("Инициализация БД завершена")