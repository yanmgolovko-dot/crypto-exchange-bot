# test_change.py
import asyncio
import logging
from unittest.mock import AsyncMock
from bot.services.crypto_wallets import LitecoinServiceBlockCypher
from bitcoinlib.keys import Key

# Включаем вывод логов в консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test():
    print("=== ТЕСТ: Проверка создания сдачи ===")
    svc = LitecoinServiceBlockCypher('dummy_token')
    
    svc.get_utxo = AsyncMock(return_value=[
        {'txid': 'a'*64, 'vout': 0, 'satoshis': 50000000, 'confirmations': 3}
    ])
    
    fake_resp = AsyncMock()
    fake_resp.status = 201
    fake_resp.json = AsyncMock(return_value={'tx': {'hash': 'fake_txid_123'}})
    
    fake_post = AsyncMock()
    fake_post.__aenter__ = AsyncMock(return_value=fake_resp)
    fake_post.__aexit__ = AsyncMock(return_value=False)
    
    fake_session = AsyncMock()
    fake_session.closed = False
    fake_session.post = lambda *a, **kw: fake_post
    svc._get_session = AsyncMock(return_value=fake_session)

    key = Key(network='litecoin')
    wif = key.wif()
    to_addr = Key(network='litecoin').address()
    
    print(f"Отправляем: 0.1 LTC")
    print(f"UTXO: 0.5 LTC (50000000 sat)")
    print(f"Комиссия: 0.001 LTC (100000 sat)")
    print(f"Ожидаемая сдача: 0.399 LTC (39900000 sat)")
    print("-" * 40)

    try:
        txid = await svc.send_transaction(wif, to_addr, 0.1)
        print(f"\n✅ УСПЕХ: txid = {txid}")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")

if __name__ == "__main__":
    asyncio.run(test())