# bot/admin/rates.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.main import is_admin
from bot.admin.states import AdminStates
from bot.services.db import db

logger = logging.getLogger(__name__)
router = Router()

# Список курсов, которые мы будем настраивать
RATES = {
    'rate_usdt_buy': '💵 USDT (Покупка)',
    'rate_usdt_sell': '💵 USDT (Продажа)',
    'rate_trx_buy': '⚡ TRX (Покупка)',
    'rate_trx_sell': '⚡ TRX (Продажа)',
    'rate_btc_buy': '₿ BTC (Покупка)',
    'rate_btc_sell': '₿ BTC (Продажа)',
    'rate_ltc_buy': 'Ł LTC (Покупка)',
    'rate_ltc_sell': 'Ł LTC (Продажа)'
}


def _fmt_rate(val) -> str:
    """Форматирует курс: 95.0 → '95', 92.50 → '92.5'. Не-число — как есть."""
    try:
        f = float(val)
        return str(int(f)) if f == int(f) else str(f)
    except (ValueError, TypeError):
        return str(val)


async def get_rates_menu_keyboard():
    kb = InlineKeyboardBuilder()
    for key, name in RATES.items():
        val = await db.get_setting(key, "0")
        kb.button(
            text=f"{name}: {_fmt_rate(val)} ₽",
            callback_data=f"admin_edit_rate_{key}",
        )

    kb.button(text="🔙 Назад в админку", callback_data="admin_back_main")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "admin_rates_menu")
async def admin_rates_menu(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # Сбрасываем FSM, чтобы пользователь не остался в waiting_for_new_rate
    # (например, если сюда пришли по кнопке «❌ Отмена»)
    await state.clear()

    kb_markup = await get_rates_menu_keyboard()
    await callback.message.edit_text(
        "⚙️ <b>Управление курсами (Обмен)</b>\n\n"
        "Здесь вы можете настроить курсы для режима «Обмен».\n"
        "Нажмите на любую кнопку, чтобы изменить значение:",
        reply_markup=kb_markup,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_rate_"))
async def admin_edit_rate_start(callback: CallbackQuery, state: FSMContext):
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    rate_key = callback.data.replace("admin_edit_rate_", "")
    rate_name = RATES.get(rate_key, rate_key)
    current_val = await db.get_setting(rate_key, "0")

    await state.update_data(editing_rate_key=rate_key, editing_rate_name=rate_name)
    await state.set_state(AdminStates.waiting_for_new_rate)

    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_rates_menu")

    await callback.message.edit_text(
        f"✏️ <b>Изменение курса:</b> {rate_name}\n\n"
        f"Текущее значение: <b>{_fmt_rate(current_val)} ₽</b>\n\n"
        f"Введите новое значение (только цифры, можно с точкой):",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_new_rate)
async def admin_edit_rate_finish(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if not await is_admin(admin_id):
        return

    # Защита от не-текстовых сообщений (фото, стикеры, гифки и т.п.):
    # иначе .replace() упадёт с AttributeError.
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте число текстом (например, 95 или 92.5).\n"
            "Для отмены введите /cancel."
        )
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Изменение курса отменено.")
        kb_markup = await get_rates_menu_keyboard()
        await message.answer(
            "⚙️ <b>Управление курсами (Обмен)</b>\n\n"
            "Выберите курс для изменения:",
            reply_markup=kb_markup,
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    rate_key = data.get('editing_rate_key')
    rate_name = data.get('editing_rate_name')

    if not rate_key:
        await message.answer("❌ Ошибка: не найден ключ курса. Вернитесь в меню.")
        await state.clear()
        return

    try:
        new_val = float(message.text.replace(",", ".").strip())
        if new_val <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите корректное положительное число (например, 95 или 92.5):"
        )
        return

    # Сохраняем «чистую» строку: 95.0 → "95", 92.5 → "92.5"
    save_value = str(int(new_val)) if new_val == int(new_val) else str(new_val)
    # updated_by — для аудита, кто менял курс
    await db.set_setting(rate_key, save_value, updated_by=admin_id)

    logger.info(
        f"[ADMIN {admin_id}] Курс {rate_key} обновлён на {save_value} ₽"
    )

    await message.answer(
        f"✅ Курс <b>{rate_name}</b> успешно обновлён на <b>{save_value} ₽</b>!",
        parse_mode="HTML",
    )
    await state.clear()

    # Снова показываем меню курсов
    kb_markup = await get_rates_menu_keyboard()
    await message.answer(
        "⚙️ <b>Управление курсами (Обмен)</b>\n\nВыберите курс для изменения:",
        reply_markup=kb_markup,
        parse_mode="HTML",
    )