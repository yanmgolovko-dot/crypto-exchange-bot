from bot.services.validator import validate_btc_address, validate_ltc_address, validate_crypto_address


def test_validate_btc_address_legacy():
    valid = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    assert validate_btc_address(valid) is True
    invalid = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfN"
    assert validate_btc_address(invalid) is False


def test_validate_btc_address_p2sh():
    valid = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy"
    assert validate_btc_address(valid) is True
    invalid = "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNL"
    assert validate_btc_address(invalid) is False


def test_validate_btc_address_bech32():
    valid = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    assert validate_btc_address(valid) is True
    invalid = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5md"
    assert validate_btc_address(invalid) is False


def test_validate_ltc_address_legacy():
    valid = "LbTjMGN7gELw4KbeyQf6cTCq859hD18guE"
    assert validate_ltc_address(valid) is True


def test_validate_ltc_address_p2sh():
    valid = "M8T1B2Zxs9gW0F6jK5qY4nX8pJ3L7vR2dA"
    assert validate_ltc_address(valid) is True


def test_validate_ltc_address_bech32():
    valid = "ltc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    assert validate_ltc_address(valid) is True


def test_validate_crypto_address():
    btc = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    ltc = "LbTjMGN7gELw4KbeyQf6cTCq859hD18guE"
    assert validate_crypto_address(btc, "BTC") is True
    assert validate_crypto_address(ltc, "LTC") is True
    assert validate_crypto_address(btc, "LTC") is False
    assert validate_crypto_address("invalid", "BTC") is False