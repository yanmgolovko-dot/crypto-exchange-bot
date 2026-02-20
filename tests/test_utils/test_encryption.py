import pytest
from bot.utils.encryption import encrypt_private_key, decrypt_private_key


def test_encrypt_decrypt():
    original = "L5K9eP6Z8dJ3qX2wR7vYmN1tQ4sA6fC8gH0jB2nM"
    encrypted = encrypt_private_key(original)
    assert encrypted != original
    decrypted = decrypt_private_key(encrypted)
    assert decrypted == original


def test_encrypt_empty_raises():
    with pytest.raises(ValueError):
        encrypt_private_key("")


def test_decrypt_empty_raises():
    with pytest.raises(ValueError):
        decrypt_private_key("")