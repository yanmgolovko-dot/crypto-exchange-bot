# bot/handlers/common.py
"""
Общие обработчики для кнопок "Назад", игнорирования и т.д.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_keyboard, currency_choice_keyboard, crypto_select_keyboard
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """
    Возвращает пользователя в главное меню (из любого места).
    Очищает состояние FSM.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Нажата кнопка 'Назад в главное меню'")

    await state.clear()
    logger.debug(f"[{user_id}] Состояние FSM очищено")

    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    logger.debug(f"[{user_id}] Отправлено главное меню")
    await callback.answer()


@router.callback_query(F.data == "back_to_crypto")
async def back_to_crypto(callback: CallbackQuery, state: FSMContext):
    """
    Возвращает пользователя к выбору криптовалюты (с предыдущего шага).
    Очищает состояние и показывает актуальные курсы.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Нажата кнопка 'Назад к выбору криптовалюты'")

    await state.set_state(None)
    logger.debug(f"[{user_id}] Состояние сброшено")

    try:
        prices = await crypto_api.get_all_prices()
        logger.debug(f"[{user_id}] Получены курсы: BTC={prices['BTC']}, LTC={prices['LTC']}")
    except Exception as e:
        logger.error(f"[{user_id}] Ошибка получения курсов: {e}", exc_info=True)
        prices = {"BTC": None, "LTC": None}

    rates_text = "📊 Актуальные курсы:\n"
    if prices["BTC"]:
        rates_text += f"• ₿ BTC: {prices['BTC']:,.0f} ₽\n"
    if prices["LTC"]:
        rates_text += f"• Ł LTC: {prices['LTC']:,.0f} ₽\n"
    rates_text += "\nВыберите криптовалюту для покупки:"

    await callback.message.edit_text(rates_text, reply_markup=crypto_select_keyboard())
    logger.debug(f"[{user_id}] Отображён экран выбора криптовалюты")
    await callback.answer()


@router.callback_query(F.data == "back_to_currency")
async def back_to_currency(callback: CallbackQuery, state: FSMContext):
    """
    Возвращает пользователя к выбору валюты ввода (рубли/крипта).
    Использует данные из состояния.
    """
    user_id = callback.from_user.id
    logger.info(f"[{user_id}] Нажата кнопка 'Назад к выбору валюты'")

    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    logger.debug(f"[{user_id}] Тип криптовалюты из состояния: {crypto_type}")

    if not crypto_type:
        logger.warning(f"[{user_id}] Не найден crypto_type в состоянии, возврат в главное меню")
        await back_to_main(callback, state)
        return

    await state.set_state(None)
    text = f"Выберите, в чём вы хотите ввести сумму для {crypto_type}:"
    await callback.message.edit_text(text, reply_markup=currency_choice_keyboard(crypto_type))
    logger.debug(f"[{user_id}] Отображён экран выбора валюты")
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    """
    Обработчик для кнопок, которые не должны ничего делать (заглушка).
    Просто отвечает на callback, чтобы убрать "часики".
    """
    user_id = callback.from_user.id
    logger.debug(f"[{user_id}] Получен callback с ignore (игнорируется)")
    await callback.answer()