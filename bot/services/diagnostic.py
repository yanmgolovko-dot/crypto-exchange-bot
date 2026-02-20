import logging
from bot.services.db import db
from bot.services.crypto_api import crypto_api
from bot.services.crypto_wallets import wallet_manager
from bot.services.order_service import OrderService
from bot.config.settings import config

logger = logging.getLogger(__name__)

class DiagnosticResult:
    """Класс для сбора и форматирования результатов диагностики"""
    def __init__(self):
        self.results = {}
        self.errors = []

    def add_success(self, name: str, message: str = "OK"):
        self.results[name] = {"status": "✅", "message": message}

    def add_error(self, name: str, error: str):
        self.results[name] = {"status": "❌", "message": error}
        self.errors.append(f"{name}: {error}")

    def to_text(self) -> str:
        lines = ["🔍 <b>Результаты диагностики:</b>\n"]
        for name, res in self.results.items():
            lines.append(f"{res['status']} <b>{name}:</b> {res['message']}")
        if self.errors:
            lines.append("\n⚠️ <b>Обнаружены ошибки:</b>")
            for err in self.errors:
                lines.append(f"   {err}")
        else:
            lines.append("\n✅ <b>Все системы работают корректно.</b>")
        return "\n".join(lines)


async def run_diagnostics(admin_id: int, bot) -> DiagnosticResult:
    """
    Запускает все проверки и возвращает объект DiagnosticResult.
    admin_id - ID администратора для отправки тестового сообщения.
    bot - экземпляр бота.
    """
    result = DiagnosticResult()

    # 1. Подключение к БД
    try:
        if not db._connection._conn:
            await db.connect()
        async with db._connection.conn.execute("SELECT 1") as cursor:
            await cursor.fetchone()
        result.add_success("База данных", "Подключение работает")
    except Exception as e:
        result.add_error("База данных", str(e))

    # 2. Проверка наличия основных таблиц
    try:
        tables = ['users', 'exchange_orders', 'system_settings', 'exchange_wallets',
                  'bank_details', 'promo_codes', 'financial_records']
        missing = []
        for table in tables:
            async with db._connection.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    missing.append(table)
        if missing:
            result.add_error("Структура БД", f"Отсутствуют таблицы: {', '.join(missing)}")
        else:
            result.add_success("Структура БД", "Все основные таблицы присутствуют")
    except Exception as e:
        result.add_error("Структура БД", str(e))

    # 3. Проверка API курсов
    try:
        btc = await crypto_api.get_btc_price_rub(force_refresh=True)
        ltc = await crypto_api.get_ltc_price_rub(force_refresh=True)
        if btc is not None and ltc is not None:
            result.add_success("Курсы валют", f"BTC: {btc:,.0f} ₽, LTC: {ltc:,.0f} ₽")
        else:
            result.add_error("Курсы валют", "Не удалось получить курсы (проверьте API)")
    except Exception as e:
        result.add_error("Курсы валют", str(e))

    # 4. Проверка кошельков
    try:
        wallets = await wallet_manager.get_all_wallets()
        if wallets:
            btc_count = len([w for w in wallets if w.crypto_type == 'BTC'])
            ltc_count = len([w for w in wallets if w.crypto_type == 'LTC'])
            active = [w for w in wallets if w.is_active]
            msg = f"BTC: {btc_count}, LTC: {ltc_count} (активных: {len(active)})"
            # Проверим баланс первого активного
            if active:
                w = active[0]
                bal = await wallet_manager.update_balance(w.id)
                if bal['success']:
                    msg += f" | Баланс {w.crypto_type}: {bal['balance']:.8f}"
                else:
                    msg += f" | Ошибка баланса: {bal.get('error')}"
            result.add_success("Кошельки", msg)
        else:
            result.add_error("Кошельки", "Нет добавленных кошельков")
    except Exception as e:
        result.add_error("Кошельки", str(e))

    # 5. Проверка расчёта заявки
    try:
        order_service = OrderService(db, crypto_api)
        calc = await order_service.calculate_order(
            crypto_type="BTC",
            input_type="rub",
            amount=5000,
            discount_percent=0
        )
        if calc and calc.get('gross_amount'):
            result.add_success("Расчёт заявки",
                               f"Сумма к оплате: {calc['gross_amount']:,.0f} ₽, получение: {calc['amount_crypto']:.8f} BTC")
        else:
            result.add_error("Расчёт заявки", "Не удалось выполнить расчёт")
    except Exception as e:
        result.add_error("Расчёт заявки", str(e))

    # 6. Проверка отправки сообщения (администратору)
    try:
        await bot.send_message(admin_id,
                               "✅ <b>Диагностика:</b> тестовое сообщение отправлено успешно",
                               parse_mode="HTML")
        result.add_success("Отправка сообщений", "OK")
    except Exception as e:
        result.add_error("Отправка сообщений", str(e))

    # 7. Проверка получения настроек
    try:
        fee = await db.get_exchange_fee()
        min_amt = await db.get_setting('min_amount', '1000')
        max_amt = await db.get_setting('max_amount', '500000')
        result.add_success("Настройки", f"Комиссия: {fee}%, мин: {min_amt} ₽, макс: {max_amt} ₽")
    except Exception as e:
        result.add_error("Настройки", str(e))

    # 8. Проверка списка администраторов
    try:
        if config.ADMIN_IDS:
            result.add_success("Администраторы", f"ID: {', '.join(map(str, config.ADMIN_IDS))}")
        else:
            result.add_error("Администраторы", "Список ADMIN_IDS пуст!")
    except Exception as e:
        result.add_error("Администраторы", str(e))

    return result