"""Обработчик команды /start и регистрации"""

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.services.user_service import UserService
from bot.keyboards import main_menu_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_service: UserService):
    await state.clear()

    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referred_by = int(args[1][3:])
        except ValueError:
            pass

    await user_service.register_or_update(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        referred_by=referred_by
    )

    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Добро пожаловать в крипто-обменник!\n\n"
        f"Здесь вы можете быстро и безопасно купить:\n"
        f"• ₿ Bitcoin (BTC)\n"
        f"• Ł Litecoin (LTC)\n\n"
        f"⏱ Среднее время обработки: 5-15 минут\n\n"
        f"Выберите действие в меню ниже 👇"
    )

    await message.answer(welcome_text, reply_markup=main_menu_keyboard())