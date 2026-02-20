"""Сервис для админ-операций с финансами"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from bot.services.db import Database
from bot.services.crypto_api import crypto_api

logger = logging.getLogger(__name__)


class AdminFinanceService:
    def __init__(self, db: Database):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Получить статистику для главного дашборда"""
        return await self.db.get_dashboard_stats()

    async def get_financial_stats(self, days: int) -> Dict[str, Any]:
        """Получить финансовую статистику за указанный период"""
        return await self.db.get_financial_stats(days=days)

    async def get_daily_stats(self, days: int) -> List[Dict[str, Any]]:
        """Получить ежедневную статистику"""
        return await self.db.get_daily_stats(days=days)

    async def get_recent_records(self, limit: int = 20) -> List[Any]:
        """Получить последние финансовые записи"""
        return await self.db.get_recent_financial_records(limit=limit)

    async def add_expense(self, amount: float, description: str, admin_id: int) -> int:
        """Добавить расход"""
        return await self.db.add_financial_record(
            record_type='expense',
            category='operational',
            amount=amount,
            description=description,
            created_by=admin_id
        )

    async def get_exchange_rates(self, force_refresh: bool = False) -> Dict[str, float]:
        """Получить текущие курсы валют"""
        btc = await crypto_api.get_btc_price_rub(force_refresh=force_refresh)
        ltc = await crypto_api.get_ltc_price_rub(force_refresh=force_refresh)
        return {"BTC": btc, "LTC": ltc}

    async def get_total_volume(self) -> float:
        """Общий оборот"""
        stats = await self.db.get_financial_stats(days=365)
        return stats['trading_volume']

    async def get_total_fees(self) -> float:
        """Общая сумма комиссий"""
        stats = await self.db.get_financial_stats(days=365)
        return stats['revenue']