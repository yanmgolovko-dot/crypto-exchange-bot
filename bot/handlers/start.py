# bot/handlers/start.py
"""
Обработчик команды /start и регистрации пользователя.
При запуске бота пользователь добавляется или обновляется в базе данных,
обрабатывается реферальная ссылка (если есть), и отображается приветственное сообщение.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.services.user_service import UserService
from bot.services.coupon_service import coupon_service
from bot.services.partner_service import partner_service
from bot.keyboards import main_menu_keyboard
from bot.services.db import db
from bot.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_service: UserService):
    """
    Обработчик команды /start.
    Выполняет:
    - очистку состояния FSM
    - извлечение реферального параметра (если есть)
    - регистрацию или обновление пользователя в БД
    - построение реферального дерева, если реферер – партнёр
    - отправку приветственного сообщения с главным меню
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    logger.info(f"[{user_id}] Пользователь запустил бота командой /start")

    await state.clear()
    logger.debug(f"[{user_id}] Состояние FSM очищено")

    # Разбираем реферальный параметр (например, /start ref123456)
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referred_by = int(args[1][3:])
            logger.info(f"[{user_id}] Переход по реферальной ссылке от пользователя {referred_by}")
        except ValueError:
            logger.warning(f"[{user_id}] Некорректный реферальный параметр: {args[1]}")

    try:
        await user_service.register_or_update(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=message.from_user.last_name,
            referred_by=referred_by
        )
        logger.info(f"[{user_id}] Пользователь успешно зарегистрирован/обновлён")

        # Выдаём приветственный купон
        await coupon_service.give_welcome_coupon(user_id)

        # Если реферальная ссылка была от партнёра, строим дерево
        if referred_by:
            partner = await db.partners.get_partner(referred_by)
            if partner and partner.is_active:
                await partner_service.build_referral_tree(user_id, referred_by)
    except Exception as e:
        logger.error(f"[{user_id}] Ошибка при регистрации пользователя: {e}", exc_info=True)

    welcome_text = (
        f"👋 Привет, {escape_html(first_name)}!\n\n"
        f"Добро пожаловать в крипто-обменник!\n\n"
        f"Здесь вы можете быстро и безопасно купить:\n"
        f"• ₿ Bitcoin (BTC)\n"
        f"• Ł Litecoin (LTC)\n\n"
        f"⏱ Среднее время обработки: 5-15 минут\n\n"
        f"Выберите действие в меню ниже 👇"
    )

    await message.answer(welcome_text, reply_markup=main_menu_keyboard(), parse_mode="HTML")
    logger.info(f"[{user_id}] Отправлено приветственное сообщение с главным меню")