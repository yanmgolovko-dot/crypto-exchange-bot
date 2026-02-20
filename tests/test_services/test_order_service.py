import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.services.order_service import OrderService


@pytest.mark.asyncio
async def test_calculate_order_rub():
    """Тест расчёта заявки при вводе в рублях."""
    db_mock = MagicMock()
    crypto_api_mock = AsyncMock()
    crypto_api_mock.get_btc_price_rub.return_value = 5_000_000
    crypto_api_mock.get_ltc_price_rub.return_value = 10_000

    # Мокаем получение комиссии из БД
    db_mock.get_exchange_fee = AsyncMock(return_value=2.5)

    service = OrderService(db_mock, crypto_api_mock)

    result = await service.calculate_order(
        crypto_type="BTC",
        input_type="rub",
        amount=10000,
        discount_percent=0
    )

    assert result is not None
    assert result['net_amount'] == 10000
    assert result['gross_amount'] == 10300
    assert result['amount_crypto'] == pytest.approx(0.002, rel=1e-3)
    assert result['fee_percent'] == 2.5
    assert result['fee_amount'] == 300


@pytest.mark.asyncio
async def test_calculate_order_crypto():
    """Тест расчёта заявки при вводе в крипте."""
    db_mock = MagicMock()
    crypto_api_mock = AsyncMock()
    crypto_api_mock.get_btc_price_rub.return_value = 5_000_000
    db_mock.get_exchange_fee = AsyncMock(return_value=2.5)

    service = OrderService(db_mock, crypto_api_mock)

    result = await service.calculate_order(
        crypto_type="BTC",
        input_type="crypto",
        amount=0.1,
        discount_percent=0
    )

    assert result is not None
    assert result['net_amount'] == pytest.approx(500_000, rel=1e-3)  # 0.1 * 5e6 = 500k
    assert result['gross_amount'] == 512_500  # округление до 100: 500000*1.025 = 512500, ceil(5125)?? Ожидаем 512500, т.к. 512500/100 = 5125.0, ceil = 5125, *100 = 512500
    assert result['amount_crypto'] == 0.1
    assert result['fee_amount'] == pytest.approx(12500, rel=1e-3)