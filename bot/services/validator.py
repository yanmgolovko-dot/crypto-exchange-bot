"""Валидация криптоадресов"""

import re

def validate_btc_address(address: str) -> bool:
    if not address:
        return False
    # Legacy addresses (1...)
    if address.startswith('1') and len(address) == 34:
        return bool(re.match(r'^[1][a-zA-Z0-9]{33}$', address))
    # P2SH addresses (3...)
    if address.startswith('3') and len(address) == 34:
        return bool(re.match(r'^[3][a-zA-Z0-9]{33}$', address))
    # Bech32 addresses (bc1...)
    if address.startswith('bc1') and 42 <= len(address) <= 62:
        return bool(re.match(r'^bc1[a-zA-Z0-9]{39,59}$', address))
    return False

def validate_ltc_address(address: str) -> bool:
    if not address:
        return False
    # Legacy addresses (L...)
    if address.startswith('L') and len(address) == 34:
        return bool(re.match(r'^[L][a-zA-Z0-9]{33}$', address))
    # P2SH addresses (M...)
    if address.startswith('M') and len(address) == 34:
        return bool(re.match(r'^[M][a-zA-Z0-9]{33}$', address))
    # Bech32 addresses (ltc1...)
    if address.startswith('ltc1') and 42 <= len(address) <= 62:
        return bool(re.match(r'^ltc1[a-zA-Z0-9]{39,59}$', address))
    return False

def validate_crypto_address(address: str, crypto_type: str) -> bool:
    if crypto_type == "BTC":
        return validate_btc_address(address)
    elif crypto_type == "LTC":
        return validate_ltc_address(address)
    return False