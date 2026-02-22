# bot/services/crypto_wallets.py
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, List, Tuple

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


# ==================== BitcoinService через BlockCypher ====================
class BitcoinServiceBlockCypher:
    """Сервис для работы с Bitcoin через BlockCypher API (не требует Electrum)."""

    API_URL = "https://api.blockcypher.com/v1/btc/main"

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
        """Получить баланс адреса в BTC через BlockCypher."""
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

    async def send_transaction(self, from_privkey_wif: str, to_address: str, amount_btc: float) -> str:
        """
        Отправить BTC через BlockCypher:
        1. Получить UTXO для адреса отправителя.
        2. Создать и подписать транзакцию через bitcoinlib.
        3. Отправить через BlockCypher API (метод push tx).
        """
        if not BITCOINLIB_AVAILABLE:
            raise Exception("bitcoinlib не установлен")

        logger.info(f"=== send_transaction Bitcoin BlockCypher START ===")
        logger.info(f"to_address: {to_address}")
        logger.info(f"amount_btc: {amount_btc}")

        # Получаем ключ и адрес отправителя
        key = Key(import_key=from_privkey_wif, network='bitcoin')
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
        t = Transaction(network='bitcoin')
        for utxo in utxos:
            t.add_input(
                prev_txid=utxo["txid"],
                output_n=utxo["vout"],
                keys=[key],
                value=utxo["satoshis"]
            )

        amount_sat = int(amount_btc * 1e8)
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


# ==================== LitecoinService через BlockCypher ====================
class LitecoinServiceBlockCypher:
    """Сервис для работы с Litecoin через BlockCypher API."""

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
        try:
            session = await self._get_session()
            url = f"{self.API_URL}/addrs/{address}/balance"
            params = {"token": self.api_token}
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_sat = data.get("balance", 0)
                    return balance_sat / 1e8
                else:
                    return 0.0
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return 0.0

    async def get_utxo(self, address: str) -> List[Dict]:
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
                    return []
        except Exception as e:
            logger.error(f"Ошибка получения UTXO: {e}")
            return []

    async def send_transaction(self, from_privkey_wif: str, to_address: str, amount_ltc: float) -> str:
        if not BITCOINLIB_AVAILABLE:
            raise Exception("bitcoinlib не установлен")

        logger.info(f"=== send_transaction Litecoin BlockCypher START ===")
        key = Key(import_key=from_privkey_wif, network='litecoin')
        from_address = key.address()
        utxos = await self.get_utxo(from_address)
        if not utxos:
            raise Exception("Нет UTXO")

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

        tx_hex = t.raw_hex()
        session = await self._get_session()
        push_url = f"{self.API_URL}/txs/push?token={self.api_token}"
        payload = {"tx": tx_hex}
        async with session.post(push_url, json=payload) as resp:
            if resp.status == 201:
                result = await resp.json()
                txid = result["tx"]["hash"]
                return txid
            else:
                error_text = await resp.text()
                raise Exception(f"Ошибка отправки BlockCypher: {resp.status} - {error_text}")


# ==================== CryptoWalletManager ====================
class CryptoWalletManager:
    """Главный менеджер, объединяющий работу с Bitcoin и Litecoin кошельками через BlockCypher."""

    def __init__(self):
        self.btc = BitcoinServiceBlockCypher(config.BLOCKCYPHER_TOKEN)
        self.ltc = LitecoinServiceBlockCypher(config.BLOCKCYPHER_TOKEN)

    async def get_wallet(self, crypto_type: str = None, wallet_id: int = None):
        return await db.get_wallet(wallet_id=wallet_id, crypto_type=crypto_type)

    async def get_all_wallets(self, crypto_type: str = None) -> List:
        return await db.get_all_wallets(crypto_type)

    async def add_wallet(self, crypto_type: str, address: str, private_key: str, label: str = None) -> int:
        return await db.add_wallet(crypto_type, address, private_key, label)

    async def update_balance(self, wallet_id: int) -> Dict:
        logger.info(f"Обновление баланса кошелька #{wallet_id}")
        wallet = await db.get_wallet(wallet_id=wallet_id)
        if not wallet:
            return {'success': False, 'error': 'Wallet not found'}
        try:
            if wallet.crypto_type == 'BTC':
                balance = await self.btc.get_balance(wallet.address)
            elif wallet.crypto_type == 'LTC':
                balance = await self.ltc.get_balance(wallet.address)
            else:
                return {'success': False, 'error': f'Unsupported crypto type: {wallet.crypto_type}'}
            await db.update_wallet_balance(wallet_id, balance, 0)
            return {'success': True, 'balance': balance}
        except Exception as e:
            logger.error(f"Ошибка обновления баланса кошелька #{wallet_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def check_sufficient_funds(self, crypto_type: str, amount: float) -> Tuple[bool, float]:
        logger.info(f"Проверка наличия средств для {crypto_type}, необходимо {amount}")
        wallet = await db.get_wallet(crypto_type=crypto_type)
        if not wallet:
            return False, 0.0
        try:
            if crypto_type == 'BTC':
                balance = await self.btc.get_balance(wallet.address)
                required = amount + 0.0001
            elif crypto_type == 'LTC':
                balance = await self.ltc.get_balance(wallet.address)
                required = amount + 0.001
            else:
                return False, 0.0
            return balance >= required, balance
        except Exception as e:
            logger.error(f"Ошибка проверки средств: {e}")
            return False, 0.0

    async def send_transaction_real(self, order_id: int, crypto_type: str,
                                    to_address: str, amount: float,
                                    wallet: Optional[Wallet] = None) -> Dict:
        logger.info(f"Запуск отправки криптовалюты по заявке #{order_id}, сумма {amount} {crypto_type}")
        if wallet is None:
            wallet = await db.get_wallet(crypto_type=crypto_type)
            if not wallet:
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

        # Создаём запись транзакции в БД (статус pending)
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
                    txid = await self.btc.send_transaction(private_key_wif, to_address, amount)
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
                    await db.update_crypto_transaction(
                        tx_db_id,
                        status='failed',
                        error_message=str(e)
                    )
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
            return {'success': False, 'error': 'Не удалось отправить транзакцию после нескольких попыток'}

        # Обновляем запись транзакции (статус broadcasted, tx_hash)
        await db.update_crypto_transaction(
            tx_db_id,
            status='broadcasted',
            tx_hash=txid,
            broadcasted_at=datetime.now().isoformat(),
            fee_paid=0
        )
        logger.info(f"Статус транзакции #{tx_db_id} обновлён на broadcasted, tx_hash={txid}")

        asyncio.create_task(self.update_balance(wallet.id))
        return {'success': True, 'tx_hash': txid}

    async def get_transaction_history(self, limit: int = 20) -> List:
        logger.debug(f"Запрос истории транзакций, лимит {limit}")
        return await db.get_recent_crypto_transactions(limit)

    async def close(self):
        logger.info("Закрытие сессий крипто-кошельков")
        await self.btc.close()
        await self.ltc.close()


wallet_manager = CryptoWalletManager()