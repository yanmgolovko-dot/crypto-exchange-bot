# bot/services/crypto_api.py
"""
API для получения курсов криптовалют с кэшированием.
Поддерживает получение курсов BTC, LTC к RUB, а также USD/RUB.
"""

import aiohttp
import asyncio
import logging
import time
from typing import Optional, Dict
from bot.config.settings import config

logger = logging.getLogger(__name__)


class CryptoAPI:
    """
    Класс для работы с криптовалютными API.
    Получает курсы BTC, LTC к рублю, а также USD/RUB, кэширует результаты.
    """

    COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
    BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"

    CACHE_TTL = 60  # время жизни кэша в секундах

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache = {
            'BTC': {'price': None, 'timestamp': 0},
            'LTC': {'price': None, 'timestamp': 0},
            'USDTRUB': {'price': None, 'timestamp': 0}
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            logger.debug("Создана новая HTTP-сессия для CryptoAPI")
        return self.session

    async def _fetch_from_coingecko(self, coin_ids: str) -> Optional[Dict]:
        try:
            session = await self._get_session()
            params = {
                "ids": coin_ids,
                "vs_currencies": "rub",
                "include_24hr_change": "false"
            }
            logger.debug(f"Запрос к CoinGecko: {coin_ids}")
            async with session.get(self.COINGECKO_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Ответ CoinGecko: {data}")
                    return data
                logger.warning(f"CoinGecko вернул статус {response.status}")
                return None
        except asyncio.TimeoutError:
            logger.warning("Таймаут при запросе к CoinGecko")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения цен с CoinGecko: {e}", exc_info=True)
            return None

    async def _fetch_from_binance(self, symbol: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.BINANCE_API_URL}?symbol={symbol}"
            logger.debug(f"Запрос к Binance: {symbol}")
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data.get("price", 0))
                    logger.debug(f"Ответ Binance {symbol}: {price}")
                    return price
                logger.warning(f"Binance вернул статус {response.status} для {symbol}")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут при запросе к Binance для {symbol}")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения цены с Binance: {e}", exc_info=True)
            return None

    async def _fetch_btc_rub(self) -> Optional[float]:
        data = await self._fetch_from_coingecko("bitcoin")
        if data and "bitcoin" in data and "rub" in data["bitcoin"]:
            return data["bitcoin"]["rub"]
        btc_rub = await self._fetch_from_binance("BTCRUB")
        if btc_rub:
            return btc_rub
        btc_usdt = await self._fetch_from_binance("BTCUSDT")
        usdt_rub = await self._fetch_from_binance("USDTRUB")
        if btc_usdt and usdt_rub:
            return btc_usdt * usdt_rub
        logger.warning("Не удалось получить курс BTC/RUB ни из одного источника")
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
        logger.warning("Не удалось получить курс LTC/RUB ни из одного источника")
        return None

    async def _fetch_usdt_rub(self) -> Optional[float]:
        """Получает курс USD/RUB (USDT/RUB) с Binance."""
        usdt_rub = await self._fetch_from_binance("USDTRUB")
        if usdt_rub:
            return usdt_rub
        logger.warning("Не удалось получить курс USD/RUB")
        return None

    async def get_btc_price_rub(self, force_refresh: bool = False) -> Optional[float]:
        now = time.time()
        cache = self._cache['BTC']
        if force_refresh or not cache['price'] or (now - cache['timestamp'] > self.CACHE_TTL):
            logger.info("Обновление курса BTC/RUB")
            price = await self._fetch_btc_rub()
            if price is not None:
                self._cache['BTC'] = {'price': price, 'timestamp': now}
                logger.info(f"Курс BTC/RUB обновлён: {price:.2f}")
            else:
                logger.error("Не удалось обновить курс BTC/RUB")
            return price
        logger.debug(f"Возврат кэшированного курса BTC/RUB: {cache['price']:.2f}")
        return cache['price']

    async def get_ltc_price_rub(self, force_refresh: bool = False) -> Optional[float]:
        now = time.time()
        cache = self._cache['LTC']
        if force_refresh or not cache['price'] or (now - cache['timestamp'] > self.CACHE_TTL):
            logger.info("Обновление курса LTC/RUB")
            price = await self._fetch_ltc_rub()
            if price is not None:
                self._cache['LTC'] = {'price': price, 'timestamp': now}
                logger.info(f"Курс LTC/RUB обновлён: {price:.2f}")
            else:
                logger.error("Не удалось обновить курс LTC/RUB")
            return price
        logger.debug(f"Возврат кэшированного курса LTC/RUB: {cache['price']:.2f}")
        return cache['price']

    async def get_usdt_rub(self, force_refresh: bool = False) -> Optional[float]:
        now = time.time()
        cache = self._cache['USDTRUB']
        if force_refresh or not cache['price'] or (now - cache['timestamp'] > self.CACHE_TTL):
            logger.info("Обновление курса USD/RUB")
            price = await self._fetch_usdt_rub()
            if price is not None:
                self._cache['USDTRUB'] = {'price': price, 'timestamp': now}
                logger.info(f"Курс USD/RUB обновлён: {price:.2f}")
            else:
                logger.error("Не удалось обновить курс USD/RUB")
            return price
        logger.debug(f"Возврат кэшированного курса USD/RUB: {cache['price']:.2f}")
        return cache['price']

    async def get_all_prices(self, force_refresh: bool = False) -> Dict[str, Optional[float]]:
        logger.debug("Запрос всех курсов")
        btc = await self.get_btc_price_rub(force_refresh)
        ltc = await self.get_ltc_price_rub(force_refresh)
        usdt = await self.get_usdt_rub(force_refresh)
        return {"BTC": btc, "LTC": ltc, "USD": usdt}

    async def refresh_prices(self, force: bool = True) -> Dict[str, Optional[float]]:
        logger.info("Принудительное обновление всех курсов")
        return await self.get_all_prices(force_refresh=True)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("HTTP-сессия CryptoAPI закрыта")


crypto_api = CryptoAPI()