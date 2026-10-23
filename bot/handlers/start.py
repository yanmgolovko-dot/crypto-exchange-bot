# bot/handlers/start.py
"""
Обработчик команды /start и регистрации пользователя.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.user_service import UserService
from bot.services.coupon_service import coupon_service
from bot.services.partner_service import partner_service
from bot.keyboards import main_menu_keyboard, exchange_menu_keyboard
from bot.services.db import db
from bot.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router()


def get_mode_selection_keyboard():
    """Создает инлайн-клавиатуру для выбора режима."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Шоп", callback_data="mode_shop")
    builder.button(text="🔄 Обмен", callback_data="mode_exchange")
    builder.adjust(2)
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_service: UserService):
    """
    Обработчик команды /start.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    logger.info(f"[{user_id}] Пользователь запустил бота командой /start")

    await state.clear()

    # Разбираем реферальный параметр
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referred_by = int(args[1][3:])
        except ValueError:
            pass

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
        f"🛒 <b>Шоп</b> — быстрая покупка криптовалюты (BTC, LTC)\n"
        f"🔄 <b>Обмен</b> — P2P обмен (функционал в разработке)"
    )

    await message.answer(welcome_text, reply_markup=get_mode_selection_keyboard(), parse_mode="HTML")
    logger.info(f"[{user_id}] Отправлено приветственное сообщение с выбором режима")


# ==================== ОБРАБОТЧИКИ ВЫБОРА РЕЖИМА ====================

@router.callback_query(F.data == "mode_shop")
async def select_shop_mode(callback: CallbackQuery):
    """Пользователь выбрал режим 'Шоп'."""
    try:
        await callback.message.delete() # Удаляем сообщение с инлайн-кнопками
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
    """Пользователь выбрал режим 'Обмен'."""
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "Вы в режиме 🔄 <b>Обмен</b>.\n\n"
        "Этот раздел находится в разработке. Скоро здесь появится функционал P2P обмена!",
        reply_markup=exchange_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

# ==================== КНОПКА СМЕНЫ РЕЖИМА ====================

@router.message(F.text == "🔄 Сменить режим")
async def change_mode_handler(message: Message):
    """Обработчик нажатия на текстовую кнопку смены режима."""
    text = (
        "Выберите нужный режим:\n\n"
        "🛒 <b>Шоп</b> — покупка криптовалюты\n"
        "🔄 <b>Обмен</b> — P2P обмен (в разработке)"
    )
    await message.answer(text, reply_markup=get_mode_selection_keyboard(), parse_mode="HTML")


# Заглушка для кнопки внутри режима Обмен, чтобы бот не молчал
@router.message(F.text == "🔄 Обмен (в разработке)")
async def exchange_placeholder(message: Message):
    await message.answer("🛠 Раздел Обмен еще в разработке. Мы работаем над этим!")