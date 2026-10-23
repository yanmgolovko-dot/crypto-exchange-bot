# bot/admin/spin.py
import logging
import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.main import is_admin
from bot.services.db import db

logger = logging.getLogger(__name__)
router = Router()

class SpinAdminStates(StatesGroup):
    waiting_for_threshold = State()
    waiting_for_prizes_json = State()


@router.callback_query(F.data == "admin_spin_menu")
async def admin_spin_menu(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    threshold = await db.get_setting('spin_threshold', '5')
    prizes_json = await db.get_setting('spin_prizes', '[]')
    
    try:
        prizes = json.loads(prizes_json)
        prizes_text = "\n".join([f"  • {p['min']}-{p['max']}: {p['text']}" for p in prizes])
    except:
        prizes_text = "  ⚠️ Ошибка в JSON"

    text = (
        f"🎰 <b>Настройки Колеса Фортуны</b>\n\n"
        f"<b>Билет за обмены:</b> каждые {threshold} успешных обменов\n\n"
        f"<b>Текущие призы (выпадение от 1 до 64):</b>\n"
        f"<code>{prizes_text}</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить порог обменов", callback_data="admin_spin_set_threshold")
    kb.button(text="📝 Изменить JSON призов", callback_data="admin_spin_set_json")
    kb.button(text="🔙 Назад", callback_data="admin_back_main")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_spin_set_threshold")
async def spin_set_threshold_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await state.set_state(SpinAdminStates.waiting_for_threshold)
    await callback.message.answer("Введите число (за сколько обменов давать 1 билет). Например: <code>5</code>", parse_mode="HTML")
    await callback.answer()

@router.message(SpinAdminStates.waiting_for_threshold)
async def spin_set_threshold_finish(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    try:
        val = int(message.text.strip())
        if val < 1: raise ValueError
    except ValueError:
        await message.answer("❌ Введите целое число больше 0:")
        return

    await db.set_setting('spin_threshold', str(val))
    await message.answer(f"✅ Теперь билет дается за каждые {val} обменов.")
    await state.clear()


@router.callback_query(F.data == "admin_spin_set_json")
async def spin_set_json_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    await state.set_state(SpinAdminStates.waiting_for_prizes_json)
    example = '[{"min": 1, "max": 30, "type": "nothing", "text": "Пусто"}, ...]'
    await callback.message.answer(
        f"Отправьте новый JSON с призами.\n"
        f"Формат:\n<code>{example}</code>\n\n"
        f"Типы: <code>nothing</code>, <code>coupon</code> (value = % скидки), <code>balance</code> (value = рубли)",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(SpinAdminStates.waiting_for_prizes_json)
async def spin_set_json_finish(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    try:
        data = json.loads(message.text.strip())
        if not isinstance(data, list): raise ValueError("Должен быть массив")
        for item in data:
            if not all(k in item for k in ['min', 'max', 'type', 'text']):
                raise ValueError("Не хватает ключей")
    except Exception as e:
        await message.answer(f"❌ Ошибка JSON: {e}. Попробуйте еще раз.")
        return

    await db.set_setting('spin_prizes', json.dumps(data, ensure_ascii=False))
    await message.answer("✅ JSON призов обновлен!")
    await state.clear()