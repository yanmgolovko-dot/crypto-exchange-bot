# bot/admin/ref_links.py
"""
Управление реферальными ссылками из админки.
Позволяет менять реферальный код пользователя на «красивый»
(например, вместо REF6083980632 сделать ILYA).
"""

import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.admin.main import is_admin
from bot.admin.states import AdminStates
from bot.services.db import db
from bot.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router()

# Разрешённые символы и длина нового кода
_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")
# Запрещаем коды вида ref12345 — они конфликтуют с legacy-парсингом
_LEGACY_RE = re.compile(r"^ref\d+$", re.IGNORECASE)


@router.callback_query(F.data == "admin_ref_links_menu")
async def ref_links_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню управления реф. ссылками."""
    admin_id = callback.from_user.id
    if not await is_admin(admin_id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить реф. код пользователя", callback_data="admin_ref_change_start")
    kb.button(text="🔙 Назад в админку", callback_data="admin_back_main")
    kb.adjust(1)

    await callback.message.edit_text(
        "🔗 <b>Управление реферальными ссылками</b>\n\n"
        "Здесь вы можете изменить реферальный код (красивую часть ссылки) "
        "для любого пользователя.\n\n"
        "Пример: вместо <code>REF6083980632</code> сделать <code>ILYA</code>.\n"
        "Ссылка станет: <code>https://t.me/ваш_бот?start=ILYA</code>\n\n"
        "⚠️ Старая ссылка (со старым кодом) перестанет работать после изменения.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin_ref_change_start")
async def ref_change_start(callback: CallbackQuery, state: FSMContext):
    """Начало смены реф. кода — просим ввести пользователя."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_target_user)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_ref_links_menu")

    await callback.message.edit_text(
        "🔍 <b>Шаг 1 из 2</b>\n\n"
        "Введите <b>ID</b> или <b>@username</b> пользователя, которому хотите изменить реф. код.\n\n"
        "Например: <code>6083980632</code> или <code>@arb_p3</code>\n"
        "Для отмены — /cancel.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_target_user)
async def ref_target_user_received(message: Message, state: FSMContext):
    """Ищем пользователя по ID или username."""
    if not await is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.")
        return

    user = None
    # 1) @username
    if text.startswith("@"):
        user = await db.get_user_by_username(text)
    # 2) чистое число = user_id
    elif text.isdigit():
        user = await db.get_user(int(text))
    # 3) username без @
    else:
        user = await db.get_user_by_username(text)

    if not user:
        await message.answer(
            "❌ Пользователь не найден.\n"
            "Проверьте ID или @username, или отправьте /cancel для отмены."
        )
        return

    await state.update_data(
        target_user_id=user.user_id,
        target_username=user.username,
    )
    await state.set_state(AdminStates.waiting_for_new_ref_code)

    current_code = user.referral_code or "—"
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="admin_ref_links_menu")

    await message.answer(
        f"👤 <b>Пользователь найден:</b>\n"
        f"   ID: <code>{user.user_id}</code>\n"
        f"   Username: {('@' + escape_html(user.username)) if user.username else 'N/A'}\n"
        f"   Текущий реф. код: <code>{escape_html(current_code)}</code>\n\n"
        f"✏️ <b>Шаг 2 из 2</b>\n\n"
        f"Введите новый реф. код:\n"
        f"   • только латиница, цифры, <code>_</code> и <code>-</code>;\n"
        f"   • длина от 3 до 32 символов;\n"
        f"   • без пробелов;\n"
        f"   • не должен начинаться с <code>ref</code> + цифры (зарезервировано).\n\n"
        f"Для отмены — /cancel.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_new_ref_code)
async def ref_new_code_received(message: Message, state: FSMContext, bot: Bot):
    """Валидируем и сохраняем новый реф. код."""
    if not await is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.")
        return

    if not _CODE_RE.match(text):
        await message.answer(
            "❌ Некорректный код.\n"
            "Разрешены только латиница, цифры, <code>_</code> и <code>-</code>, "
            "длина от 3 до 32 символов. Попробуйте снова или /cancel.",
            parse_mode="HTML",
        )
        return

    if _LEGACY_RE.match(text):
        await message.answer(
            "❌ Код вида <code>ref12345</code> зарезервирован системой. "
            "Выберите другой.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    target_username = data.get("target_username")

    if not target_user_id:
        await message.answer("❌ Ошибка: не найден пользователь. Начните заново.")
        await state.clear()
        return

    # Проверка на занятость
    existing = await db.get_user_by_referral_code(text)
    if existing and existing.user_id != target_user_id:
        await message.answer(
            f"❌ Код <code>{escape_html(text)}</code> уже занят другим пользователем "
            f"(ID: <code>{existing.user_id}</code>).\n"
            f"Введите другой код или /cancel.",
            parse_mode="HTML",
        )
        return

    try:
        await db.set_user_referral_code(target_user_id, text)
    except Exception as e:
        logger.exception("Ошибка сохранения реф. кода: %s", e)
        await message.answer(
            "❌ Не удалось сохранить код (возможно, уже занят). "
            "Попробуйте другой или /cancel."
        )
        return

    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "ваш_бот"

    new_link = f"https://t.me/{bot_username}?start={text}"
    safe_username = f"@{escape_html(target_username)}" if target_username else str(target_user_id)

    await message.answer(
        f"✅ <b>Реф. код успешно изменён!</b>\n\n"
        f"👤 Пользователь: {safe_username} (ID: <code>{target_user_id}</code>)\n"
        f"🔗 Новый код: <code>{escape_html(text)}</code>\n"
        f"📎 Новая ссылка:\n<code>{escape_html(new_link)}</code>\n\n"
        f"⚠️ Старая ссылка (со старым кодом) больше не будет работать.",
        parse_mode="HTML",
    )

    # Уведомляем клиента (если это не сам админ)
    if target_user_id != message.from_user.id:
        try:
            await bot.send_message(
                target_user_id,
                f"🔗 <b>Ваша реферальная ссылка обновлена!</b>\n\n"
                f"Новая ссылка:\n<code>{escape_html(new_link)}</code>\n\n"
                f"Поделитесь ей с друзьями, чтобы получать бонусы.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить пользователя {target_user_id}: {e}")
            await message.answer(
                f"⚠️ Код сохранён, но не удалось уведомить пользователя "
                f"(возможно, он заблокировал бота)."
            )

    await state.clear()