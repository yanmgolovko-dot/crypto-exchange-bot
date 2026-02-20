import pytest
from unittest.mock import AsyncMock
from bot.services.exchange_calculator import ExchangeCalculator


@pytest.mark.asyncio
async def test_calculate_from_net_btc():
    mock_crypto = AsyncMock()
    mock_crypto.get_btc_price_rub.return_value = 5_000_000

    calc = ExchangeCalculator(crypto_api=mock_crypto)

    result = await calc.calculate_from_net(
        net_amount=10000,
        crypto_type="BTC",
        fee_percent=2.5
    )

    assert result is not None
    assert result['net_amount'] == 10000
    assert result['gross_amount'] == 10300
    assert result['amount_crypto'] == pytest.approx(0.002, rel=1e-3)
    assert result['crypto_type'] == "BTC"
    assert result['fee_amount'] == 300
    assert result['rate'] == 5_000_000


@pytest.mark.asyncio
async def test_calculate_from_net_ltc():
    mock_crypto = AsyncMock()
    mock_crypto.get_ltc_price_rub.return_value = 10_000

    calc = ExchangeCalculator(crypto_api=mock_crypto)

    result = await calc.calculate_from_net(
        net_amount=5000,
        crypto_type="LTC",
        fee_percent=2.5
    )

    assert result is not None
    assert result['net_amount'] == 5000
    assert result['gross_amount'] == 5200
    assert result['amount_crypto'] == pytest.approx(0.5, rel=1e-3)
    assert result['crypto_type'] == "LTC"
    assert result['fee_amount'] == 200
    assert result['rate'] == 10_000


@pytest.mark.asyncio
async def test_calculate_exchange_legacy():
    mock_crypto = AsyncMock()
    mock_crypto.get_btc_price_rub.return_value = 5_000_000

    calc = ExchangeCalculator(crypto_api=mock_crypto)

    result = await calc.calculate_exchange(amount_rub=10000, crypto_type="BTC")

    assert result is not None
    assert result['amount_rub'] == 10000
    # Ожидаем точное значение после округления до 8 знаков
    assert result['amount_crypto'] == 0.00195122
    assert result['fee_amount'] == pytest.approx(243.9, rel=1e-3)