"""initial_schema

Revision ID: 1ea9a06be25a
Revises: 
Create Date: 2026-02-18 18:41:49.936198

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ea9a06be25a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица users
    op.create_table('users',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_activity', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('total_exchanges', sa.Integer(), server_default='0', nullable=True),
        sa.Column('total_volume', sa.Float(), server_default='0', nullable=True),
        sa.Column('is_banned', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('ban_reason', sa.String(), nullable=True),
        sa.Column('ban_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('banned_by', sa.Integer(), nullable=True),
        sa.Column('referral_code', sa.String(), nullable=True, unique=True),
        sa.Column('referred_by', sa.Integer(), nullable=True),
        sa.Column('bonus_balance', sa.Float(), server_default='0', nullable=True),
        sa.Column('language', sa.String(), server_default='ru', nullable=True),
        sa.Column('notifications_enabled', sa.Boolean(), server_default='1', nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )

    # Таблица exchange_orders
    op.create_table('exchange_orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('crypto_type', sa.String(), nullable=False),
        sa.Column('amount_rub', sa.Float(), nullable=False),
        sa.Column('amount_crypto', sa.Float(), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('fee_percent', sa.Float(), nullable=False),
        sa.Column('discount_percent', sa.Float(), server_default='0', nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=True),
        sa.Column('bank_receipt', sa.String(), nullable=True),
        sa.Column('crypto_address', sa.String(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('paid_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('admin_comment', sa.String(), nullable=True),
        sa.Column('promo_code', sa.String(), nullable=True),
        sa.Column('admin_checked_by', sa.Integer(), nullable=True),
        sa.Column('admin_checked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('manual_payment_details', sa.String(), nullable=True),
        sa.Column('tx_hash', sa.String(), nullable=True),
        sa.Column('reminder_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('last_reminder_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица bank_details
    op.create_table('bank_details',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('card_number', sa.String(), nullable=False),
        sa.Column('bank_name', sa.String(), nullable=False),
        sa.Column('holder_name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('daily_limit', sa.Float(), server_default='1000000', nullable=True),
        sa.Column('daily_used', sa.Float(), server_default='0', nullable=True),
        sa.Column('last_reset_date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('added_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица promo_codes
    op.create_table('promo_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(), nullable=False, unique=True),
        sa.Column('discount_percent', sa.Float(), nullable=False),
        sa.Column('max_uses', sa.Integer(), server_default='100', nullable=True),
        sa.Column('used_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('valid_from', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('valid_to', sa.TIMESTAMP(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица promo_usage
    op.create_table('promo_usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('promo_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['promo_id'], ['promo_codes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.UniqueConstraint('promo_id', 'user_id'),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица financial_records
    op.create_table('financial_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('record_type', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(), server_default='RUB', nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['exchange_orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица system_settings
    op.create_table('system_settings',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )
    # Вставляем начальную запись для payment_mode
    op.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('payment_mode', 'auto')")

    # Таблица user_sessions
    op.create_table('user_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_activity', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица referral_earnings
    op.create_table('referral_earnings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('referrer_id', sa.Integer(), nullable=False),
        sa.Column('referred_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('percent', sa.Float(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('is_paid', sa.Boolean(), server_default='0', nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['exchange_orders.id'], ),
        sa.ForeignKeyConstraint(['referred_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['referrer_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица exchange_wallets
    op.create_table('exchange_wallets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('crypto_type', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=False, unique=True),
        sa.Column('private_key', sa.String(), nullable=False),
        sa.Column('balance', sa.Float(), server_default='0', nullable=True),
        sa.Column('pending_balance', sa.Float(), server_default='0', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('is_default', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_balance_check', sa.TIMESTAMP(), nullable=True),
        sa.Column('total_sent', sa.Float(), server_default='0', nullable=True),
        sa.Column('total_received', sa.Float(), server_default='0', nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Таблица crypto_transactions
    op.create_table('crypto_transactions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('wallet_id', sa.Integer(), nullable=False),
        sa.Column('crypto_type', sa.String(), nullable=False),
        sa.Column('to_address', sa.String(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('fee', sa.Float(), nullable=True),
        sa.Column('fee_paid', sa.Float(), nullable=True),
        sa.Column('tx_hash', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=True),
        sa.Column('confirmations', sa.Integer(), server_default='0', nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('broadcasted_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('confirmed_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['exchange_orders.id'], ),
        sa.ForeignKeyConstraint(['wallet_id'], ['exchange_wallets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Индексы
    op.create_index('idx_orders_user_id', 'exchange_orders', ['user_id'])
    op.create_index('idx_orders_status', 'exchange_orders', ['status'])
    op.create_index('idx_orders_created', 'exchange_orders', ['created_at'])
    op.create_index('idx_financial_type', 'financial_records', ['record_type'])
    op.create_index('idx_financial_date', 'financial_records', ['created_at'])
    op.create_index('idx_users_banned', 'users', ['is_banned'])
    op.create_index('idx_promo_code', 'promo_codes', ['code'])
    op.create_index('idx_crypto_tx_order', 'crypto_transactions', ['order_id'])
    op.create_index('idx_crypto_tx_status', 'crypto_transactions', ['status'])
    op.create_index('idx_wallets_type', 'exchange_wallets', ['crypto_type'])
    op.create_index('idx_wallets_active', 'exchange_wallets', ['is_active'])


def downgrade() -> None:
    # Удаление таблиц в обратном порядке (с учётом зависимостей)
    op.drop_table('crypto_transactions')
    op.drop_table('exchange_wallets')
    op.drop_table('referral_earnings')
    op.drop_table('user_sessions')
    op.drop_table('system_settings')
    op.drop_table('financial_records')
    op.drop_table('promo_usage')
    op.drop_table('promo_codes')
    op.drop_table('bank_details')
    op.drop_table('exchange_orders')
    op.drop_table('users')