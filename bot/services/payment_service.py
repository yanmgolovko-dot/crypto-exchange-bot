"""Сервис для работы с оплатой и чеками"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import Database
from bot.config.settings import config
from bot.keyboards import admin_order_keyboard, receipt_keyboard

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: Database):
        self.db = db

    async def save_receipt(self, order_id: int, file_path: str) -> bool:
        """Сохраняет путь к чеку в заявке и меняет статус на paid"""
        await self.db.add_bank_receipt(order_id, file_path)
        await self.db.update_order_status(order_id, "paid")
        return True

    async def notify_admins_about_receipt(
        self,
        bot: Bot,
        order_id: int,
        user_id: int,
        username: Optional[str],
        amount_rub: float,
        amount_crypto: float,
        crypto_type: str,
        crypto_address: str,
        file_path: str
    ) -> None:
        """Отправляет уведомление админам с чеком и клавиатурой"""
        safe_username = username if username else 'N/A'
        safe_address = crypto_address

        caption = (
            f"📎 <b>Получен PDF-чек по заявке #{order_id}!</b>\n\n"
            f"Пользователь: @{safe_username} (ID: {user_id})\n"
            f"Сумма к оплате: {amount_rub:,.0f} ₽\n"
            f"Кошелек: <code>{safe_address}</code>\n"
            f"Количество: <code>{amount_crypto:.8f} {crypto_type}</code>\n\n"
            f"Проверьте оплату и подтвердите заявку."
        )

        for admin_id in config.ADMIN_IDS:
            for attempt in range(3):
                try:
                    await bot.send_document(
                        admin_id,
                        FSInputFile(file_path),
                        caption=caption,
                        reply_markup=admin_order_keyboard(order_id),
                        parse_mode="HTML"
                    )
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"Не удалось отправить чек админу {admin_id} после 3 попыток: {e}")
                    else:
                        await asyncio.sleep(2)

    async def get_bank_details_for_order(self, payment_mode: str, payment_source: str) -> Dict[str, Any]:
        """
        Возвращает реквизиты для оплаты в зависимости от режима и источника.
        Возвращает словарь с текстом и флагом, нужно ли ожидать ввода админа.
        """
        if payment_mode == 'auto' or (payment_mode == 'manual' and payment_source == 'auto'):
            details = await self.db.get_bank_details()
            if not details:
                return {'success': False, 'error': 'Нет доступных реквизитов'}
            return {
                'success': True,
                'auto': True,
                'bank_name': details.bank_name,
                'card_number': details.card_number,
                'holder_name': details.holder_name
            }
        else:
            # Ручной ввод реквизитов админом
            return {
                'success': True,
                'auto': False,
                'message': 'Ожидайте, администратор отправит реквизиты.'
            }

    async def process_manual_payment_details(
        self,
        order_id: int,
        details: str,
        user_id: int,
        username: Optional[str],
        bot: Bot
    ) -> bool:
        """Отправляет введённые админом реквизиты пользователю"""
        await self.db.set_order_manual_payment_details(order_id, details)

        try:
            await bot.send_message(
                user_id,
                f"💳 <b>Реквизиты для оплаты заявки #{order_id}</b>\n\n"
                f"{details}\n\n"
                f"После оплаты нажмите кнопку ниже, чтобы прикрепить чек.",
                reply_markup=receipt_keyboard(order_id),
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки реквизитов пользователю {user_id}: {e}")
            return False

    # ==================== НОВЫЙ МЕТОД ДЛЯ НАПОМИНАНИЙ С ДЕТАЛЯМИ ЗАЯВКИ ====================

    async def send_payment_reminder(self, bot: Bot, order, user_id: int) -> bool:
        """
        Отправляет напоминание об оплате пользователю с деталями заявки и кнопкой для загрузки чека.
        order - объект заявки (Order), содержащий все необходимые поля.
        """
        try:
            safe_address = order.crypto_address
            text = (
                f"⏰ <b>Напоминание об оплате</b>\n\n"
                f"📋 <b>Заявка #{order.id}</b>\n"
                f"Криптовалюта: {order.crypto_type}\n"
                f"Сумма к оплате: {order.amount_rub:,.0f} ₽\n"
                f"Вы получите: {order.amount_crypto:.8f} {order.crypto_type}\n"
                f"Кошелёк: <code>{safe_address}</code>\n\n"
                f"Вы создали заявку, но ещё не оплатили её.\n"
                f"Пожалуйста, выполните перевод и загрузите чек, чтобы получить криптовалюту.\n\n"
                f"Если у вас возникли вопросы, обратитесь в поддержку."
            )
            # Используем receipt_keyboard, которая уже содержит кнопки "Прикрепить чек" и "Отменить заявку"
            await bot.send_message(
                user_id,
                text,
                reply_markup=receipt_keyboard(order.id),
                parse_mode="HTML"
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")
            return False