# bot/services/crypto_wallets.py
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# Для Bitcoin (старый сервис через cryptos)
try:
    from cryptos import *
    CRYPTOS_AVAILABLE = True
except ImportError:
    CRYPTOS_AVAILABLE = False
    logging.warning("⚠️ cryptos не установлен. Установите: pip install cryptos")

# Для Litecoin используем bitcoinlib (чистый Python) + BlockCypher
try:
    from bitcoinlib.transactions import Transaction
    from bitcoinlib.keys import Key
    BITCOINLIB_AVAILABLE = True
except ImportError:
    BITCOINLIB_AVAILABLE = False
    logging.warning("⚠️ bitcoinlib не установлен. Установите: pip install bitcoinlib")

from bot.services.db import db
from bot.services.db.wallet_repository import Wallet
from bot.utils.encryption import decrypt_private_key
from bot.config.settings import config

logger = logging.getLogger(__name__)


# ==================== BitcoinService (старый, через cryptos) ====================
class BitcoinService:
    """Обёртка над cryptos для работы с Bitcoin. Подключается к ElectrumX серверам."""

    DEFAULT_SERVERS = [
        ('electrum.blockstream.info', 50002, 'ssl'),
        ('electrum.emzy.de', 50002, 'ssl'),
        ('electrum.bitaroo.net', 50002, 'ssl'),
        ('btc.electrumx.be', 50002, 'ssl'),
    ]

    def __init__(self, testnet=False, servers=None):
        self.testnet = testnet
        self.servers = servers or self.DEFAULT_SERVERS
        self.coin = None
        self._init_coin()

    def _init_coin(self):
        """Пытается подключиться к одному из серверов ElectrumX."""
        for server in self.servers:
            try:
                if self.testnet:
                    self.coin = Bitcoin(testnet=True)
                else:
                    self.coin = Bitcoin(servers=[server])
                # Проверяем соединение, запросив баланс известного адреса
                self.coin.get_balance("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
                logger.info(f"Bitcoin service подключён к {server}")
                return
            except Exception as e:
                logger.warning(f"Не удалось подключиться к {server}: {e}")
                continue
        logger.error("Не удалось подключиться ни к одному ElectrumX серверу для Bitcoin. Функции кошелька будут недоступны.")
        self.coin = None

    def get_balance(self, address):
        """Возвращает баланс адреса в BTC."""
        if self.coin is None:
            logger.error("Bitcoin service не инициализирован")
            return 0.0
        try:
            result = self.coin.get_balance(address)
            if isinstance(result, dict):
                if 'balance' in result:
                    return result['balance'] / 1e8
                elif 'confirmed' in result:
                    return result['confirmed'] / 1e8
                else:
                    logger.error(f"Неожиданный формат баланса: {result}")
                    return 0.0
            elif isinstance(result, (int, float)):
                return float(result)
            else:
                logger.error(f"Неожиданный формат баланса: {result}")
                return 0.0
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return 0.0

    def get_unspent(self, address):
        """Возвращает список UTXO для адреса."""
        if self.coin is None:
            logger.error("Bitcoin service не инициализирован")
            return []
        try:
            return self.coin.unspent(address)
        except Exception as e:
            logger.error(f"Ошибка получения UTXO: {e}")
            return []

    def create_transaction(self, from_address, to_address, amount_btc, private_key):
        """Создаёт и подписывает транзакцию Bitcoin, возвращает hex."""
        if self.coin is None:
            raise Exception("Bitcoin service не инициализирован")
        utxos = self.get_unspent(from_address)
        if not utxos:
            raise Exception("Нет UTXO для адреса отправителя")
        amount_satoshi = int(amount_btc * 1e8)
        outputs = [(to_address, amount_satoshi)]
        tx_hex = self.coin.mktx_with_change(
            inputs=utxos,
            outputs=outputs,
            privkey=private_key,
            change_addr=from_address
        )
        return tx_hex

    def broadcast_transaction(self, tx_hex):
        """Отправляет транзакцию в сеть Bitcoin."""
        if self.coin is None:
            raise Exception("Bitcoin service не инициализирован")
        try:
            txid = self.coin.pushtx(tx_hex)
            return txid
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            return None


# ==================== LitecoinService через BlockCypher ====================
class LitecoinServiceBlockCypher:
    """Сервис для работы с Litecoin через BlockCypher API (не требует RPC)."""

    API_URL = "https://api.blockcypher.com/v1/ltc/main"

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def get_balance(self, address: str) -> float:
        """Получить баланс адреса в LTC через BlockCypher."""
        try:
            session = await self._get_session()
            url = f"{self.API_URL}/addrs/{address}/balance"
            params = {"token": self.api_token}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_sat = data.get("balance", 0)
                    if isinstance(balance_sat, str):
                        balance_sat = int(balance_sat)
                    return balance_sat / 1e8
                else:
                    logger.error(f"Ошибка BlockCypher: {resp.status}")
                    return 0.0
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return 0.0

    async def get_utxo(self, address: str) -> List[Dict]:
        """Получить UTXO для адреса через BlockCypher."""
        try:
            session = await self._get_session()
            url = f"{self.API_URL}/addrs/{address}?unspentOnly=true&token={self.api_token}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    txrefs = data.get("txrefs", [])
                    utxos = []
                    for tx in txrefs:
                        utxos.append({
                            "txid": tx["tx_hash"],
                            "vout": tx["tx_output_n"],
                            "satoshis": tx["value"],
                            "confirmations": tx.get("confirmations", 0)
                        })
                    return utxos
                else:
                    logger.error(f"Ошибка получения UTXO: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Ошибка получения UTXO: {e}")
            return []

    async def send_transaction(self, from_privkey_wif: str, to_address: str, amount_ltc: float) -> str:
        """
        Отправить LTC через BlockCypher:
        1. Получить UTXO для адреса отправителя.
        2. Создать и подписать транзакцию через bitcoinlib.
        3. Отправить через BlockCypher API (метод push tx).
        """
        if not BITCOINLIB_AVAILABLE:
            raise Exception("bitcoinlib не установлен")

        logger.info(f"=== send_transaction BlockCypher START ===")
        logger.info(f"to_address: {to_address}")
        logger.info(f"amount_ltc: {amount_ltc}")

        # Получаем ключ и адрес отправителя
        key = Key(import_key=from_privkey_wif, network='litecoin')
        from_address = key.address()
        logger.info(f"from_address: {from_address}")

        # Получаем UTXO
        utxos = await self.get_utxo(from_address)
        if not utxos:
            raise Exception("Нет непотраченных выходов (UTXO) для этого адреса")

        logger.info(f"Найдено UTXO: {len(utxos)}")
        for utxo in utxos:
            logger.info(f"UTXO: {utxo['txid']}:{utxo['vout']} = {utxo['satoshis']} satoshis")

        # Создаём транзакцию через bitcoinlib
        t = Transaction(network='litecoin')
        for utxo in utxos:
            t.add_input(
                prev_txid=utxo["txid"],
                output_n=utxo["vout"],
                keys=[key],
                value=utxo["satoshis"]
            )

        amount_sat = int(amount_ltc * 1e8)
        t.add_output(address=to_address, value=amount_sat)
        t.sign()

        if not t.verify():
            raise Exception("Transaction verification failed")
        logger.info("Транзакция подписана и верифицирована")

        tx_hex = t.raw_hex()
        logger.info(f"raw_hex длина: {len(tx_hex)}")

        # Отправляем через BlockCypher
        session = await self._get_session()
        push_url = f"{self.API_URL}/txs/push?token={self.api_token}"
        payload = {"tx": tx_hex}
        async with session.post(push_url, json=payload) as resp:
            if resp.status == 201:
                result = await resp.json()
                txid = result["tx"]["hash"]
                logger.info(f"✅ Транзакция отправлена, txid: {txid}")
                return txid
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка отправки BlockCypher: {resp.status} - {error_text}")


# ==================== CryptoWalletManager ====================
class CryptoWalletManager:
    """Главный менеджер, объединяющий работу с Bitcoin и Litecoin кошельками."""

    def __init__(self):
        self.btc = BitcoinService(testnet=False)
        self.ltc = LitecoinServiceBlockCypher(config.BLOCKCYPHER_TOKEN)

    async def get_wallet(self, crypto_type: str = None, wallet_id: int = None):
        """Получить кошелёк по ID или типу (возвращает первый активный по умолчанию)."""
        return await db.get_wallet(wallet_id=wallet_id, crypto_type=crypto_type)

    async def get_all_wallets(self, crypto_type: str = None) -> List:
        """Получить все кошельки (опционально по типу)."""
        return await db.get_all_wallets(crypto_type)

    async def add_wallet(self, crypto_type: str, address: str, private_key: str, label: str = None) -> int:
        """Добавить новый кошелёк (ключ будет зашифрован)."""
        return await db.add_wallet(crypto_type, address, private_key, label)

    async def update_balance(self, wallet_id: int) -> Dict:
        """Обновить баланс конкретного кошелька через соответствующий сервис."""
        logger.info(f"Обновление баланса кошелька #{wallet_id}")
        wallet = await db.get_wallet(wallet_id=wallet_id)
        if not wallet:
            logger.warning(f"Кошелёк #{wallet_id} не найден")
            return {'success': False, 'error': 'Wallet not found'}
        try:
            if wallet.crypto_type == 'BTC':
                balance = self.btc.get_balance(wallet.address)
            elif wallet.crypto_type == 'LTC':
                balance = await self.ltc.get_balance(wallet.address)
            else:
                return {'success': False, 'error': f'Unsupported crypto type: {wallet.crypto_type}'}
            await db.update_wallet_balance(wallet_id, balance, 0)
            logger.info(f"Баланс кошелька {wallet.address}: {balance} {wallet.crypto_type}")
            return {'success': True, 'balance': balance}
        except Exception as e:
            logger.error(f"Ошибка обновления баланса кошелька #{wallet_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def check_sufficient_funds(self, crypto_type: str, amount: float) -> Tuple[bool, float]:
        """Проверить, достаточно ли средств на активном кошельке (с учётом комиссии)."""
        logger.info(f"Проверка наличия средств для {crypto_type}, необходимо {amount}")
        wallet = await db.get_wallet(crypto_type=crypto_type)
        if not wallet:
            logger.warning(f"Нет активного кошелька для {crypto_type}")
            return False, 0.0
        if crypto_type == 'BTC':
            balance = self.btc.get_balance(wallet.address)
            required = amount + 0.0001
        elif crypto_type == 'LTC':
            balance = await self.ltc.get_balance(wallet.address)
            required = amount + 0.001
        else:
            return False, 0.0
        logger.info(f"Баланс: {balance}, требуется: {required}")
        return balance >= required, balance

    async def send_transaction_real(self, order_id: int, crypto_type: str,
                                    to_address: str, amount: float,
                                    wallet: Optional[Wallet] = None) -> Dict:
        """
        Отправка криптовалюты с повторными попытками.
        **Порядок действий (исправлено):**
        1. Создаётся запись в таблице crypto_transactions (статус 'pending').
        2. Выполняется отправка.
        3. При успехе запись обновляется (статус 'broadcasted', tx_hash).
        4. При ошибке запись помечается как 'failed' с сохранением ошибки.
        """
        logger.info(f"Запуск отправки криптовалюты по заявке #{order_id}, сумма {amount} {crypto_type}")
        if wallet is None:
            wallet = await db.get_wallet(crypto_type=crypto_type)
            if not wallet:
                logger.error(f"Нет активного кошелька для {crypto_type}")
                return {'success': False, 'error': f'Нет активного кошелька для {crypto_type}'}

        from_address = str(wallet.address).strip()
        to_address = str(to_address).strip()
        if not from_address or not to_address:
            return {'success': False, 'error': 'Пустой адрес'}

        try:
            private_key_wif = decrypt_private_key(wallet.private_key)
            if not private_key_wif:
                return {'success': False, 'error': 'Пустой приватный ключ'}
        except Exception as e:
            logger.error(f"Ошибка расшифровки ключа для кошелька #{wallet.id}: {e}")
            return {'success': False, 'error': f'Ошибка расшифровки ключа: {e}'}

        # ШАГ 1: Создаём запись транзакции в БД (статус pending)
        tx_db_id = await db.create_crypto_transaction(
            order_id=order_id,
            wallet_id=wallet.id,
            crypto_type=wallet.crypto_type,
            to_address=to_address,
            amount=amount
        )
        logger.info(f"Создана запись транзакции #{tx_db_id} со статусом pending")

        max_retries = 3
        txid = None

        for attempt in range(max_retries):
            try:
                if crypto_type == 'BTC':
                    if not CRYPTOS_AVAILABLE:
                        return {'success': False, 'error': 'cryptos не установлен'}
                    tx_hex = self.btc.create_transaction(
                        from_address=from_address,
                        to_address=to_address,
                        amount_btc=amount,
                        private_key=private_key_wif
                    )
                    txid = self.btc.broadcast_transaction(tx_hex)
                elif crypto_type == 'LTC':
                    txid = await self.ltc.send_transaction(private_key_wif, to_address, amount)
                else:
                    return {'success': False, 'error': f'Неподдерживаемый тип: {crypto_type}'}

                if txid:
                    logger.info(f"Транзакция отправлена, txid: {txid}")
                    break
                else:
                    raise Exception("broadcast вернул пустой txid")
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Все попытки не удались: {e}")
                    # Обновляем статус транзакции на failed
                    await db.update_crypto_transaction(
                        tx_db_id,
                        status='failed',
                        error_message=str(e)
                    )
                    logger.info(f"Статус транзакции #{tx_db_id} обновлён на failed")
                    return {'success': False, 'error': str(e)}
                wait = 2 ** attempt
                logger.warning(f"Попытка {attempt+1} не удалась: {e}, повтор через {wait} сек")
                await asyncio.sleep(wait)

        if not txid:
            await db.update_crypto_transaction(
                tx_db_id,
                status='failed',
                error_message='Не удалось отправить транзакцию после нескольких попыток'
            )
            logger.info(f"Статус транзакции #{tx_db_id} обновлён на failed")
            return {'success': False, 'error': 'Не удалось отправить транзакцию после нескольких попыток'}

        # ШАГ 3: Обновляем запись транзакции (статус broadcasted, tx_hash)
        await db.update_crypto_transaction(
            tx_db_id,
            status='broadcasted',
            tx_hash=txid,
            broadcasted_at=datetime.now().isoformat(),
            fee_paid=0
        )
        logger.info(f"Статус транзакции #{tx_db_id} обновлён на broadcasted, tx_hash={txid}")

        asyncio.create_task(self.update_balance(wallet.id))
        logger.info(f"✅ Транзакция по заявке #{order_id} успешно отправлена, tx_hash={txid}")
        return {'success': True, 'tx_hash': txid}

    async def get_transaction_history(self, limit: int = 20) -> List:
        """Получить историю транзакций (последние limit)."""
        logger.debug(f"Запрос истории транзакций, лимит {limit}")
        return await db.get_recent_crypto_transactions(limit)

    async def close(self):
        """Закрыть все сессии."""
        logger.info("Закрытие сессий крипто-кошельков")
        if hasattr(self.ltc, 'close'):
            await self.ltc.close()


wallet_manager = CryptoWalletManager()