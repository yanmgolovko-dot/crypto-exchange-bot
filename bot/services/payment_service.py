# bot/services/payment_service.py
"""Сервис для работы с оплатой и чеками."""

import os
import logging
import asyncio
from typing import Optional, Dict, Any

from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import Database
from bot.config.settings import config
from bot.keyboards import receipt_received_keyboard, receipt_keyboard

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Сервис для обработки платежей:
    - сохранение чеков
    - уведомление администраторов о новых чеках
    - получение банковских реквизитов
    - отправка реквизитов пользователю (ручной режим)
    - отправка напоминаний об оплате
    """

    def __init__(self, db: Database):
        self.db = db

    async def save_receipt(self, order_id: int, file_path: str) -> bool:
        """
        Идемпотентно сохраняет путь к чеку и переводит заявку в 'paid'.

        - Если заявка не найдена — False.
        - Если статус заявки не 'pending' (уже paid/processing/completed/...) —
          чек не перезаписываем, False.
        - Иначе атомарно: добавляем путь и меняем статус с expected_status='pending'.
          Если гонка (статус уже сменился) — False.

        :return: True только если чек принят впервые.
        """
        order = await self.db.orders.get_order(order_id)
        if order is None:
            logger.warning("save_receipt: заявка #%s не найдена", order_id)
            return False

        if order.status != "pending":
            logger.info(
                "save_receipt: заявка #%s уже в статусе '%s' — повторный чек не принимаем",
                order_id, order.status,
            )
            return False

        logger.info("Сохранение чека для заявки #%s, путь: %s", order_id, file_path)
        await self.db.orders.add_bank_receipt(order_id, file_path)

        ok = await self.db.orders.update_order_status(
            order_id, "paid", expected_status="pending"
        )
        if not ok:
            logger.warning(
                "save_receipt: не удалось перевести заявку #%s в 'paid' "
                "(статус изменился параллельно)", order_id,
            )
            return False

        logger.info("Статус заявки #%s изменён на paid", order_id)
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
        """
        Отправляет уведомление всем администраторам о получении чека.
        К сообщению прикрепляется сам чек и клавиатура для подтверждения/отклонения.
        """
        logger.info(f"Уведомление администраторов о получении чека по заявке #{order_id}")
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
            for attempt in range(3):  # до 3 попыток при ошибке
                try:
                    await bot.send_document(
                        admin_id,
                        FSInputFile(file_path),
                        caption=caption,
                        reply_markup=receipt_received_keyboard(order_id),
                        parse_mode="HTML"
                    )
                    logger.info(f"Чек отправлен админу {admin_id}")
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"Не удалось отправить чек админу {admin_id} после 3 попыток: {e}")
                    else:
                        await asyncio.sleep(2)

    async def get_bank_details_for_order(self, payment_mode: str, payment_source: str) -> Dict[str, Any]:
        """
        Возвращает реквизиты для оплаты в зависимости от режима и источника.
        :param payment_mode: 'auto' или 'manual' (глобальный режим оплаты)
        :param payment_source: 'auto' или 'manual' (источник реквизитов в ручном режиме)
        :return: словарь с ключами 'success', 'auto' и данными реквизитов или сообщением об ошибке
        """
        logger.debug(f"Получение реквизитов: payment_mode={payment_mode}, payment_source={payment_source}")
        if payment_mode == 'auto' or (payment_mode == 'manual' and payment_source == 'auto'):
            details = await self.db.get_bank_details()
            if not details:
                logger.warning("Нет доступных реквизитов в БД")
                return {'success': False, 'error': 'Нет доступных реквизитов'}
            logger.debug(f"Найдены реквизиты: банк {details.bank_name}, карта {details.card_number[:4]}...")
            return {
                'success': True,
                'auto': True,
                'bank_name': details.bank_name,
                'card_number': details.card_number,
                'holder_name': details.holder_name
            }
        else:
            logger.debug("Ручной режим с вводом реквизитов администратором")
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
        """
        Отправляет введённые администратором реквизиты пользователю.
        :param order_id: ID заявки
        :param details: текст реквизитов
        :param user_id: ID пользователя
        :param username: username пользователя (для логов)
        :param bot: объект бота
        :return: True, если сообщение отправлено успешно
        """
        logger.info(f"Отправка введённых реквизитов пользователю {user_id} по заявке #{order_id}")
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
            logger.info(f"Реквизиты успешно отправлены пользователю {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки реквизитов пользователю {user_id}: {e}")
            return False

    async def send_payment_reminder(self, bot: Bot, order, user_id: int) -> bool:
        """
        Отправляет пользователю напоминание об оплате с деталями заявки и кнопкой для загрузки чека.
        :param bot: объект бота
        :param order: объект заявки (Order)
        :param user_id: ID пользователя
        :return: True, если сообщение отправлено успешно
        """
        logger.info(f"Отправка напоминания об оплате пользователю {user_id} по заявке #{order.id}")
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
            await bot.send_message(
                user_id,
                text,
                reply_markup=receipt_keyboard(order.id),
                parse_mode="HTML"
            )
            logger.info(f"Напоминание отправлено пользователю {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")
            return False