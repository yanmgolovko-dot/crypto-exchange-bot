# bot/services/crypto_wallets.py
import logging
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Tuple

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

_DUST_SAT = 546
BALANCE_CACHE_TTL_MINUTES = 10
NETWORK_FEE_CACHE_TTL_SECONDS = 60

_DEFAULT_NETWORK_FEE_SAT = {'BTC': 800, 'LTC': 2000}


class BitcoinServiceBlockCypher:
    """Сервис для работы с Bitcoin через несколько API (fallback)."""

    BLOCKCYPHER_API_URL = "https://api.blockcypher.com/v1/btc/main"
    BLOCKSTREAM_API_URL = "https://blockstream.info/api"
    MEMPOOL_API_URL = "https://mempool.space/api"

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

    async def _get_balance_blockstream(self, address: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.BLOCKSTREAM_API_URL}/address/{address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    chain = data.get("chain_stats", {})
                    mempool = data.get("mempool_stats", {})
                    balance_sat = (
                        chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
                        + mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
                    )
                    logger.info(f"Blockstream BTC баланс {address[:10]}...: {balance_sat} sat")
                    return balance_sat / 1e8
                logger.warning(f"Blockstream вернул {resp.status} для {address[:10]}...")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"Blockstream timeout для {address[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"Blockstream ошибка для {address[:10]}...: {e}")
            return None

    async def _get_balance_mempool(self, address: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.MEMPOOL_API_URL}/address/{address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    chain = data.get("chain_stats", {})
                    mempool = data.get("mempool_stats", {})
                    balance_sat = (
                        chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
                        + mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
                    )
                    logger.info(f"mempool.space BTC баланс {address[:10]}...: {balance_sat} sat")
                    return balance_sat / 1e8
                logger.warning(f"mempool.space вернул {resp.status} для {address[:10]}...")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"mempool.space timeout для {address[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"mempool.space ошибка для {address[:10]}...: {e}")
            return None

    async def _get_balance_blockcypher(self, address: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.BLOCKCYPHER_API_URL}/addrs/{address}/balance"
            params = {"token": self.api_token}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_sat = data.get("final_balance", 0)
                    if isinstance(balance_sat, str):
                        balance_sat = int(balance_sat)
                    logger.info(f"BlockCypher BTC баланс {address[:10]}...: {balance_sat} sat")
                    return balance_sat / 1e8
                logger.warning(f"BlockCypher вернул {resp.status} для {address[:10]}...")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"BlockCypher timeout для {address[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"BlockCypher ошибка для {address[:10]}...: {e}")
            return None

    async def get_balance(self, address: str) -> float:
        """Получить баланс BTC с fallback. :raises RuntimeError если все упали."""
        for provider_name, func in [
            ("Blockstream", self._get_balance_blockstream),
            ("mempool.space", self._get_balance_mempool),
            ("BlockCypher", self._get_balance_blockcypher),
        ]:
            result = await func(address)
            if result is not None:
                return result
        logger.error(f"Все провайдеры BTC недоступны для {address[:10]}...")
        raise RuntimeError(f"All BTC balance providers failed for {address[:10]}...")

    async def get_utxo(self, address: str) -> List[Dict]:
        """Получить UTXO для адреса (сначала Blockstream, потом BlockCypher)."""
        # 1. Пытаемся через Blockstream (самый надежный)
        try:
            session = await self._get_session()
            url = f"{self.BLOCKSTREAM_API_URL}/address/{address}/utxo"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    utxos = [{
                        "txid": tx["txid"],
                        "vout": tx["vout"],
                        "satoshis": tx["value"],
                        "confirmations": 1 if tx.get("status", {}).get("confirmed", False) else 0
                    } for tx in data]
                    logger.info(f"Blockstream UTXO для {address[:10]}...: {len(utxos)} шт.")
                    return utxos
        except Exception as e:
            logger.warning(f"Blockstream UTXO ошибка для {address[:10]}...: {e}")

        # 2. Fallback на BlockCypher (с добавлением неподтвержденных)
        try:
            session = await self._get_session()
            url = f"{self.BLOCKCYPHER_API_URL}/addrs/{address}?unspentOnly=true&token={self.api_token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    txrefs = data.get("txrefs", [])
                    unconfirmed = data.get("unconfirmed_txrefs", [])
                    all_tx = txrefs + unconfirmed  # ВАЖНО: берем и неподтвержденные
                    
                    utxos = [{
                        "txid": tx["tx_hash"],
                        "vout": tx["tx_output_n"],
                        "satoshis": tx["value"],
                        "confirmations": tx.get("confirmations", 0)
                    } for tx in all_tx]
                    logger.info(f"BlockCypher UTXO для {address[:10]}...: {len(utxos)} шт. (вкл. unconfirmed)")
                    return utxos
                logger.error(f"Ошибка получения UTXO BlockCypher: {resp.status}")
                return []
        except Exception as e:
            logger.error(f"Ошибка получения UTXO BlockCypher: {e}")
            return []

    async def send_transaction(self, from_privkey_wif: str, to_address: str,
                               amount_btc: float, fee_sat: int) -> str:
        if not BITCOINLIB_AVAILABLE:
            raise Exception("bitcoinlib не установлен")
        logger.info("=== send_transaction Bitcoin BlockCypher START ===")
        logger.info(f"to_address: {to_address}")
        logger.info(f"amount_btc: {amount_btc}")
        
        key = Key(import_key=from_privkey_wif, network='bitcoin')
        from_address = key.address()
        logger.info(f"from_address: {from_address}")
        
        utxos = await self.get_utxo(from_address)
        if not utxos:
            raise Exception("Нет UTXO")
            
        logger.info(f"Найдено UTXO: {len(utxos)}")
        for utxo in utxos:
            logger.info(f"UTXO: {utxo['txid']}:{utxo['vout']} = {utxo['satoshis']} satoshis")
            
        amount_sat = int(round(amount_btc * 1e8))
        logger.info(f"Фиксированная комиссия сети (BTC): {fee_sat} satoshis")
        
        t = Transaction(network='bitcoin', fee=fee_sat)
        total_input_sat = 0
        for utxo in utxos:
            t.add_input(
                prev_txid=utxo["txid"],
                output_n=utxo["vout"],
                keys=[key],
                value=utxo["satoshis"],
            )
            total_input_sat += utxo["satoshis"]
            
        change_sat = total_input_sat - amount_sat - fee_sat
        if change_sat < 0:
            raise Exception(
                f"Недостаточно средств на кошельке: требуется "
                f"{amount_sat + fee_sat} sat, доступно {total_input_sat} sat"
            )
            
        t.add_output(address=to_address, value=amount_sat)
        if change_sat > _DUST_SAT:
            t.add_output(address=from_address, value=change_sat)
            logger.info(f"Добавлена сдача: {change_sat} sat на {from_address}")
        elif change_sat > 0:
            logger.info(f"Сдача {change_sat} sat ≤ dust-порога уходит в комиссию")
        else:
            logger.info("Сдача = 0, UTXO израсходованы полностью")
            
        # Подписываем транзакцию
        txid = t.sign(keys=[key])
        
        # ЖЕЛЕЗОБЕТОННАЯ ЗАЩИТА: если библиотека вернула None (баг API), берем хеш из самого объекта
        if not txid:
            txid = getattr(t, 'txid', None)
            
        if not txid:
            raise Exception("Ошибка библиотеки: не удалось получить хеш подписанной транзакции")
            
        logger.info(f"Транзакция успешно подписана и отправлена, txid: {txid}")
        return str(txid)


class LitecoinServiceBlockCypher(BitcoinServiceBlockCypher):
    """Сервис для работы с Litecoin через несколько API (fallback)."""

    BLOCKCYPHER_API_URL = "https://api.blockcypher.com/v1/ltc/main"
    LITECOINSPACE_API_URL = "https://litecoinspace.org/api"
    BLOCKCHAIR_API_URL = "https://api.blockchair.com/litecoin/dashboards/address"

    async def _get_balance_litecoinspace(self, address: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.LITECOINSPACE_API_URL}/address/{address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    chain = data.get("chain_stats", {})
                    mempool = data.get("mempool_stats", {})
                    balance_sat = (
                        chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
                        + mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
                    )
                    logger.info(f"litecoinspace LTC баланс {address[:10]}...: {balance_sat} sat")
                    return balance_sat / 1e8
                logger.warning(f"litecoinspace вернул {resp.status} для {address[:10]}...")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"litecoinspace timeout для {address[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"litecoinspace ошибка для {address[:10]}...: {e}")
            return None

    async def _get_balance_blockchair(self, address: str) -> Optional[float]:
        try:
            session = await self._get_session()
            url = f"{self.BLOCKCHAIR_API_URL}/{address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    addr_data = data.get("data", {}).get(address, {}).get("address", {})
                    balance_sat = addr_data.get("balance", 0)
                    logger.info(f"Blockchair LTC баланс {address[:10]}...: {balance_sat} sat")
                    return balance_sat / 1e8
                logger.warning(f"Blockchair вернул {resp.status} для {address[:10]}...")
                return None
        except asyncio.TimeoutError:
            logger.warning(f"Blockchair timeout для {address[:10]}...")
            return None
        except Exception as e:
            logger.warning(f"Blockchair ошибка для {address[:10]}...: {e}")
            return None

    async def get_balance(self, address: str) -> float:
        """Получить баланс LTC с fallback. :raises RuntimeError если все упали."""
        for provider_name, func in [
            ("litecoinspace", self._get_balance_litecoinspace),
            ("Blockchair", self._get_balance_blockchair),
            ("BlockCypher", self._get_balance_blockcypher),
        ]:
            result = await func(address)
            if result is not None:
                return result
        logger.error(f"Все провайдеры LTC недоступны для {address[:10]}...")
        raise RuntimeError(f"All LTC balance providers failed for {address[:10]}...")

    async def get_utxo(self, address: str) -> List[Dict]:
        """Получить UTXO для LTC (сначала litecoinspace, потом BlockCypher)."""
        # 1. Пытаемся через litecoinspace
        try:
            session = await self._get_session()
            url = f"{self.LITECOINSPACE_API_URL}/address/{address}/utxo"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    utxos = [{
                        "txid": tx["txid"],
                        "vout": tx["vout"],
                        "satoshis": tx["value"],
                        "confirmations": 1 if tx.get("status", {}).get("confirmed", False) else 0
                    } for tx in data]
                    logger.info(f"litecoinspace UTXO для {address[:10]}...: {len(utxos)} шт.")
                    return utxos
        except Exception as e:
            logger.warning(f"litecoinspace UTXO ошибка для {address[:10]}...: {e}")

        # 2. Fallback на BlockCypher
        try:
            session = await self._get_session()
            url = f"{self.BLOCKCYPHER_API_URL}/addrs/{address}?unspentOnly=true&token={self.api_token}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    txrefs = data.get("txrefs", [])
                    unconfirmed = data.get("unconfirmed_txrefs", [])
                    all_tx = txrefs + unconfirmed
                    
                    utxos = [{
                        "txid": tx["tx_hash"],
                        "vout": tx["tx_output_n"],
                        "satoshis": tx["value"],
                        "confirmations": tx.get("confirmations", 0)
                    } for tx in all_tx]
                    logger.info(f"BlockCypher UTXO для {address[:10]}...: {len(utxos)} шт. (вкл. unconfirmed)")
                    return utxos
                logger.error(f"Ошибка получения UTXO LTC BlockCypher: {resp.status}")
                return []
        except Exception as e:
            logger.error(f"Ошибка получения UTXO LTC BlockCypher: {e}")
            return []

    async def send_transaction(self, from_privkey_wif: str, to_address: str,
                               amount_ltc: float, fee_sat: int) -> str:
        if not BITCOINLIB_AVAILABLE:
            raise Exception("bitcoinlib не установлен")
        logger.info("=== send_transaction Litecoin BlockCypher START ===")
        logger.info(f"to_address: {to_address}")
        logger.info(f"amount_ltc: {amount_ltc}")
        
        key = Key(import_key=from_privkey_wif, network='litecoin')
        from_address = key.address()
        logger.info(f"from_address: {from_address}")
        
        utxos = await self.get_utxo(from_address)
        if not utxos:
            raise Exception("Нет UTXO")
            
        logger.info(f"Найдено UTXO: {len(utxos)}")
        for utxo in utxos:
            logger.info(f"UTXO: {utxo['txid']}:{utxo['vout']} = {utxo['satoshis']} satoshis")
            
        amount_sat = int(round(amount_ltc * 1e8))
        logger.info(f"Фиксированная комиссия сети (LTC): {fee_sat} satoshis")
        
        t = Transaction(network='litecoin', fee=fee_sat)
        total_input_sat = 0
        for utxo in utxos:
            t.add_input(
                prev_txid=utxo["txid"],
                output_n=utxo["vout"],
                keys=[key],
                value=utxo["satoshis"],
            )
            total_input_sat += utxo["satoshis"]
            
        change_sat = total_input_sat - amount_sat - fee_sat
        if change_sat < 0:
            raise Exception(
                f"Недостаточно средств на кошельке: требуется "
                f"{amount_sat + fee_sat} sat, доступно {total_input_sat} sat"
            )
            
        t.add_output(address=to_address, value=amount_sat)
        if change_sat > _DUST_SAT:
            t.add_output(address=from_address, value=change_sat)
            logger.info(f"Добавлена сдача: {change_sat} sat на {from_address}")
        elif change_sat > 0:
            logger.info(f"Сдача {change_sat} sat ≤ dust-порога уходит в комиссию")
        else:
            logger.info("Сдача = 0, UTXO израсходованы полностью")
            
        # Подписываем транзакцию
        txid = t.sign(keys=[key])
        
        # ЖЕЛЕЗОБЕТОННАЯ ЗАЩИТА
        if not txid:
            txid = getattr(t, 'txid', None)
            
        if not txid:
            raise Exception("Ошибка библиотеки: не удалось получить хеш подписанной транзакции")
            
        logger.info(f"Транзакция успешно подписана и отправлена, txid: {txid}")
        return str(txid)


class CryptoWalletManager:
    """Главный менеджер, объединяющий работу с Bitcoin и Litecoin кошельками."""

    def __init__(self):
        self.btc = BitcoinServiceBlockCypher(config.BLOCKCYPHER_TOKEN)
        self.ltc = LitecoinServiceBlockCypher(config.BLOCKCYPHER_TOKEN)
        self._wallet_locks: Dict[int, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._fee_cache: Dict[str, Tuple[int, float]] = {}

    async def get_fixed_fee_sat(self, crypto_type: str) -> int:
        """Читает фиксированную комиссию сети из system_settings (с кэшем 60 сек)."""
        now = time.time()
        cached = self._fee_cache.get(crypto_type)
        if cached and (now - cached[1]) < NETWORK_FEE_CACHE_TTL_SECONDS:
            return cached[0]

        setting_key = f'network_fee_{crypto_type.lower()}_sat'
        default = _DEFAULT_NETWORK_FEE_SAT.get(crypto_type, 0)
        try:
            value = await db.get_setting(setting_key, str(default))
            fee = int(value)
        except (ValueError, TypeError):
            logger.warning(f"Некорректное значение {setting_key}, использую default={default}")
            fee = default
        self._fee_cache[crypto_type] = (fee, now)
        return fee

    def invalidate_fee_cache(self):
        """Сбрасывает кэш комиссий (вызывается админом при изменении)."""
        self._fee_cache.clear()

    async def _get_wallet_lock(self, wallet_id: int) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._wallet_locks.get(wallet_id)
            if lock is None:
                lock = asyncio.Lock()
                self._wallet_locks[wallet_id] = lock
            return lock

    @staticmethod
    def _is_cache_fresh(wallet: Wallet) -> bool:
        """Проверяет, что last_balance_check не старше BALANCE_CACHE_TTL_MINUTES."""
        if not wallet.last_balance_check:
            return False

        last = wallet.last_balance_check
        if isinstance(last, datetime):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        else:
            try:
                last = datetime.strptime(
                    str(last), '%Y-%m-%d %H:%M:%S'
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Не удалось распарсить last_balance_check кошелька #{wallet.id} "
                    f"({wallet.last_balance_check!r}, type={type(wallet.last_balance_check).__name__}): {e}"
                )
                return False

        return (datetime.now(timezone.utc) - last) < timedelta(minutes=BALANCE_CACHE_TTL_MINUTES)

    async def _fetch_and_cache_balance(self, wallet: Wallet, force: bool) -> Dict:
        if not force and self._is_cache_fresh(wallet):
            logger.debug(
                f"Баланс кошелька #{wallet.id} из кэша "
                f"(last_balance_check={wallet.last_balance_check})"
            )
            return {'success': True, 'balance': wallet.balance}

        lock = await self._get_wallet_lock(wallet.id)
        async with lock:
            fresh_wallet = await db.get_wallet(wallet_id=wallet.id)
            if not fresh_wallet:
                return {'success': False, 'error': 'Wallet not found'}
            if not force and self._is_cache_fresh(fresh_wallet):
                logger.debug(
                    f"Баланс кошелька #{fresh_wallet.id} из кэша после lock "
                    f"(last_balance_check={fresh_wallet.last_balance_check})"
                )
                return {'success': True, 'balance': fresh_wallet.balance}

            try:
                if fresh_wallet.crypto_type == 'BTC':
                    balance = await self.btc.get_balance(fresh_wallet.address)
                elif fresh_wallet.crypto_type == 'LTC':
                    balance = await self.ltc.get_balance(fresh_wallet.address)
                else:
                    return {
                        'success': False,
                        'error': f'Unsupported crypto type: {fresh_wallet.crypto_type}',
                    }
            except Exception as e:
                logger.error(
                    f"Ошибка получения баланса кошелька #{fresh_wallet.id}: {e}",
                    exc_info=True,
                )
                return {'success': False, 'error': str(e)}

            await db.update_wallet_balance(fresh_wallet.id, balance, 0)
            logger.info(f"Баланс кошелька #{fresh_wallet.id} обновлён: {balance}")
            return {'success': True, 'balance': balance}

    async def get_wallet(self, crypto_type: str = None, wallet_id: int = None):
        return await db.get_wallet(wallet_id=wallet_id, crypto_type=crypto_type)

    async def get_all_wallets(self, crypto_type: str = None) -> List:
        return await db.get_all_wallets(crypto_type)

    async def add_wallet(self, crypto_type: str, address: str, private_key: str, label: str = None) -> int:
        return await db.add_wallet(crypto_type, address, private_key, label)

    async def update_balance(self, wallet_id: int, force: bool = False) -> Dict:
        logger.info(f"Обновление баланса кошелька #{wallet_id} (force={force})")
        wallet = await db.get_wallet(wallet_id=wallet_id)
        if not wallet:
            return {'success': False, 'error': 'Wallet not found'}
        return await self._fetch_and_cache_balance(wallet, force)

    async def check_sufficient_funds(
        self, crypto_type: str, amount: float, force: bool = False
    ) -> Tuple[bool, float]:
        logger.info(f"Проверка наличия средств для {crypto_type}, необходимо {amount}")
        wallet = await db.get_wallet(crypto_type=crypto_type)
        if not wallet:
            return False, 0.0
        result = await self._fetch_and_cache_balance(wallet, force)
        if not result.get('success'):
            logger.warning(
                f"Не удалось получить баланс {crypto_type} для проверки средств: "
                f"{result.get('error')}"
            )
            return False, 0.0

        balance = result['balance']
        fee_sat = await self.get_fixed_fee_sat(crypto_type)
        required = amount + (fee_sat / 1e8)
        return balance >= required, balance

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
            fee_sat = await self.get_fixed_fee_sat(crypto_type)
            if crypto_type == 'BTC':
                txid = await self.btc.send_transaction(private_key_wif, to_address, amount, fee_sat)
            elif crypto_type == 'LTC':
                txid = await self.ltc.send_transaction(private_key_wif, to_address, amount, fee_sat)
            else:
                return {'success': False, 'error': f'Unsupported crypto type: {crypto_type}'}
            logger.info(f"Транзакция отправлена, txid: {txid}")
            return {'success': True, 'tx_hash': txid}
        except Exception as e:
            logger.error(f"Ошибка отправки транзакции: {e}")
            return {'success': False, 'error': str(e)}

    async def get_transaction_history(self, limit: int = 20) -> List:
        logger.debug(f"Запрос истории транзакций, лимит {limit}")
        return await db.get_recent_crypto_transactions(limit)

    async def close(self):
        logger.info("Закрытие сессий крипто-кошельков")
        await self.btc.close()
        await self.ltc.close()


wallet_manager = CryptoWalletManager()