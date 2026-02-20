"""Конфигурация бота обменника криптовалют"""

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Конфигурация бота"""

    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = None

    # Комиссии и лимиты
    EXCHANGE_FEE: float = float(os.getenv("EXCHANGE_FEE", "2.5"))
    MIN_AMOUNT: float = float(os.getenv("MIN_AMOUNT", "1000"))
    MAX_AMOUNT: float = float(os.getenv("MAX_AMOUNT", "500000"))

    # Банковские реквизиты (начальные)
    BANK_CARD: str = os.getenv("BANK_CARD", "")
    BANK_NAME: str = os.getenv("BANK_NAME", "Сбербанк")
    BANK_HOLDER: str = os.getenv("BANK_HOLDER", "")

    # Кошельки (опционально, для авто-заполнения)
    BTC_WALLET: str = os.getenv("BTC_WALLET", "")
    LTC_WALLET: str = os.getenv("LTC_WALLET", "")

    # База данных
    DB_PATH: str = os.getenv("DB_PATH", "data/exchange.db")

    # Секретный ключ для шифрования приватных ключей
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "default-insecure-key-change-in-production")

    # Токен BlockCypher (опционально, больше не нужен, но оставим для совместимости)
    BLOCKCYPHER_TOKEN: str = os.getenv("BLOCKCYPHER_TOKEN", "")

    # Версия бота (начальная, будет обновляться в БД)
    BOT_VERSION: str = "0.000"

    # Время жизни кэша курсов (секунды)
    RATE_CACHE_TTL: int = int(os.getenv("RATE_CACHE_TTL", "30"))

    # Эндпоинты GetBlock для Litecoin
    LTC_RPC_URL: str = os.getenv("LTC_RPC_URL", "")
    LTC_REST_URL: str = os.getenv("LTC_REST_URL", "")

    def __post_init__(self):
        if self.ADMIN_IDS is None:
            admin_ids_str = os.getenv("ADMIN_IDS", "")
            self.ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

config = Config()