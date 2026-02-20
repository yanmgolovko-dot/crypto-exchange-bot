"""Общие обработчики (назад, отмена и т.д.)"""

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_keyboard, currency_choice_keyboard, crypto_select_keyboard
from bot.services.crypto_api import crypto_api

router = Router()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_crypto")
async def back_to_crypto(callback: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    prices = await crypto_api.get_all_prices()
    rates_text = "📊 Актуальные курсы:\n"
    if prices["BTC"]:
        rates_text += f"• ₿ BTC: {prices['BTC']:,.0f} ₽\n"
    if prices["LTC"]:
        rates_text += f"• Ł LTC: {prices['LTC']:,.0f} ₽\n"
    rates_text += "\nВыберите криптовалюту для покупки:"
    await callback.message.edit_text(rates_text, reply_markup=crypto_select_keyboard())
    await callback.answer()

@router.callback_query(F.data == "back_to_currency")
async def back_to_currency(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    crypto_type = data.get('crypto_type')
    await state.set_state(None)
    text = f"Выберите, в чём вы хотите ввести сумму для {crypto_type}:"
    await callback.message.edit_text(text, reply_markup=currency_choice_keyboard(crypto_type))
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: CallbackQuery):
    await callback.answer()