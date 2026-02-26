# bot/services/admin_order_service.py
"""Сервис для админ-операций с заявками."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from aiogram import Bot

from bot.services.db import Database
from bot.services.crypto_wallets import CryptoWalletManager
from bot.services.coupon_service import coupon_service
from bot.services.partner_service import partner_service
from bot.config.settings import config
from bot.services.review_notifier import ask_for_review

logger = logging.getLogger(__name__)


class AdminOrderService:
    """Содержит бизнес-логику для подтверждения, отклонения заявок администратором."""

    def __init__(self, db: Database, wallet_manager: CryptoWalletManager):
        self.db = db
        self.wallet_manager = wallet_manager

    async def approve_order_auto(
        self,
        order_id: int,
        admin_id: int,
        bot: Bot
    ) -> Dict[str, Any]:
        """
        Подтверждение заявки в автоматическом режиме.
        Выбирает активный кошелёк с достаточным балансом и отправляет криптовалюту.
        """
        logger.info(f"[ADMIN {admin_id}] Автоматическое подтверждение заявки #{order_id}")

        order = await self.db.get_order(order_id)
        if not order:
            logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не найдена")
            return {'success': False, 'error': 'Заявка не найдена'}

        if order.status != 'paid':
            logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} имеет статус {order.status}, требуется paid")
            return {'success': False, 'error': f'Заявка не в статусе "оплачена". Текущий статус: {order.status}'}

        # Атомарно пытаемся заблокировать заявку (обновить статус на processing)
        async with self.db.uow() as uow:
            cursor = await uow._connection.conn.execute("""
                UPDATE exchange_orders
                SET status = 'processing'
                WHERE id = ? AND status = 'paid'
                RETURNING id
            """, (order_id,))
            row = await cursor.fetchone()
            if not row:
                await uow.rollback()
                logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} уже обрабатывается")
                return {'success': False, 'error': 'Заявка уже обрабатывается или была изменена'}
            await uow.commit()
        logger.debug(f"[ADMIN {admin_id}] Заявка #{order_id} заблокирована (статус processing)")

        wallets = await self.db.get_all_wallets(crypto_type=order.crypto_type, include_inactive=False)
        if not wallets:
            logger.warning(f"[ADMIN {admin_id}] Нет активных кошельков {order.crypto_type} для заявки #{order_id}")
            await self.db.update_order_status(order_id, 'paid', 'Нет кошельков, блокировка снята')
            return {'success': False, 'error': f'Нет активных кошельков {order.crypto_type}'}

        fee_estimate = 0.001 if order.crypto_type == 'LTC' else 0.0001
        required_amount = order.amount_crypto + fee_estimate
        logger.debug(f"Необходимая сумма с учётом комиссии: {required_amount} {order.crypto_type}")

        selected_wallet = None
        for wallet in wallets:
            balance_result = await self.wallet_manager.update_balance(wallet.id)
            if not balance_result['success']:
                logger.warning(f"Не удалось обновить баланс кошелька {wallet.id}: {balance_result.get('error')}")
                continue
            balance = balance_result['balance']
            if balance >= required_amount:
                selected_wallet = wallet
                logger.info(f"Выбран кошелёк {wallet.address} с балансом {balance} {order.crypto_type}")
                break

        if not selected_wallet:
            logger.warning(f"[ADMIN {admin_id}] Недостаточно средств для заявки #{order_id}")
            await self.db.update_order_status(order_id, 'paid', 'Недостаточно средств, блокировка снята')
            return {
                'success': False,
                'error': f'Нет кошельков с достаточным балансом. Требуется {required_amount:.8f} {order.crypto_type}'
            }

        tx_result = await self.wallet_manager.send_transaction_real(
            order_id=order_id,
            crypto_type=order.crypto_type,
            to_address=order.crypto_address,
            amount=order.amount_crypto,
            wallet=selected_wallet
        )

        if not tx_result['success']:
            logger.error(f"[ADMIN {admin_id}] Ошибка отправки транзакции по заявке #{order_id}: {tx_result.get('error')}")
            await self.db.update_order_status(order_id, 'paid', f'Ошибка отправки: {tx_result.get("error")}')
            return {'success': False, 'error': tx_result.get('error', 'Неизвестная ошибка')}

        tx_hash = tx_result.get('tx_hash', 'N/A')
        logger.info(f"[ADMIN {admin_id}] Транзакция отправлена, tx_hash={tx_hash}")

        async with self.db.uow() as uow:
            await uow.orders.update_order_status(
                order_id,
                'completed',
                f"Подтверждено админом {admin_id}. TX: {tx_hash}",
                admin_id
            )
            await uow.finance.add_financial_record(
                record_type='income',
                category='exchange_fee',
                amount=order.amount_rub * order.fee_percent / 100,
                description=f'Комиссия с заявки #{order_id}',
                order_id=order_id,
                created_by=admin_id
            )
            await uow.commit()
        logger.info(f"[ADMIN {admin_id}] Заявка #{order_id} завершена, комиссия записана")

        # Выдаём купоны за активность пользователю
        await coupon_service.check_and_give_activity_coupons(order.user_id)

        # Начисляем партнёрские вознаграждения
        await partner_service.process_order_reward(order)

        # Отправляем предложение оставить отзыв
        await ask_for_review(bot, order.user_id, order_id)

        return {
            'success': True,
            'tx_hash': tx_hash,
            'order': order
        }

    async def approve_order_manual(self, order_id: int, admin_id: int) -> bool:
        logger.info(f"[ADMIN {admin_id}] Ручное подтверждение заявки #{order_id}")
        order = await self.db.get_order(order_id)
        if not order or order.status != 'paid':
            logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не в статусе paid")
            return False
        return True

    async def complete_order_with_tx_hash(
        self,
        order_id: int,
        tx_hash: str,
        admin_id: int,
        bot: Bot
    ) -> bool:
        logger.info(f"[ADMIN {admin_id}] Завершение заявки #{order_id} с хешем {tx_hash}")
        order = await self.db.get_order(order_id)
        if not order:
            logger.warning(f"[ADMIN {admin_id}] Заявка #{order_id} не найдена")
            return False

        async with self.db.uow() as uow:
            await uow.orders.update_order_tx_hash(order_id, tx_hash, admin_id)
            await uow.orders.update_order_status(
                order_id,
                'completed',
                f"Хеш введён админом {admin_id}",
                admin_id
            )
            await uow.finance.add_financial_record(
                record_type='income',
                category='exchange_fee',
                amount=order.amount_rub * order.fee_percent / 100,
                description=f'Комиссия с заявки #{order_id}',
                order_id=order_id,
                created_by=admin_id
            )
            await uow.commit()
        logger.info(f"[ADMIN {admin_id}] Заявка #{order_id} завершена")

        # Выдаём купоны за активность
        await coupon_service.check_and_give_activity_coupons(order.user_id)

        # Начисляем партнёрские вознаграждения
        await partner_service.process_order_reward(order)

        # Отправляем предложение оставить отзыв
        await ask_for_review(bot, order.user_id, order_id)
        return True

    async def reject_order(self, order_id: int, admin_id: int) -> bool:
        logger.info(f"[ADMIN {admin_id}] Отклонение заявки #{order_id}")
        async with self.db.uow() as uow:
            await uow.orders.update_order_status(
                order_id,
                'cancelled',
                f"Отклонено админом {admin_id}",
                admin_id
            )
            await uow.commit()
        return True

    async def request_receipt(self, order_id: int, user_id: int) -> bool:
        logger.debug(f"Запрос чека для заявки #{order_id}")
        order = await self.db.get_order(order_id)
        if not order:
            return False
        return True

    async def send_payment_details(
        self,
        order_id: int,
        details: str,
        user_id: int
    ) -> bool:
        logger.info(f"Сохранение платёжных реквизитов для заявки #{order_id}")
        await self.db.set_order_manual_payment_details(order_id, details)
        return True