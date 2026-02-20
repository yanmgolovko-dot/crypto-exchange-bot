import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from bot.services.db.order_repository import OrderRepository
from bot.services.db.user_repository import UserRepository


@pytest.mark.asyncio
async def test_create_order(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser", "Test", "User")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        promo_code=None,
        discount_percent=0
    )

    assert order_id > 0

    order = await repo.get_order(order_id)
    assert order is not None
    assert order.user_id == 12345
    assert order.crypto_type == "BTC"
    assert order.amount_rub == 10000
    assert order.amount_crypto == 0.002
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_get_order_not_found(db):
    repo = OrderRepository(db._connection)
    order = await repo.get_order(99999)
    assert order is None


@pytest.mark.asyncio
async def test_update_order_status(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="addr"
    )

    await repo.update_order_status(order_id, "paid", "Оплачено")
    order = await repo.get_order(order_id)
    assert order.status == "paid"
    assert order.paid_at is not None

    await repo.update_order_status(order_id, "completed", "Завершено", admin_id=999)
    order = await repo.get_order(order_id)
    assert order.status == "completed"
    assert order.completed_at is not None
    assert order.admin_checked_by == 999


@pytest.mark.asyncio
async def test_add_bank_receipt(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="addr"
    )

    receipt_path = "data/receipts/test.pdf"
    await repo.add_bank_receipt(order_id, receipt_path)

    order = await repo.get_order(order_id)
    assert order.bank_receipt == receipt_path


@pytest.mark.asyncio
async def test_get_user_orders(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    amounts = []
    for i in range(3):
        amount = 10000 + i * 1000
        amounts.append(amount)
        await repo.create_order(
            user_id=12345,
            username="testuser",
            crypto_type="BTC",
            amount_rub=amount,
            amount_crypto=0.002,
            rate=5_000_000,
            fee_percent=2.5,
            crypto_address="addr"
        )
        # Увеличиваем задержку до 1 секунды, чтобы created_at гарантированно различались
        await asyncio.sleep(1)

    orders = await repo.get_user_orders(12345, limit=10)
    assert len(orders) == 3
    # Проверяем, что заказы отсортированы по убыванию created_at (последний первый)
    # Последний созданный имеет наибольшую сумму (i=2 -> 12000)
    assert orders[0].amount_rub == max(amounts)
    # Также можно проверить, что id убывают (если автоинкремент)
    ids = [o.id for o in orders]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_get_pending_orders(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(1, "u1")
    await user_repo.add_or_update_user(2, "u2")

    repo = OrderRepository(db._connection)
    order1 = await repo.create_order(user_id=1, username="u1", crypto_type="BTC", amount_rub=1000,
                                      amount_crypto=0.001, rate=5_000_000, fee_percent=2.5,
                                      crypto_address="addr1")
    order2 = await repo.create_order(user_id=2, username="u2", crypto_type="LTC", amount_rub=2000,
                                      amount_crypto=0.2, rate=10_000, fee_percent=2.5,
                                      crypto_address="addr2")
    await repo.update_order_status(order2, "paid")

    pending = await repo.get_pending_orders()
    ids = [o.id for o in pending]
    assert order1 in ids
    assert order2 in ids


@pytest.mark.asyncio
async def test_set_order_manual_payment_details(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="addr"
    )

    details = "Карта: 1234 **** **** 5678"
    await repo.set_order_manual_payment_details(order_id, details)

    order = await repo.get_order(order_id)
    assert order.manual_payment_details == details


@pytest.mark.asyncio
async def test_update_order_tx_hash(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="addr"
    )

    tx_hash = "abcdef1234567890"
    await repo.update_order_tx_hash(order_id, tx_hash, admin_id=999)

    order = await repo.get_order(order_id)
    assert order.tx_hash == tx_hash
    assert order.admin_checked_by == 999
    assert order.admin_checked_at is not None


@pytest.mark.asyncio
async def test_pending_orders_for_reminder(db):
    user_repo = UserRepository(db._connection)
    await user_repo.add_or_update_user(12345, "testuser")

    repo = OrderRepository(db._connection)
    order_id = await repo.create_order(
        user_id=12345,
        username="testuser",
        crypto_type="BTC",
        amount_rub=10000,
        amount_crypto=0.002,
        rate=5_000_000,
        fee_percent=2.5,
        crypto_address="addr"
    )

    # Используем UTC для корректного сравнения с created_at, которое хранится в UTC
    past_time_utc = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    await db._connection.conn.execute(
        "UPDATE exchange_orders SET created_at = ? WHERE id = ?",
        (past_time_utc, order_id)
    )
    await db._connection.conn.commit()

    # Проверяем, что разница в минутах действительно больше 5, используя julianday
    cursor = await db._connection.conn.execute(
        "SELECT (julianday('now') - julianday(created_at)) * 24 * 60 FROM exchange_orders WHERE id = ?",
        (order_id,)
    )
    row = await cursor.fetchone()
    diff_minutes = row[0]
    assert diff_minutes > 5, f"Разница во времени {diff_minutes:.2f} минут, должна быть > 5"

    orders = await repo.get_pending_orders_for_reminder(minutes=5, max_reminders=3)
    ids = [o.id for o in orders]
    assert order_id in ids

    await repo.increment_reminder_count(order_id)

    order = await repo.get_order(order_id)
    assert order.reminder_count == 1
    assert order.last_reminder_at is not None