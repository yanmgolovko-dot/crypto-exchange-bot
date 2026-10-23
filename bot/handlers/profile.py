# bot/handlers/profile.py
"""Обработчики для личного кабинета пользователя."""

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.crypto_api import crypto_api
from bot.services.coupon_service import coupon_service
from bot.services.review_service import review_service
from bot.services.partner_service import partner_service
from bot.keyboards import main_menu_keyboard
from bot.admin.main import is_admin
from bot.utils.helpers import safe_edit_message, escape_html
from bot.utils.qr_generator import generate_qr_bytes

logger = logging.getLogger(__name__)
router = Router()


async def get_user_profile_keyboard(user_id: int):
    kb = InlineKeyboardBuilder()

    kb.button(text="📊 Статистика", callback_data="user_stats")
    kb.button(text="💰 Бонусы", callback_data="user_bonus")

    kb.button(text="📋 Мои заявки", callback_data="user_orders")
    kb.button(text="🎫 Купоны", callback_data="user_my_coupons")

    kb.button(text="🎁 Промокоды", callback_data="user_promos")
    kb.button(text="📝 Отзывы", callback_data="user_my_reviews")

    kb.button(text="🔗 Рефералы", callback_data="user_referral")
    kb.button(text="⚙️ Настройки", callback_data="user_settings")

    partner = await db.partners.get_partner(user_id)
    if partner and partner.is_active:
        kb.button(text="🤝 Партнёрский кабинет", callback_data="user_partner_cabinet")

    if await is_admin(user_id):
        kb.button(text="👑 Админка", callback_data="user_admin_panel")

    kb.button(text="🔙 Главное меню", callback_data="user_back_main")

    layout = [2, 2, 2, 2]
    if partner and partner.is_active:
        layout.append(1)
    if await is_admin(user_id):
        layout.append(1)
    layout.append(1)
    kb.adjust(*layout)

    return kb.as_markup()


def _build_referral_link(bot_username: str, user) -> str:
    code = getattr(user, "referral_code", None) or f"REF{user.user_id}"
    return f"https://t.me/{bot_username}?start={code}"


@router.message(Command("profile"))
@router.message(F.text == "👤 Личный кабинет")
async def cmd_profile(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await db.add_or_update_user(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        user = await db.get_user(user_id)

    is_banned, ban_reason = await db.is_user_banned(user_id)
    if is_banned:
        await message.answer(
            f"🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
            f"Причина: {ban_reason}\n\n"
            f"Для разблокировки обратитесь в поддержку.",
            parse_mode="HTML"
        )
        return

    stats = await db.get_user_stats(user_id)

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"<b>Информация:</b>\n"
        f"   ID: <code>{user.user_id}</code>\n"
        f"   Имя: {escape_html(user.first_name or 'Не указано')}\n"
        f"   Дата регистрации: {user.created_at[:10] if user.created_at else 'N/A'}\n\n"
        f"<b>Статистика:</b>\n"
        f"   Всего обменов: {stats['total_orders']}\n"
        f"   Общий объем: {stats['total_volume']:,.0f} ₽\n"
        f"   Сэкономлено: {stats['total_saved']:,.0f} ₽\n\n"
        f"<b>Бонусы:</b>\n"
        f"   Баланс: {user.bonus_balance:,.0f} ₽\n\n"
    )

    if user.referral_code:
        text += f"<b>Реферальный код:</b> <code>{escape_html(user.referral_code)}</code>\n\n"

    text += "Выберите раздел:"

    kb = await get_user_profile_keyboard(user_id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "user_orders")
async def user_orders(callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = await db.get_user_orders(user_id, limit=10)
    if not orders:
        text = "📋 У вас пока нет заявок."
    else:
        text = "📋 <b>Ваши заявки</b>\n\n"
        for order in orders:
            status_emoji = {
                "pending": "⏳", "paid": "💳", "completed": "✅", "cancelled": "❌"
            }.get(order.status, "❓")
            status_text = {
                "pending": "Ожидает", "paid": "Проверка",
                "completed": "Выполнена", "cancelled": "Отменена"
            }.get(order.status, "Неизв.")
            display_number = order.public_order_number or order.id
            text += (
                f"{status_emoji} <b>#{display_number}</b> | {order.crypto_type}\n"
                f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f}\n"
                f"   {status_text}\n"
                f"   {order.created_at[:10]}\n\n"
            )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="user_back_profile")
    await safe_edit_message(callback.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_partner_cabinet")
async def user_partner_cabinet(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    partner = await db.partners.get_partner(user_id)
    if not partner or not partner.is_active:
        await callback.answer("⛔ У вас нет доступа к партнёрскому кабинету.", show_alert=True)
        return
    from bot.handlers.partner import partner_entry
    await partner_entry(callback.from_user.id, callback.bot)
    await callback.answer()


@router.callback_query(F.data == "user_admin_panel")
async def user_admin_panel(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет доступа к админ-панели.", show_alert=True)
        return
    from bot.admin.main import cmd_admin
    await cmd_admin(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "user_stats")
async def user_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    orders = await db.get_user_orders(user_id, limit=5)

    text = (
        f"📊 <b>Моя статистика</b>\n\n"
        f"<b>Общая информация:</b>\n"
        f"   Всего обменов: {stats['total_orders']}\n"
        f"   Общий объем: {stats['total_volume']:,.0f} ₽\n"
        f"   Сэкономлено на скидках: {stats['total_saved']:,.0f} ₽\n\n"
    )
    if orders:
        text += "<b>Последние заявки:</b>\n"
        for order in orders:
            status_emoji = {
                "pending": "⏳", "paid": "💳", "completed": "✅", "cancelled": "❌"
            }.get(order.status, "❓")
            status_text = {
                "pending": "Ожидает оплаты", "paid": "На проверке",
                "completed": "Выполнена", "cancelled": "Отменена"
            }.get(order.status, "Неизвестно")
            text += (
                f"{status_emoji} <b>#{order.id}</b> | {order.crypto_type}\n"
                f"   {order.amount_rub:,.0f} ₽ → {order.amount_crypto:.8f}\n"
                f"   Статус: {status_text}\n"
                f"   Дата: {order.created_at[:10] if order.created_at else 'N/A'}\n\n"
            )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_bonus")
async def user_bonus(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return
    text = (
        f"💰 <b>Бонусный баланс</b>\n\n"
        f"Текущий баланс: <b>{user.bonus_balance:,.0f} ₽</b>\n\n"
        f"<b>Как заработать бонусы?</b>\n"
        f"• Приглашайте друзей по реферальной ссылке\n"
        f"• Используйте промокоды\n"
        f"• Совершайте обмены\n\n"
        f"<b>Как использовать?</b>\n"
        f"Бонусы автоматически применяются при обмене и уменьшают комиссию."
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔗 Реферальная программа", callback_data="user_referral")
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    keyboard.adjust(1)
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_promos")
async def user_promos(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        all_promos = await db.get_all_promo_codes()
        used_promo_ids = set(await db.get_user_used_promo_ids(user_id))
        now = datetime.now().isoformat()
        available, used = [], []
        for promo in all_promos:
            if not promo.is_active:
                continue
            if promo.valid_to and promo.valid_to < now:
                continue
            if promo.id in used_promo_ids:
                used.append(promo)
            else:
                available.append(promo)

        text = "🎁 <b>Мои промокоды</b>\n\n"
        if available:
            text += "<b>Доступные для использования:</b>\n"
            for promo in available:
                text += f"• <code>{escape_html(promo.code)}</code> — скидка {promo.discount_percent}% (осталось {promo.max_uses - promo.used_count} шт.)\n"
        else:
            text += "У вас нет доступных промокодов.\n"
        if used:
            text += "\n<b>Использованные:</b>\n"
            for promo in used:
                text += f"• {escape_html(promo.code)} — скидка {promo.discount_percent}%\n"
        if not available and not used:
            text = "🎁 <b>Мои промокоды</b>\n\nУ вас пока нет промокодов. Следите за акциями!"
    except Exception as e:
        logger.error(f"[{user_id}] Ошибка при получении промокодов: {e}", exc_info=True)
        text = "❌ Произошла ошибка при загрузке промокодов."
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_my_coupons")
async def user_my_coupons(callback: CallbackQuery):
    user_id = callback.from_user.id
    coupons = await coupon_service.get_user_coupons(user_id)
    if not coupons:
        text = "🎫 <b>Мои купоны</b>\n\nУ вас пока нет доступных купонов."
    else:
        text = "🎫 <b>Мои купоны</b>\n\n"
        for coup in coupons:
            discount_str = f"{coup.discount_value}%" if coup.discount_type == 'percent' else f"{coup.discount_value:,.0f} ₽"
            on_str = "на всю сумму" if coup.discount_on == 'order' else "на комиссию"
            valid_str = "бессрочно" if not coup.valid_to else f"до {coup.valid_to[:10]}"
            text += (
                f"• <b>{escape_html(coup.code)}</b>\n"
                f"  Скидка: {discount_str} {on_str}\n"
                f"  {escape_html(coup.description or '—')}\n"
                f"  Действует: {valid_str}\n\n"
            )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_my_reviews")
async def user_my_reviews(callback: CallbackQuery):
    user_id = callback.from_user.id
    reviews = await review_service.get_user_reviews(user_id)
    if not reviews:
        text = "📝 У вас пока нет отзывов."
    else:
        text = "📝 <b>Мои отзывы</b>\n\n"
        for rev in reviews:
            status = "✅ Опубликован" if rev.is_approved else "⏳ На модерации"
            rating_stars = "⭐" * rev.rating + "☆" * (5 - rev.rating)
            text += f"Заявка #{rev.order_id} {rating_stars} ({status})\n"
            text += f"Комментарий: {escape_html(rev.comment or '—')}\n"
            if rev.admin_reply:
                text += f"<i>Ответ: {escape_html(rev.admin_reply)}</i>\n"
            text += f"—— {rev.created_at[:10]}\n\n"
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


# ==================== РЕФЕРАЛЫ + QR ====================

@router.callback_query(F.data == "user_referral")
async def user_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return

    bot_info = await callback.bot.get_me()
    referral_link = _build_referral_link(bot_info.username, user)
    ref_code = user.referral_code or f"REF{user.user_id}"

    caption = (
        f"🔗 <b>Ваша реферальная ссылка</b>\n\n"
        f"<b>Код:</b> <code>{escape_html(ref_code)}</code>\n"
        f"<b>Ссылка:</b>\n<code>{escape_html(referral_link)}</code>\n\n"
        f"📲 Покажите QR-код другу — он сразу попадёт в бота как ваш реферал.\n\n"
        f"💰 Получайте <b>1%</b> с каждого обмена приглашённых."
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📤 Поделиться",
        url=f"https://t.me/share/url?url={referral_link}&text=Крипто-обменник с лучшими курсами!"
    )
    kb.button(text="🔙 Назад", callback_data="user_back_profile")
    kb.adjust(1)

    # Пытаемся удалить старое сообщение (если callback пришёл из текстового меню)
    try:
        await callback.message.delete()
    except Exception:
        pass

    qr_buf = generate_qr_bytes(referral_link)
    if qr_buf:
        photo = BufferedInputFile(qr_buf.read(), filename=f"ref_{user.user_id}.png")
        await callback.message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    else:
        # Fallback: если QR-библиотека недоступна
        await callback.message.answer(
            caption,
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await callback.answer()


@router.callback_query(F.data == "user_settings")
async def user_settings(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"<b>Уведомления:</b> {'✅ Включены' if user.notifications_enabled else '❌ Отключены'}\n"
        f"<b>Язык:</b> {escape_html(user.language or 'ru')}\n\n"
        f"Выберите настройку для изменения:"
    )
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔔 Уведомления", callback_data="user_toggle_notifications")
    keyboard.button(text="🔙 Назад", callback_data="user_back_profile")
    keyboard.adjust(1)
    await safe_edit_message(callback.message, text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "user_toggle_notifications")
async def user_toggle_notifications(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Ошибка загрузки данных", show_alert=True)
        return
    new_value = not user.notifications_enabled
    await db.set_user_notifications(user_id, new_value)
    status = "включены" if new_value else "отключены"
    await callback.answer(f"Уведомления {status}", show_alert=True)
    await user_settings(callback)


@router.callback_query(F.data == "user_back_profile")
async def user_back_profile(callback: CallbackQuery):
    await cmd_profile(callback.message)
    await callback.answer()


@router.callback_query(F.data == "user_back_main")
async def user_back_main(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()