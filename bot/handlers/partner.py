# bot/handlers/partner.py
"""Партнёрский кабинет."""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.partner_service import partner_service
from bot.keyboards import main_menu_keyboard
from bot.config.settings import config
from bot.utils.helpers import safe_edit_message, escape_html
from bot.utils.qr_generator import generate_qr_bytes

logger = logging.getLogger(__name__)
router = Router()


class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_method = State()
    waiting_details = State()


def partner_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Моя статистика", callback_data="partner_stats")
    kb.button(text="🔗 Реферальная ссылка", callback_data="partner_link")
    kb.button(text="💰 Запросить вывод", callback_data="partner_withdraw")
    kb.button(text="📜 История выводов", callback_data="partner_withdraw_history")
    kb.button(text="🔙 Назад", callback_data="partner_back")
    kb.adjust(1)
    return kb.as_markup()


async def partner_entry(user_id: int, bot: Bot):
    partner = await db.partners.get_partner(user_id)
    if not partner or not partner.is_active:
        await bot.send_message(user_id, "⛔ У вас нет доступа к партнёрскому кабинету.")
        return
    await bot.send_message(
        user_id,
        "🤝 Добро пожаловать в партнёрский кабинет!",
        reply_markup=partner_keyboard()
    )


@router.message(Command("partner"))
async def cmd_partner(message: Message):
    await partner_entry(message.from_user.id, message.bot)


@router.callback_query(F.data == "partner_stats")
async def partner_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    partner = await db.partners.get_partner(user_id)
    if not partner:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    stats = await partner_service.get_partner_stats(user_id)
    if not stats:
        await callback.answer("Ошибка загрузки статистики", show_alert=True)
        return
    text = (
        f"📊 <b>Ваша статистика</b>\n\n"
        f"💰 Баланс: {stats['balance']:.2f} ₽\n"
        f"🏆 Всего заработано: {stats['total_earned']:.2f} ₽\n"
        f"👥 Рефералы:\n"
    )
    for level, count in stats['referrals'].items():
        text += f"  Уровень {level.split('_')[1]}: {count}\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="partner_back")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== РЕФЕРАЛЬНАЯ ССЫЛКА + QR ====================

@router.callback_query(F.data == "partner_link")
async def partner_link(callback: CallbackQuery):
    user_id = callback.from_user.id
    partner = await db.partners.get_partner(user_id)
    if not partner:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    user = await db.get_user(user_id)
    if not user:
        await callback.answer("⛔ Пользователь не найден", show_alert=True)
        return

    bot_info = await callback.bot.get_me()
    code = user.referral_code or f"REF{user.user_id}"
    link = f"https://t.me/{bot_info.username}?start={code}"

    caption = (
        f"🔗 <b>Ваша партнёрская ссылка</b>\n\n"
        f"<b>Код:</b> <code>{escape_html(code)}</code>\n"
        f"<b>Ссылка:</b>\n<code>{escape_html(link)}</code>\n\n"
        f"📲 Покажите QR-код — новый партнёр попадёт к вам в структуру."
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📤 Поделиться",
        url=f"https://t.me/share/url?url={link}&text=Крипто-обменник с лучшими курсами!"
    )
    kb.button(text="🔙 Назад", callback_data="partner_back")
    kb.adjust(1)

    try:
        await callback.message.delete()
    except Exception:
        pass

    qr_buf = generate_qr_bytes(link)
    if qr_buf:
        photo = BufferedInputFile(qr_buf.read(), filename=f"partner_{user.user_id}.png")
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(
            caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await callback.answer()


@router.callback_query(F.data == "partner_withdraw")
async def partner_withdraw_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    partner = await db.partners.get_partner(user_id)
    if not partner:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    settings = await db.partners.get_settings()
    await state.set_state(WithdrawStates.waiting_amount)
    await safe_edit_message(
        callback.message,
        f"💰 Введите сумму для вывода (мин. {settings.min_withdraw} ₽):"
    )
    await callback.answer()


@router.message(WithdrawStates.waiting_amount)
async def withdraw_amount_received(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return
    await state.update_data(amount=amount)
    await state.set_state(WithdrawStates.waiting_method)
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Банковская карта", callback_data="withdraw_method_card")
    kb.button(text="₿ Bitcoin (BTC)", callback_data="withdraw_method_btc")
    kb.button(text="Ł Litecoin (LTC)", callback_data="withdraw_method_ltc")
    kb.button(text="💵 USDT (TRC20)", callback_data="withdraw_method_usdt")
    kb.button(text="🔙 Отмена", callback_data="withdraw_cancel")
    kb.adjust(1)
    await message.answer("Выберите способ вывода:", reply_markup=kb.as_markup())


@router.callback_query(WithdrawStates.waiting_method)
async def withdraw_method_chosen(callback: CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[-1]
    await state.update_data(method=method)
    await state.set_state(WithdrawStates.waiting_details)
    prompts = {
        'card': "Введите номер карты и банк (например: 1234 5678 9012 3456, Сбербанк)",
        'btc': "Введите ваш Bitcoin-адрес",
        'ltc': "Введите ваш Litecoin-адрес",
        'usdt': "Введите ваш USDT-адрес (сеть TRC20)"
    }
    await safe_edit_message(callback.message, prompts.get(method, "Введите реквизиты:"))
    await callback.answer()


@router.message(WithdrawStates.waiting_details)
async def withdraw_details_received(message: Message, state: FSMContext):
    details = message.text.strip()
    data = await state.get_data()
    amount = data['amount']
    method = data['method']
    user_id = message.from_user.id
    success, msg, request_id = await partner_service.request_withdraw(
        user_id, amount, method, details
    )
    if success:
        await message.answer(
            f"✅ {msg}\n\nВаша заявка будет обработана администратором."
        )
        admin_text = (
            f"💰 <b>Новая заявка на вывод</b>\n"
            f"Партнёр: {escape_html(message.from_user.username or str(user_id))} (ID: {user_id})\n"
            f"Сумма: {amount:.2f} ₽\n"
            f"Способ: {escape_html(method)}\n"
            f"Реквизиты: {escape_html(details)}\n\n"
            f"Обработать: /admin"
        )
        from bot.admin.main import notify_admins
        await notify_admins(message.bot, admin_text)
    else:
        await message.answer(f"❌ {msg}")
    await state.clear()
    await partner_entry(user_id, message.bot)


@router.callback_query(F.data == "withdraw_cancel")
async def withdraw_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await partner_entry(callback.from_user.id, callback.bot)
    await callback.answer()


@router.callback_query(F.data == "partner_withdraw_history")
async def partner_withdraw_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    partner = await db.partners.get_partner(user_id)
    if not partner:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return
    requests = await db.partners.get_user_withdraw_requests(user_id)
    if not requests:
        text = "📜 У вас пока нет заявок на вывод."
    else:
        text = "📜 <b>История выводов</b>\n\n"
        for req in requests:
            status_emoji = {
                'pending': '⏳', 'approved': '✅', 'rejected': '❌'
            }.get(req.status, '❓')
            text += (
                f"{status_emoji} #{req.id} от {req.created_at[:10]}\n"
                f"   Сумма: {req.amount:.2f} ₽, способ: {escape_html(req.payment_method or '')}\n"
                f"   Статус: {req.status}\n"
            )
            if req.admin_comment:
                text += f"   Комментарий: {escape_html(req.admin_comment)}\n"
            text += "\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="partner_back")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "partner_back")
async def partner_back(callback: CallbackQuery):
    await partner_entry(callback.from_user.id, callback.bot)
    await callback.answer()