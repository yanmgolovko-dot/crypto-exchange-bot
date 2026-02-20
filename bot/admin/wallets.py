"""Обработчики админ-панели для управления крипто-кошельками"""

import logging
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.db import db
from bot.services.admin_wallet_service import AdminWalletService
from bot.admin.main import is_admin
from bot.admin.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_wallets_menu")
async def admin_wallets_menu(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer()

    balances = await admin_wallet_service.refresh_balances()
    btc_balance = balances['BTC']
    ltc_balance = balances['LTC']

    wallets = await admin_wallet_service.get_wallets()
    btc_wallets = [w for w in wallets if w.crypto_type == 'BTC']
    ltc_wallets = [w for w in wallets if w.crypto_type == 'LTC']

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Добавить кошелек", callback_data="admin_wallet_add")
    keyboard.button(text="📋 Список кошельков", callback_data="admin_wallet_list")
    keyboard.button(text="🔄 Обновить балансы", callback_data="admin_wallet_refresh")
    keyboard.button(text="📊 История транзакций", callback_data="admin_wallet_tx_history")
    keyboard.button(text="🗑 Удалить все кошельки", callback_data="admin_wallets_delete_all_confirm")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    text = (
        f"💎 <b>Управление крипто-кошельками</b>\n\n"
        f"<b>Bitcoin (BTC):</b>\n"
        f"   Кошельков: {len(btc_wallets)}\n"
        f"   Баланс: {btc_balance:.8f} BTC\n\n"
        f"<b>Litecoin (LTC):</b>\n"
        f"   Кошельков: {len(ltc_wallets)}\n"
        f"   Баланс: {ltc_balance:.8f} LTC\n\n"
        f"Выберите действие:"
    )

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_wallet_add")
async def admin_wallet_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.adding_wallet_type)

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="₿ Bitcoin (BTC)", callback_data="wallet_type_BTC")
    keyboard.button(text="Ł Litecoin (LTC)", callback_data="wallet_type_LTC")
    keyboard.button(text="🔙 Отмена", callback_data="admin_wallets_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(
        "💎 <b>Добавление кошелька</b>\n\n"
        "Выберите тип криптовалюты:",
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wallet_type_"))
async def admin_wallet_address(callback: CallbackQuery, state: FSMContext):
    crypto_type = callback.data.split("_")[2]

    await state.update_data(wallet_type=crypto_type)
    await state.set_state(AdminStates.adding_wallet_address)

    await callback.message.edit_text(
        f"💎 <b>Добавление {crypto_type} кошелька</b>\n\n"
        f"Введите публичный адрес кошелька:\n"
        f"(например: {'1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa' if crypto_type == 'BTC' else 'LVgDpZd7dJ6t7mLqFf7vQZpC7J7z4y5Y5'})",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.adding_wallet_address)
async def admin_wallet_key(message: Message, state: FSMContext):
    address = message.text.strip()
    data = await state.get_data()
    crypto_type = data.get('wallet_type')

    if len(address) < 26 or len(address) > 60:
        await message.answer("❌ Некорректный адрес. Попробуйте еще раз:")
        return

    await state.update_data(wallet_address=address)
    await state.set_state(AdminStates.adding_wallet_key)

    await message.answer(
        f"🔑 <b>Введите приватный ключ (WIF)</b>\n\n"
        f"Формат WIF (начинается с {'K' if crypto_type == 'BTC' else 'T'}...):\n\n"
        f"⚠️ <b>Внимание!</b> Ключ будет зашифрован и храниться в базе данных.\n"
        f"Убедитесь, что у вас есть резервная копия!",
        parse_mode="HTML"
    )


@router.message(AdminStates.adding_wallet_key)
async def admin_wallet_label(message: Message, state: FSMContext):
    private_key = message.text.strip()

    if len(private_key) < 50:
        await message.answer("❌ Некорректный WIF ключ. Попробуйте еще раз:")
        return

    await state.update_data(wallet_key=private_key)
    await state.set_state(AdminStates.adding_wallet_label)

    await message.answer(
        "🏷 <b>Введите метку для кошелька</b>\n\n"
        "(например: 'Основной BTC', 'Резервный LTC' или оставьте пустым):"
    )


@router.message(AdminStates.adding_wallet_label)
async def admin_wallet_finish(message: Message, state: FSMContext, admin_wallet_service: AdminWalletService):
    label = message.text.strip() or None
    data = await state.get_data()

    try:
        wallet_id = await admin_wallet_service.add_wallet(
            crypto_type=data['wallet_type'],
            address=data['wallet_address'],
            private_key=data['wallet_key'],
            label=label
        )
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            await message.answer("❌ Кошелек с таким адресом уже существует.")
        else:
            await message.answer(f"❌ Ошибка при добавлении кошелька: {e}")
        await state.clear()
        return

    await admin_wallet_service.wallet_manager.update_balance(wallet_id)

    safe_address = html.escape(data['wallet_address'])
    await message.answer(
        f"✅ <b>Кошелек добавлен!</b>\n\n"
        f"Тип: {data['wallet_type']}\n"
        f"Адрес: <code>{safe_address}</code>\n"
        f"Метка: {label or 'Нет'}",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 К кошелькам", callback_data="admin_wallets_menu").as_markup(),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data == "admin_wallet_list")
async def admin_wallet_list(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    wallets = await admin_wallet_service.get_wallets(include_inactive=True)

    if not wallets:
        await callback.answer("Нет добавленных кошельков", show_alert=True)
        return

    text = "💎 <b>Список кошельков:</b>\n\n"
    keyboard = InlineKeyboardBuilder()

    for wallet in wallets:
        status = "✅" if wallet.is_active else "❌"
        default = " (по умолчанию)" if wallet.is_default else ""
        safe_address = html.escape(wallet.address[:20])
        text += (
            f"{status} <b>{wallet.crypto_type}</b>{default}\n"
            f"   Адрес: <code>{safe_address}...</code>\n"
            f"   Баланс: {wallet.balance:.8f} {wallet.crypto_type}\n"
            f"   Метка: {wallet.label or 'Нет'}\n\n"
        )
        if wallet.is_active:
            keyboard.button(text=f"❌ Деактивировать {wallet.crypto_type}", callback_data=f"admin_wallet_deactivate_{wallet.id}")
        else:
            keyboard.button(text=f"✅ Активировать {wallet.crypto_type}", callback_data=f"admin_wallet_activate_{wallet.id}")
        # Кнопка полного удаления
        keyboard.button(text=f"🗑 Удалить навсегда {wallet.crypto_type}", callback_data=f"admin_wallet_hard_delete_confirm_{wallet.id}")

    keyboard.button(text="🔙 Назад", callback_data="admin_wallets_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallet_deactivate_"))
async def admin_wallet_deactivate_confirm(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        wallet_id = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    success = await admin_wallet_service.deactivate_wallet(wallet_id)
    if success:
        try:
            await callback.answer("✅ Кошелек деактивирован", show_alert=True)
        except Exception:
            pass
        await admin_wallet_list(callback, admin_wallet_service)
    else:
        await callback.answer("❌ Ошибка при деактивации", show_alert=True)


@router.callback_query(F.data.startswith("admin_wallet_activate_"))
async def admin_wallet_activate(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.answer("⏳ Функция активации в разработке", show_alert=True)


# ==================== ПОЛНОЕ УДАЛЕНИЕ КОШЕЛЬКА ====================

@router.callback_query(F.data.startswith("admin_wallet_hard_delete_confirm_"))
async def admin_wallet_hard_delete_confirm(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        wallet_id = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    wallet = await admin_wallet_service.db.get_wallet(wallet_id=wallet_id)
    if not wallet:
        await callback.answer("❌ Кошелек не найден", show_alert=True)
        return

    text = (
        f"⚠️ <b>Подтверждение полного удаления кошелька</b>\n\n"
        f"Тип: {wallet.crypto_type}\n"
        f"Адрес: <code>{html.escape(wallet.address)}</code>\n"
        f"Метка: {wallet.label or 'Нет'}\n\n"
        f"Это действие <b>безвозвратно удалит</b> кошелёк из базы данных.\n"
        f"Все связанные транзакции останутся, но кошелёк перестанет существовать.\n\n"
        f"Вы уверены?"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить навсегда", callback_data=f"admin_wallet_hard_delete_execute_{wallet_id}")
    keyboard.button(text="❌ Нет", callback_data="admin_wallet_list")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_wallet_hard_delete_execute_"))
async def admin_wallet_hard_delete_execute(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    try:
        wallet_id = int(callback.data.split("_")[-1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка формата данных", show_alert=True)
        return

    try:
        success = await admin_wallet_service.hard_delete_wallet(wallet_id)
        if success:
            try:
                await callback.answer("✅ Кошелек полностью удалён", show_alert=True)
            except Exception:
                pass
            await admin_wallet_list(callback, admin_wallet_service)
        else:
            await callback.answer("❌ Ошибка при удалении (неизвестная причина)", show_alert=True)
    except Exception as e:
        error_str = str(e)
        if "FOREIGN KEY constraint failed" in error_str:
            await callback.answer("❌ Нельзя удалить: есть связанные транзакции. Сначала удалите их вручную.", show_alert=True)
        else:
            await callback.answer(f"❌ Ошибка: {error_str[:100]}", show_alert=True)


# ==================== УДАЛЕНИЕ ВСЕХ КОШЕЛЬКОВ (ДЕАКТИВАЦИЯ) ====================

@router.callback_query(F.data == "admin_wallets_delete_all_confirm")
async def admin_wallets_delete_all_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    text = (
        "⚠️ <b>Подтверждение деактивации всех кошельков</b>\n\n"
        "Это действие <b>деактивирует</b> ВСЕ кошельки (как BTC, так и LTC).\n"
        "Они перестанут использоваться для отправки и проверки балансов.\n"
        "Вы сможете активировать их позже или добавить новые.\n\n"
        "Вы уверены?"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, деактивировать всё", callback_data="admin_wallets_delete_all_execute")
    keyboard.button(text="❌ Нет", callback_data="admin_wallets_menu")
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_wallets_delete_all_execute")
async def admin_wallets_delete_all_execute(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    wallets = await admin_wallet_service.get_wallets(include_inactive=True)
    if not wallets:
        await callback.answer("📭 Нет кошельков для деактивации", show_alert=True)
        return

    deactivated = 0
    for wallet in wallets:
        if wallet.is_active:
            await admin_wallet_service.deactivate_wallet(wallet.id)
            deactivated += 1

    try:
        await callback.answer(f"✅ Деактивировано кошельков: {deactivated}", show_alert=True)
    except Exception:
        pass

    await admin_wallets_menu(callback, admin_wallet_service)


# ==================== ОБНОВЛЕНИЕ БАЛАНСОВ ====================

@router.callback_query(F.data == "admin_wallet_refresh")
async def admin_wallet_refresh(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await callback.answer("🔄 Обновляю балансы...", show_alert=False)

    balances = await admin_wallet_service.refresh_balances()
    wallets = await admin_wallet_service.get_wallets()
    btc_wallets = [w for w in wallets if w.crypto_type == 'BTC']
    ltc_wallets = [w for w in wallets if w.crypto_type == 'LTC']

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Добавить кошелек", callback_data="admin_wallet_add")
    keyboard.button(text="📋 Список кошельков", callback_data="admin_wallet_list")
    keyboard.button(text="🔄 Обновить балансы", callback_data="admin_wallet_refresh")
    keyboard.button(text="📊 История транзакций", callback_data="admin_wallet_tx_history")
    keyboard.button(text="🗑 Удалить все кошельки", callback_data="admin_wallets_delete_all_confirm")
    keyboard.button(text="🔙 Назад", callback_data="admin_back_main")
    keyboard.adjust(1)

    new_text = (
        f"💎 <b>Управление крипто-кошельками</b>\n\n"
        f"<b>Bitcoin (BTC):</b>\n"
        f"   Кошельков: {len(btc_wallets)}\n"
        f"   Баланс: {balances['BTC']:.8f} BTC\n\n"
        f"<b>Litecoin (LTC):</b>\n"
        f"   Кошельков: {len(ltc_wallets)}\n"
        f"   Баланс: {balances['LTC']:.8f} LTC\n\n"
        f"Выберите действие:"
    )

    try:
        await callback.message.edit_text(new_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e):
            logger.error(f"Ошибка при обновлении сообщения: {e}")
            await callback.message.answer(new_text, reply_markup=keyboard.as_markup(), parse_mode="HTML")


# ==================== ИСТОРИЯ ТРАНЗАКЦИЙ ====================

@router.callback_query(F.data == "admin_wallet_tx_history")
async def admin_wallet_tx_history(callback: CallbackQuery, admin_wallet_service: AdminWalletService):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    transactions = await admin_wallet_service.wallet_manager.get_transaction_history(limit=20)

    if not transactions:
        await callback.answer("Нет транзакций", show_alert=True)
        return

    text = "📊 <b>История транзакций:</b>\n\n"

    for tx in transactions[:10]:
        status_emoji = {
            'pending': '⏳',
            'broadcasted': '📤',
            'confirmed': '✅',
            'failed': '❌'
        }.get(tx.status, '❓')

        safe_to_address = html.escape(tx.to_address[:20])
        safe_tx_hash = html.escape(tx.tx_hash[:16]) if tx.tx_hash else 'N/A'

        text += (
            f"{status_emoji} <b>#{tx.id}</b> | Заявка #{tx.order_id}\n"
            f"   {tx.amount:.8f} {tx.crypto_type}\n"
            f"   На: <code>{safe_to_address}...</code>\n"
            f"   TX: <code>{safe_tx_hash}...</code>\n"
            f"   Подтверждений: {tx.confirmations}\n\n"
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="admin_wallets_menu")

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()