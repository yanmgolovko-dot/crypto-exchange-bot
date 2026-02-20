# bot/services/admin_finance_service.py
"""
Сервис для админ-операций с финансами.
Предоставляет методы для получения статистики, управления расходами и курсами.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from bot.services.db import Database
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)


class AdminFinanceService:
    """
    Сервис для административных операций, связанных с финансами:
    - получение общей и ежедневной статистики
    - добавление расходов
    - просмотр последних финансовых записей
    - обновление курсов валют
    """

    def __init__(self, db: Database):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        Получить статистику для главного дашборда.
        Возвращает словарь с количеством пользователей, заявок, оборотом и т.д.
        """
        logger.info("Запрос статистики для дашборда")
        try:
            stats = await self.db.get_dashboard_stats()
            logger.debug(f"Статистика дашборда получена: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Ошибка при получении статистики дашборда: {e}", exc_info=True)
            return {}

    async def get_financial_stats(self, days: int) -> Dict[str, Any]:
        """
        Получить финансовую статистику за указанный период (выручка, расходы, прибыль, оборот).
        :param days: количество дней, за которые нужна статистика
        """
        logger.info(f"Запрос финансовой статистики за {days} дней")
        try:
            stats = await self.db.get_financial_stats(days=days)
            logger.debug(f"Финансовая статистика за {days} дней: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Ошибка при получении финансовой статистики за {days} дней: {e}", exc_info=True)
            return {'revenue': 0, 'expenses': 0, 'profit': 0, 'trading_volume': 0, 'period_days': days}

    async def get_daily_stats(self, days: int) -> List[Dict[str, Any]]:
        """
        Получить ежедневную статистику (количество заявок, объём, комиссия) за последние days дней.
        :param days: количество дней (обычно 7 или 30)
        """
        logger.info(f"Запрос ежедневной статистики за {days} дней")
        try:
            daily_stats = await self.db.get_daily_stats(days=days)
            logger.debug(f"Получено {len(daily_stats)} записей ежедневной статистики")
            return daily_stats
        except Exception as e:
            logger.error(f"Ошибка при получении ежедневной статистики: {e}", exc_info=True)
            return []

    async def get_recent_records(self, limit: int = 20) -> List[Any]:
        """
        Получить последние финансовые записи (доходы, расходы).
        :param limit: максимальное количество записей
        """
        logger.info(f"Запрос последних финансовых записей (limit={limit})")
        try:
            records = await self.db.get_recent_financial_records(limit=limit)
            logger.debug(f"Получено {len(records)} финансовых записей")
            return records
        except Exception as e:
            logger.error(f"Ошибка при получении последних финансовых записей: {e}", exc_info=True)
            return []

    async def add_expense(self, amount: float, description: str, admin_id: int) -> int:
        """
        Добавить расход (запись типа 'expense') в финансовые записи.
        :param amount: сумма расхода
        :param description: описание
        :param admin_id: ID администратора, добавившего расход
        :return: ID созданной записи или 0 при ошибке
        """
        logger.info(f"[ADMIN {admin_id}] Добавление расхода: {amount} ₽ - {description}")
        try:
            record_id = await self.db.add_financial_record(
                record_type='expense',
                category='operational',
                amount=amount,
                description=description,
                created_by=admin_id
            )
            logger.info(f"[ADMIN {admin_id}] Расход добавлен, ID записи: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"[ADMIN {admin_id}] Ошибка при добавлении расхода: {e}", exc_info=True)
            return 0

    async def get_exchange_rates(self, force_refresh: bool = False) -> Dict[str, float]:
        """
        Получить текущие курсы BTC и LTC к рублю.
        :param force_refresh: если True, игнорировать кэш и принудительно обновить
        """
        logger.info(f"Запрос курсов валют (force_refresh={force_refresh})")
        try:
            btc = await crypto_api.get_btc_price_rub(force_refresh=force_refresh)
            ltc = await crypto_api.get_ltc_price_rub(force_refresh=force_refresh)
            logger.info(f"Курсы: BTC={btc}, LTC={ltc}")
            return {"BTC": btc, "LTC": ltc}
        except Exception as e:
            logger.error(f"Ошибка при получении курсов: {e}", exc_info=True)
            return {"BTC": None, "LTC": None}

    async def get_total_volume(self) -> float:
        """
        Общий оборот (сумма всех выполненных заявок) за всё время.
        """
        logger.info("Запрос общего оборота")
        try:
            stats = await self.db.get_financial_stats(days=365)
            volume = stats.get('trading_volume', 0.0)
            logger.debug(f"Общий оборот: {volume} ₽")
            return volume
        except Exception as e:
            logger.error(f"Ошибка при получении общего оборота: {e}", exc_info=True)
            return 0.0

    async def get_total_fees(self) -> float:
        """
        Общая сумма комиссий (выручка) за всё время.
        """
        logger.info("Запрос общей суммы комиссий")
        try:
            stats = await self.db.get_financial_stats(days=365)
            fees = stats.get('revenue', 0.0)
            logger.debug(f"Общая сумма комиссий: {fees} ₽")
            return fees
        except Exception as e:
            logger.error(f"Ошибка при получении общей суммы комиссий: {e}", exc_info=True)
            return 0.0