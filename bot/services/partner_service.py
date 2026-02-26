# bot/services/partner_service.py
import logging
import random
import string
from typing import Optional, List, Dict, Any, Tuple

from bot.services.db import db
from bot.services.db.partner_repository import PartnerSettings
from bot.services.db.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


class PartnerService:
    """Бизнес-логика для партнёрской программы."""

    async def generate_referral_code(self, user_id: int) -> str:
        """Генерирует уникальный реферальный код для пользователя."""
        # Простой генератор: можно улучшить
        code = f"REF{user_id}"
        # Проверим уникальность
        existing = await db.partners.get_partner(user_id)
        if existing and existing.referral_code:
            return existing.referral_code
        return code

    async def add_partner(self, user_id: int, referral_code: str = None) -> bool:
        """Добавляет пользователя в партнёры."""
        if not referral_code:
            referral_code = await self.generate_referral_code(user_id)
        return await db.partners.add_partner(user_id, referral_code)

    async def build_referral_tree(self, new_user_id: int, referrer_id: int):
        """
        При регистрации нового пользователя по ссылке партнёра строит все уровни вверх.
        """
        settings = await db.partners.get_settings()
        max_levels = settings.max_levels

        # Рекурсивно или циклом поднимаемся вверх до максимального уровня
        current_referrer = referrer_id
        level = 1
        while level <= max_levels and current_referrer:
            # Проверяем, что реферер является активным партнёром
            partner = await db.partners.get_partner(current_referrer)
            if partner and partner.is_active:
                await db.partners.add_referral_link(current_referrer, new_user_id, level)
            # Переходим выше
            # Для этого нужно знать, кто пригласил текущего реферера. Ищем в referral_tree записи, где referred_id = current_referrer и уровень минимальный.
            # Упростим: будем хранить в users поле referred_by, но для многоуровневости нужно дерево. Поэтому в этом методе мы будем использовать referred_by из users.
            # В users есть поле referred_by. Будем подниматься по нему.
            user = await db.get_user(current_referrer)
            current_referrer = user.referred_by if user else None
            level += 1

    async def process_order_reward(self, order):
        """
        Начисляет вознаграждения партнёрам после завершения заказа.
        Вызывается из admin_order_service после коммита.
        """
        settings = await db.partners.get_settings()
        if not settings.enabled:
            return

        # Определяем базу для начисления (комиссия или сумма заказа)
        if settings.commission_source == 'fee':
            base_amount = order.amount_rub * order.fee_percent / 100
        else:
            base_amount = order.amount_rub

        # Получаем всех рефереров до max_levels
        referrers = await db.partners.get_referrers_chain(order.user_id, settings.max_levels)

        async with db.uow() as uow:
            for referrer_id, level in referrers:
                # Проверяем, что реферер активный партнёр
                partner = await uow.partners.get_partner(referrer_id)
                if not partner or not partner.is_active:
                    continue

                # Находим настройку для этого уровня
                reward_config = next((r for r in settings.level_rewards if r['level'] == level), None)
                if not reward_config:
                    continue

                # Вычисляем сумму вознаграждения
                if reward_config['type'] == 'fixed':
                    reward = reward_config['value']
                else:  # percent
                    reward = base_amount * reward_config['value'] / 100

                if reward <= 0:
                    continue

                # Начисляем
                await uow.partners.update_partner_balance(referrer_id, reward)
                # Записываем в referral_earnings
                await uow.finance.add_financial_record(
                    record_type='expense',
                    category='referral_payment',
                    amount=reward,
                    description=f'Начисление партнёру за заказ #{order.id}, уровень {level}',
                    order_id=order.id,
                    created_by=None
                )
                # Также можно сохранить в отдельной таблице referral_earnings, но у нас уже есть финансовая запись.
                # Для статистики партнёра можно добавить отдельную таблицу, но пока достаточно.

            await uow.commit()

    async def request_withdraw(
        self,
        user_id: int,
        amount: float,
        payment_method: str,
        payment_details: str
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Создаёт заявку на вывод. Проверяет минимальную сумму и баланс.
        Возвращает (успех, сообщение, id заявки)
        """
        settings = await db.partners.get_settings()
        if amount < settings.min_withdraw:
            return False, f"Минимальная сумма вывода: {settings.min_withdraw} ₽", None

        partner = await db.partners.get_partner(user_id)
        if not partner or partner.balance < amount:
            return False, "Недостаточно средств на балансе", None

        # Создаём заявку
        request_id = await db.partners.create_withdraw_request(
            user_id, amount, payment_method, payment_details
        )
        return True, "Заявка создана, ожидайте подтверждения администратора", request_id

    async def approve_withdraw(self, request_id: int, admin_id: int) -> Tuple[bool, str]:
        """
        Одобряет вывод: списывает сумму с баланса партнёра и помечает заявку как approved.
        """
        request = await db.partners.get_withdraw_request(request_id)
        if not request or request.status != 'pending':
            return False, "Заявка не найдена или уже обработана"

        partner = await db.partners.get_partner(request.user_id)
        if not partner or partner.balance < request.amount:
            return False, "Недостаточно средств на балансе (возможно, баланс изменился)"

        async with db.uow() as uow:
            # Списываем баланс
            new_balance = partner.balance - request.amount
            await uow.partners.set_partner_balance(request.user_id, new_balance)
            # Одобряем заявку
            await uow.partners.approve_withdraw_request(request_id, admin_id)
            await uow.commit()

        return True, "Вывод одобрен"

    async def reject_withdraw(self, request_id: int, admin_id: int, comment: str) -> bool:
        return await db.partners.reject_withdraw_request(request_id, admin_id, comment)

    async def get_partner_stats(self, user_id: int) -> Dict[str, Any]:
        """Возвращает статистику для партнёра."""
        partner = await db.partners.get_partner(user_id)
        if not partner:
            return {}
        # Количество рефералов по уровням
        stats = {
            'balance': partner.balance,
            'total_earned': partner.total_earned,
            'referrals': {}
        }
        settings = await db.partners.get_settings()
        for level in range(1, settings.max_levels + 1):
            count = await db.partners.get_downline_count(user_id, level)
            stats['referrals'][f'level_{level}'] = count
        return stats


partner_service = PartnerService()