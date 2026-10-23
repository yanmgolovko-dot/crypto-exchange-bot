# bot/handlers/start.py
"""Обработчик команды /start и регистрации пользователя."""

import logging
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.user_service import UserService
from bot.services.coupon_service import coupon_service
from bot.services.partner_service import partner_service
from bot.keyboards import main_menu_keyboard, exchange_menu_keyboard, exchange_crypto_select_keyboard
from bot.services.db import db
from bot.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router()

_LEGACY_REF_RE = re.compile(r"^ref(\d+)$", re.IGNORECASE)


def get_mode_selection_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Шоп", callback_data="mode_shop")
    builder.button(text="🔄 Обмен", callback_data="mode_exchange")
    builder.adjust(2)
    return builder.as_markup()


async def _resolve_referrer(payload: str):
    """
    Возвращает user_id реферера по полезной нагрузке /start.
    Сначала пробует найти пользователя по реферальному коду (vanity),
    затем — legacy-формат ref{user_id}.
    """
    if not payload:
        return None

    # 1) Vanity code (REF12345 или ILYA или любой кастомный)
    referrer = await db.get_user_by_referral_code(payload)
    if referrer:
        return referrer.user_id

    # 2) Legacy ref{user_id}
    m = _LEGACY_REF_RE.match(payload)
    if m:
        return int(m.group(1))

    return None


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_service: UserService):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    logger.info(f"[{user_id}] Пользователь запустил бота командой /start")

    await state.clear()

    args = message.text.split()
    referred_by = None
    if len(args) > 1:
        try:
            referred_by = await _resolve_referrer(args[1])
        except Exception as e:
            logger.warning(f"[{user_id}] Ошибка парсинга реф. параметра: {e}")

    try:
        await user_service.register_or_update(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=message.from_user.last_name,
            referred_by=referred_by
        )
        await coupon_service.give_welcome_coupon(user_id)

        if referred_by:
            partner = await db.partners.get_partner(referred_by)
            if partner and partner.is_active:
                await partner_service.build_referral_tree(user_id, referred_by)
    except Exception as e:
        logger.error(f"[{user_id}] Ошибка при регистрации пользователя: {e}", exc_info=True)

    welcome_text = (
        f"👋 Привет, {escape_html(first_name)}!\n\n"
        f"Добро пожаловать в наш сервис!\n\n"
        f"Пожалуйста, выберите, что вы хотите сделать:\n"
        f"🛒 <b>Шоп</b> — быстрая покупка криптовалюты на холодный кошелёк (BTC, LTC)\n"
        f"🔄 <b>Обмен</b> — P2P обмен с выводом на биржу (USDT, TRX, BTC, LTC)"
    )

    await message.answer(welcome_text, reply_markup=get_mode_selection_keyboard(), parse_mode="HTML")
    logger.info(f"[{user_id}] Отправлено приветственное сообщение с выбором режима")


@router.callback_query(F.data == "mode_shop")
async def select_shop_mode(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "Вы в режиме 🛒 <b>Шоп</b>.\n\nВыберите действие в меню ниже 👇",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "mode_exchange")
async def select_exchange_mode(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "Вы в режиме 🔄 <b>Обмен</b>.\n\n"
        "Здесь вы можете купить или продать популярные монеты через официальную биржу.\n"
        "Выберите действие в меню ниже 👇",
        reply_markup=exchange_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.text == "🔄 Сменить режим")
async def change_mode_handler(message: Message):
    text = (
        "Выберите нужный режим:\n\n"
        "🛒 <b>Шоп</b> — покупка криптовалюты (BTC, LTC)\n"
        "🔄 <b>Обмен</b> — покупка/продажа на биржу (USDT, TRX, BTC, LTC)"
    )
    await message.answer(text, reply_markup=get_mode_selection_keyboard(), parse_mode="HTML")


@router.message(F.text == "🔴 Купить (Обмен)")
async def exchange_buy_start(message: Message):
    await message.answer(
        "Выберите валюту, которую хотите <b>купить</b>:",
        reply_markup=exchange_crypto_select_keyboard("buy"),
        parse_mode="HTML"
    )


@router.message(F.text == "🟢 Продать (Обмен)")
async def exchange_sell_start(message: Message):
    await message.answer(
        "Выберите валюту, которую хотите <b>продать</b>:",
        reply_markup=exchange_crypto_select_keyboard("sell"),
        parse_mode="HTML"
    )