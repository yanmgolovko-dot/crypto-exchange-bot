# bot/utils/tx_validator.py
"""
Валидация хешей транзакций для поддерживаемых криптовалют.

BTC / LTC: 64 hex-символа (SHA-256 double-hash).
Прочие монеты: минимальная длина 32 hex-символа (настраивается).
"""

import re
from typing import Optional

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_HEX_MIN_RE = re.compile(r"^[0-9a-fA-F]{32,}$")

# Явные правила для монет
_STRICT_HEX64 = {"BTC", "LTC", "BCH", "DOGE", "DASH"}
_MIN_LEN_BY_CURRENCY = {
    # сюда можно добавлять монеты с иной длиной
    # "ETH": 66,  # 0x + 64 hex
}


def validate_tx_hash(currency: str, tx_hash: Optional[str]) -> tuple[bool, str]:
    """
    Проверяет формат хеша транзакции для указанной валюты.

    :return: (is_valid, error_message). При успехе error_message == "".
    """
    if not tx_hash or not tx_hash.strip():
        return False, "Хеш транзакции не может быть пустым."

    tx_hash = tx_hash.strip()
    cur = (currency or "").upper()

    if cur in _STRICT_HEX64:
        if not _HEX64_RE.match(tx_hash):
            return False, f"Хеш {cur} должен содержать ровно 64 hex-символа."
        return True, ""

    if cur in _MIN_LEN_BY_CURRENCY:
        expected = _MIN_LEN_BY_CURRENCY[cur]
        if not _HEX_MIN_RE.match(tx_hash) or len(tx_hash) < expected:
            return False, f"Хеш {cur} должен содержать не менее {expected} hex-символов."
        return True, ""

    # Универсальное правило: минимум 32 hex-символа
    if not _HEX_MIN_RE.match(tx_hash):
        return False, "Хеш транзакции должен содержать минимум 32 hex-символа."
    return True, ""