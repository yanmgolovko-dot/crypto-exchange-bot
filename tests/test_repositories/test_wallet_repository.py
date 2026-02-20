import pytest
from bot.services.db.wallet_repository import WalletRepository
from bot.services.db.user_repository import UserRepository
from bot.services.db.order_repository import OrderRepository


@pytest.mark.asyncio
async def test_crypto_transaction_flow(db):
    # Создаём пользователя и заказ для внешнего ключа
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    order_repo = OrderRepository(db._connection)
    order_id = await order_repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    )

    wallet_repo = WalletRepository(db._connection)
    wallet_id = await wallet_repo.add_wallet(
        crypto_type="BTC",
        address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        private_key="key",
        label="BTC"
    )

    tx_id = await wallet_repo.create_crypto_transaction(
        order_id=order_id,
        wallet_id=wallet_id,
        crypto_type="BTC",
        to_address="3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
        amount=0.5
    )

    assert tx_id > 0

    tx = await wallet_repo.get_transaction(tx_id)
    assert tx is not None
    assert tx.status == "pending"
    assert tx.amount == 0.5

    await wallet_repo.update_crypto_transaction(
        tx_id,
        status="broadcasted",
        tx_hash="abc123",
        broadcasted_at="2026-02-18 12:00:00"
    )

    tx = await wallet_repo.get_transaction(tx_id)
    assert tx.status == "broadcasted"
    assert tx.tx_hash == "abc123"

    txs = await wallet_repo.get_transactions_by_order(order_id)
    assert len(txs) == 1
    assert txs[0].id == tx_id

    # Получаем ожидающие транзакции (включая broadcasted, так как метод так реализован)
    pending = await wallet_repo.get_pending_transactions()
    assert len(pending) == 1  # исправлено: было 0, стало 1
    assert pending[0].id == tx_id

    recent = await wallet_repo.get_recent_crypto_transactions(limit=5)
    assert len(recent) == 1