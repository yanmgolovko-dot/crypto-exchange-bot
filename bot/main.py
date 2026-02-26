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

# ========== НАСТРОЙКА ЛОГГЕРА СРАЗУ ПОСЛЕ ИМПОРТА СТАНДАРТНЫХ БИБЛИОТЕК ==========
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logging.getLogger().debug("🔧 Базовая настройка логгера выполнена")

# Импорты aiogram
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, Update
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties

# Импорты модулей проекта
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
from bot.services.partner_service import partner_service
from bot.handlers import router as user_router
from bot.admin import router as admin_router

# Отключаем буферизацию stdout для Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

logger = logging.getLogger(__name__)

print("🔧 Создание сессии бота...")
session = AiohttpSession(timeout=300)
bot = Bot(token=config.BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# ==================== ОТЛАДОЧНАЯ МИДЛВАРЬ ДЛЯ ЛОГГИРОВАНИЯ АПДЕЙТОВ ====================
@dp.update.outer_middleware()
async def log_updates(handler, event: Update, data):
    logger.info(f"📩 Получен апдейт ID: {event.update_id}")
    if event.message:
        logger.info(f"   Сообщение от {event.message.from_user.id}: {event.message.text}")
    elif event.callback_query:
        logger.info(f"   Callback от {event.callback_query.from_user.id}: {event.callback_query.data}")
    return await handler(event, data)

print("🔧 Инициализация сервисов...")
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
    """
    Фоновая задача для отправки напоминаний о неоплаченных заявках.
    Проверяет настройку reminders_enabled – если отключено, ничего не делает.
    """
    logger.info("Запуск воркера напоминаний")
    while True:
        try:
            # Проверяем, включены ли напоминания
            reminders_enabled = await db.settings.get_reminders_enabled()
            if not reminders_enabled:
                await asyncio.sleep(60)
                continue

            orders = await db.orders.get_pending_orders_for_reminder(minutes=5, max_reminders=3)
            for order in orders:
                # Пытаемся отправить до 3 раз с экспоненциальной задержкой
                for attempt in range(3):
                    try:
                        logger.info(f"Отправка напоминания по заявке #{order.id} пользователю {order.user_id} (попытка {attempt+1})")
                        success = await payment_service.send_payment_reminder(bot, order, order.user_id)
                        if success:
                            await db.orders.increment_reminder_count(order.id)
                            logger.info(f"Напоминание по заявке #{order.id} успешно отправлено")
                            break
                        else:
                            logger.warning(f"Не удалось отправить напоминание по заявке #{order.id} (попытка {attempt+1})")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке напоминания по заявке #{order.id} (попытка {attempt+1}): {e}")
                        if attempt == 2:
                            logger.error(f"Все попытки для заявки #{order.id} исчерпаны")
                        else:
                            wait = 2 ** attempt  # экспоненциальная задержка: 1, 2, 4 секунды
                            await asyncio.sleep(wait)
                await asyncio.sleep(1)  # пауза между разными заявками
        except Exception as e:
            logger.exception(f"Критическая ошибка в воркере напоминаний: {e}")
        await asyncio.sleep(60)


async def on_startup():
    print("🟢 on_startup: начало")
    start_time = time.time()
    logger.info("[START] Запуск бота, инициализация...")

    def create_tables():
        init_db_sync()
        logger.info("[OK] Таблицы созданы/проверены")

    await asyncio.to_thread(create_tables)
    print("🟢 Таблицы созданы/проверены")

    print("🟢 Подключение к базе данных...")
    await db.connect()
    logger.info("[OK] Подключение к базе данных установлено")
    print("🟢 Подключение к БД выполнено")

    # Получаем уровень логирования из БД через сервис
    print("🟢 Чтение уровня логирования из БД...")
    try:
        if hasattr(db, 'get_log_level'):
            db_log_level = await db.get_log_level()
            log_level = getattr(logging, db_log_level.upper(), logging.INFO)
        else:
            logger.warning("Метод get_log_level не найден. Использую INFO.")
            log_level = logging.INFO
            db_log_level = "INFO"
    except Exception as e:
        logger.warning(f"Не удалось получить уровень из БД: {e}. Использую INFO.")
        log_level = logging.INFO
        db_log_level = "INFO"
    print(f"🟢 Уровень логирования из БД (через сервис): {db_log_level}")

    # Применяем уровень к корневому логгеру
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Устанавливаем уровни для шумных библиотек
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)

    logger.info(f"Уровень логирования установлен: {db_log_level} (из БД)")
    print(f"🟢 Логгеры настроены")

    new_version = await db.increment_bot_version()
    logger.info(f"[OK] Версия бота: {new_version}")
    print(f"🟢 Версия бота: {new_version}")

    elapsed = time.time() - start_time
    logger.info(f"[TIME] Время загрузки: {elapsed:.2f} секунд")
    print(f"🟢 Время загрузки: {elapsed:.2f} сек")

    # Игнорируем отправку самому себе (боту)
    bot_id = (await bot.get_me()).id
    for admin_id in config.ADMIN_IDS:
        if admin_id == bot_id:
            logger.warning(f"ID бота {bot_id} присутствует в списке администраторов. Пропускаем уведомление.")
            continue
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
            print(f"🟢 Уведомление отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")
            print(f"❌ Ошибка уведомления админа {admin_id}: {e}")

    print("🟢 on_startup завершён")


async def on_shutdown():
    logger.info("Остановка бота...")
    await wallet_manager.close()
    await crypto_api.close()
    await db.close()


async def main():
    print("🟢 main: запуск...")
    logger.info("Запуск бота...")
    try:
        bot_info = await bot.get_me()
        print(f"✅ Бот @{bot_info.username} подключён")
    except Exception as e:
        print(f"❌ Не удалось подключиться к Telegram API: {e}")
        return

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Вебхук удалён")
    except Exception as e:
        print(f"⚠️ Не удалось удалить вебхук: {e}")

    try:
        webhook_info = await bot.get_webhook_info()
        print(f"📡 Информация о вебхуке: url={webhook_info.url}, pending_updates={webhook_info.pending_update_count}")
    except Exception as e:
        print(f"⚠️ Не удалось получить информацию о вебхуке: {e}")

    await on_startup()

    asyncio.create_task(reminder_worker(bot, db, payment_service))

    try:
        print("🟢 Запуск polling с skip_updates=True...")
        await dp.start_polling(bot, skip_updates=True)
        print("🟢 Polling завершён (не должно происходить)")
    except Exception as e:
        print(f"❌ Ошибка в polling: {e}")
        traceback.print_exc()
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Ошибка при запуске:")
        traceback.print_exc()
        sys.exit(1)