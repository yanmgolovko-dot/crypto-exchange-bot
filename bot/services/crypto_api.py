"""API для получения курсов криптовалют с кэшированием"""

import aiohttp
import asyncio
import logging
import time
from typing import Optional, Dict
from bot.config.settings import config

logger = logging.getLogger(__name__)


class CryptoAPI:
    """Класс для работы с криптовалютными API с кэшированием результатов"""

    COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
    BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"

    CACHE_TTL = 60  # время жизни кэша в секундах (1 минута)

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache = {
            'BTC': {'price': None, 'timestamp': 0},
            'LTC': {'price': None, 'timestamp': 0}
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _fetch_from_coingecko(self, coin_ids: str) -> Optional[Dict]:
        try:
            session = await self._get_session()
            params = {
                "ids": coin_ids,
                "vs_currencies": "rub",
                "include_24hr_change": "false"
            }
            async with session.get(self.COINGECKO_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                logger.warning(f"CoinGecko вернул статус {response.status}")
                return None
        except Exception as e:
            logger.error(f"Ошибка получения цен с CoinGecko: {e}")
            return None

    async def _fetch_from_binance(self, symbol: str) -> Optional[float]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.BINANCE_API_URL}?symbol={symbol}") as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data.get("price", 0))
                return None
        except Exception as e:
            logger.error(f"Ошибка получения цены с Binance: {e}")
            return None

    async def _fetch_btc_rub(self) -> Optional[float]:
        # Сначала пробуем CoinGecko
        data = await self._fetch_from_coingecko("bitcoin")
        if data and "bitcoin" in data and "rub" in data["bitcoin"]:
            return data["bitcoin"]["rub"]
        # Fallback: Binance BTCRUB
        btc_rub = await self._fetch_from_binance("BTCRUB")
        if btc_rub:
            return btc_rub
        # Ещё fallback: BTCUSDT * USDTRUB
        btc_usdt = await self._fetch_from_binance("BTCUSDT")
        usdt_rub = await self._fetch_from_binance("USDTRUB")
        if btc_usdt and usdt_rub:
            return btc_usdt * usdt_rub
        return None

    async def _fetch_ltc_rub(self) -> Optional[float]:
        data = await self._fetch_from_coingecko("litecoin")
        if data and "litecoin" in data and "rub" in data["litecoin"]:
            return data["litecoin"]["rub"]
        ltc_rub = await self._fetch_from_binance("LTCRUB")
        if ltc_rub:
            return ltc_rub
        ltc_usdt = await self._fetch_from_binance("LTCUSDT")
        usdt_rub = await self._fetch_from_binance("USDTRUB")
        if ltc_usdt and usdt_rub:
            return ltc_usdt * usdt_rub
        return None

    async def get_btc_price_rub(self, force_refresh: bool = False) -> Optional[float]:
        """Получить курс BTC к RUB с кэшированием"""
        now = time.time()
        cache = self._cache['BTC']
        if force_refresh or not cache['price'] or (now - cache['timestamp'] > self.CACHE_TTL):
            price = await self._fetch_btc_rub()
            if price is not None:
                self._cache['BTC'] = {'price': price, 'timestamp': now}
            return price
        return cache['price']

    async def get_ltc_price_rub(self, force_refresh: bool = False) -> Optional[float]:
        """Получить курс LTC к RUB с кэшированием"""
        now = time.time()
        cache = self._cache['LTC']
        if force_refresh or not cache['price'] or (now - cache['timestamp'] > self.CACHE_TTL):
            price = await self._fetch_ltc_rub()
            if price is not None:
                self._cache['LTC'] = {'price': price, 'timestamp': now}
            return price
        return cache['price']

    async def get_all_prices(self, force_refresh: bool = False) -> Dict[str, Optional[float]]:
        """Получить все курсы (с возможностью принудительного обновления)"""
        btc = await self.get_btc_price_rub(force_refresh)
        ltc = await self.get_ltc_price_rub(force_refresh)
        return {"BTC": btc, "LTC": ltc}

    async def refresh_prices(self, force: bool = True) -> Dict[str, Optional[float]]:
        """Принудительно обновить все курсы (для админки)"""
        return await self.get_all_prices(force_refresh=True)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


crypto_api = CryptoAPI()