# bot/main.py
"""Основной файл Telegram бота обменника криптовалют"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
import traceback
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config.settings import config
from bot.services.db import db, Database
from bot.services.db.init import init_db_sync
from bot.services.crypto_api import crypto_api
from bot.services.crypto_wallets import wallet_manager, CryptoWalletManager
from bot.services.order_service import OrderService
from bot.services.payment_service import PaymentService
from bot.services.user_service import UserService
from bot.services.admin_order_service import AdminOrderService
from bot.services.admin_user_service import AdminUserService
from bot.services.admin_wallet_service import AdminWalletService
from bot.services.admin_finance_service import AdminFinanceService
from bot.handlers import router as user_router
from bot.admin import router as admin_router

# Отключаем буферизацию stdout для Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ (временная, потом будет заменена из БД) ====================
# Сначала настраиваем базовое логирование, чтобы видеть процесс загрузки
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Создаём сессию с увеличенным таймаутом
session = AiohttpSession(timeout=300)
bot = Bot(token=config.BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ==================== ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ ====================
order_service = OrderService(db, crypto_api)
payment_service = PaymentService(db)
user_service = UserService(db)
admin_order_service = AdminOrderService(db, wallet_manager)
admin_user_service = AdminUserService(db)
admin_wallet_service = AdminWalletService(db, wallet_manager)
admin_finance_service = AdminFinanceService(db)

# ==================== МИДЛВАРЬ ДЛЯ ПРОКИДЫВАНИЯ ЗАВИСИМОСТЕЙ ====================
async def services_middleware(handler, event, data):
    data['db'] = db
    data['crypto_api'] = crypto_api
    data['wallet_manager'] = wallet_manager
    data['order_service'] = order_service
    data['payment_service'] = payment_service
    data['user_service'] = user_service
    data['admin_order_service'] = admin_order_service
    data['admin_user_service'] = admin_user_service
    data['admin_wallet_service'] = admin_wallet_service
    data['admin_finance_service'] = admin_finance_service
    data['bot'] = bot
    return await handler(event, data)

# ==================== МИДЛВАРИ ДЛЯ ПРОВЕРКИ БАНА И АКТИВНОСТИ ====================
async def check_banned_middleware(handler, event, data):
    if isinstance(event, (Message, CallbackQuery)):
        user_id = event.from_user.id
        user_service = data.get('user_service')
        if not user_service:
            return await handler(event, data)
        is_banned, ban_reason = await user_service.is_banned(user_id)
        if is_banned:
            if isinstance(event, Message):
                await event.answer(
                    f"🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                    f"Причина: {ban_reason}\n\n"
                    f"Для разблокировки обратитесь в поддержку.",
                    parse_mode="HTML"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔ Ваш аккаунт заблокирован", show_alert=True)
            return
    return await handler(event, data)

async def update_activity_middleware(handler, event, data):
    if isinstance(event, (Message, CallbackQuery)):
        user_id = event.from_user.id
        asyncio.create_task(db.users.update_last_activity(user_id))
    return await handler(event, data)

# Регистрируем мидлвари
dp.message.middleware(services_middleware)
dp.callback_query.middleware(services_middleware)
dp.message.middleware(check_banned_middleware)
dp.callback_query.middleware(check_banned_middleware)
dp.message.middleware(update_activity_middleware)
dp.callback_query.middleware(update_activity_middleware)

dp.include_router(admin_router)
dp.include_router(user_router)


# ==================== ФОНОВЫЙ ВОРКЕР НАПОМИНАНИЙ ====================
async def reminder_worker(bot: Bot, db: Database, payment_service: PaymentService):
    """Фоновая задача для отправки напоминаний о неоплаченных заявках."""
    logger.info("Запуск воркера напоминаний")
    while True:
        try:
            orders = await db.orders.get_pending_orders_for_reminder(minutes=5, max_reminders=3)
            for order in orders:
                logger.info(f"Отправка напоминания по заявке #{order.id} пользователю {order.user_id}")
                success = await payment_service.send_payment_reminder(bot, order, order.user_id)
                if success:
                    await db.orders.increment_reminder_count(order.id)
                await asyncio.sleep(1)
        except Exception as e:
            logger.exception(f"Ошибка в воркере напоминаний: {e}")
        await asyncio.sleep(60)


async def on_startup():
    start_time = time.time()
    logger.info("[START] Запуск бота, инициализация...")

    # Создаём таблицы, если их нет (синхронно, в потоке)
    def create_tables():
        init_db_sync()
        logger.info("[OK] Таблицы созданы/проверены")

    await asyncio.to_thread(create_tables)

    # Подключаемся к БД
    await db.connect()
    logger.info("[OK] Подключение к базе данных установлено")

    # Получаем уровень логирования из БД и перенастраиваем корневой логгер
    try:
        # Проверяем наличие метода get_log_level (на случай, если БД ещё не обновлена)
        if hasattr(db, 'get_log_level'):
            db_log_level = await db.get_log_level()
            log_level = getattr(logging, db_log_level.upper(), logging.INFO)
        else:
            logger.warning("Метод get_log_level не найден в db. Использую INFO.")
            log_level = logging.INFO
            db_log_level = "INFO"
    except Exception as e:
        logger.warning(f"Не удалось получить уровень логирования из БД: {e}. Использую INFO.")
        log_level = logging.INFO
        db_log_level = "INFO"

    # Настройка форматтера и обработчиков
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # чтобы все сообщения доходили до обработчиков

    # Очистим старые обработчики, если они были (например, от basicConfig)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Создаём новые обработчики с нужным уровнем
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Консольный вывод (может быть проблема с кодировкой на Windows, поэтому эмодзи заменены на текст)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(log_level)

    # Файловый вывод с ротацией (10 MB, 5 бэкапов)
    file_handler = RotatingFileHandler('bot.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)  # в файл пишем всё

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Устанавливаем уровни для шумных библиотек
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

    logger.info(f"Уровень логирования установлен: {db_log_level} (из БД)")

    new_version = await db.increment_bot_version()
    logger.info(f"[OK] Версия бота: {new_version}")

    elapsed = time.time() - start_time
    logger.info(f"[TIME] Время загрузки: {elapsed:.2f} секунд")

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🤖 <b>Бот запущен!</b>\n\n"
                f"Версия: {new_version}\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Загрузка: {elapsed:.2f} сек\n"
                f"Уровень логов: {db_log_level}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")


async def on_shutdown():
    logger.info("Остановка бота...")
    await wallet_manager.close()
    await crypto_api.close()
    await db.close()


async def main():
    logger.info("Запуск бота...")
    await on_startup()

    asyncio.create_task(reminder_worker(bot, db, payment_service))

    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("Ошибка при запуске:")
        traceback.print_exc()
        sys.exit(1)