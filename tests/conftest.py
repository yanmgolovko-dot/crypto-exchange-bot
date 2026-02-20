import os
import pytest
import pytest_asyncio
from aioresponses import aioresponses
from typing import AsyncGenerator

from bot.services.db import Database
from bot.services.db.init import init_db_sync
from bot.services.crypto_api import CryptoAPI
from bot.services.exchange_calculator import exchange_calculator
from bot.config.settings import config

TEST_DB_PATH = "data/test_exchange.db"
os.environ["DB_PATH"] = TEST_DB_PATH
config.DB_PATH = TEST_DB_PATH


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    init_db_sync()
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[Database, None]:
    db_instance = Database()
    await db_instance.connect()
    yield db_instance
    await db_instance.close()


@pytest.fixture
def mock_crypto_api():
    with aioresponses() as m:
        yield m


@pytest_asyncio.fixture
async def crypto_api():
    return CryptoAPI()


@pytest_asyncio.fixture
async def calculator(crypto_api):
    return exchange_calculator