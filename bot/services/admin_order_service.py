# bot/services/admin_order_service.py
"""Сервис для админ-операций с заявками."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from bot.services.db import Database
from bot.services.crypto_wallets import CryptoWalletManager
from bot.config.settings import config

logger = logging.getLogger(__name__)


class AdminOrderService:
    """Содержит бизнес-логику для подтверждения, отклонения заявок администратором."""

    def __init__(self, db: Database, wallet_manager: CryptoWalletManager):
        self.db = db
        self.wallet_manager = wallet_manager

    # ========== ИСПРАВЛЕННЫЙ МЕТОД (см. пункт 4) ==========
    async def approve_order_auto(
        self,
        order_id: int,
        admin_id: int
    ) -> Dict[str, Any]:
        """
        Подтверждение заявки в автоматическом режиме.
        Выбирает активный кошелёк с достаточным балансом и отправляет криптовалюту.
        **Добавлена атомарная блокировка заявки через статус 'processing' для предотвращения двойной отправки.**
        """
        order = await self.db.get_order(order_id)
        if not order:
            return {'success': False, 'error': 'Заявка не найдена'}

        # 1. Проверяем, что заявка ещё не завершена и не обрабатывается
        if order.status != 'paid':
            return {'success': False, 'error': f'Заявка не в статусе "оплачена". Текущий статус: {order.status}'}

        # Атомарно пытаемся заблокировать заявку (обновить статус на processing)
        async with self.db.uow() as uow:
            # Пытаемся обновить только если статус всё ещё 'paid'
            cursor = await uow._connection.conn.execute("""
                UPDATE exchange_orders
                SET status = 'processing'
                WHERE id = ? AND status = 'paid'
                RETURNING id
            """, (order_id,))
            row = await cursor.fetchone()
            if not row:
                await uow.rollback()
                return {'success': False, 'error': 'Заявка уже обрабатывается или была изменена'}
            await uow.commit()

        # Получаем все активные кошельки данного типа
        wallets = await self.db.get_all_wallets(crypto_type=order.crypto_type, include_inactive=False)
        if not wallets:
            # Возвращаем статус обратно в paid (снимаем блокировку)
            await self.db.update_order_status(order_id, 'paid', 'Нет кошельков, блокировка снята')
            return {'success': False, 'error': f'Нет активных кошельков {order.crypto_type}'}

        # Определяем примерную комиссию для проверки
        fee_estimate = 0.001 if order.crypto_type == 'LTC' else 0.0001
        required_amount = order.amount_crypto + fee_estimate

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
            # Снимаем блокировку
            await self.db.update_order_status(order_id, 'paid', 'Недостаточно средств, блокировка снята')
            return {
                'success': False,
                'error': f'Нет кошельков с достаточным балансом. Требуется {required_amount:.8f} {order.crypto_type}'
            }

        # Отправляем транзакцию, передавая выбранный кошелёк
        tx_result = await self.wallet_manager.send_transaction_real(
            order_id=order_id,
            crypto_type=order.crypto_type,
            to_address=order.crypto_address,
            amount=order.amount_crypto,
            wallet=selected_wallet
        )

        if not tx_result['success']:
            # Возвращаем статус в paid при ошибке
            await self.db.update_order_status(order_id, 'paid', f'Ошибка отправки: {tx_result.get("error")}')
            return {'success': False, 'error': tx_result.get('error', 'Неизвестная ошибка')}

        tx_hash = tx_result.get('tx_hash', 'N/A')

        # Финальное обновление (заявка переводится в completed)
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

        return {
            'success': True,
            'tx_hash': tx_hash,
            'order': order
        }

    async def approve_order_manual(self, order_id: int, admin_id: int) -> bool:
        """
        Подготовка к ручному подтверждению (после получения оплаты).
        Просто проверяет, что заявка существует и имеет статус 'paid'.
        """
        order = await self.db.get_order(order_id)
        if not order or order.status != 'paid':
            return False
        return True

    async def complete_order_with_tx_hash(
        self,
        order_id: int,
        tx_hash: str,
        admin_id: int
    ) -> bool:
        """
        Завершение заявки после ввода хеша транзакции (ручной режим).
        Сохраняет хеш, меняет статус на 'completed' и записывает комиссию.
        """
        order = await self.db.get_order(order_id)
        if not order:
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
        return True

    async def reject_order(self, order_id: int, admin_id: int) -> bool:
        """Отклонение заявки (статус 'cancelled')."""
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
        """
        Запросить чек у пользователя (отправить напоминание).
        Возвращает True, если заявка существует (фактическая отправка происходит в хендлере).
        """
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
        """
        Сохраняет введённые админом платёжные реквизиты для ручного режима.
        Сама отправка сообщения пользователю происходит в payment_service.
        """
        await self.db.set_order_manual_payment_details(order_id, details)
        return True