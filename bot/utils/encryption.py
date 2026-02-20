# bot/utils/encryption.py
"""
Модуль для шифрования и дешифрования приватных ключей.
Использует библиотеку cryptography с ключом, производным от пароля и соли.
"""

import base64
import os
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from bot.config.settings import config

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """
    Получает ключ шифрования из пароля ENCRYPTION_KEY и соли ENCRYPTION_SALT.
    Соль обязательна и должна быть задана в переменных окружения.
    """
    password = config.ENCRYPTION_KEY.encode()
    salt = os.getenv('ENCRYPTION_SALT')
    if not salt:
        logger.error("ENCRYPTION_SALT не задана в переменных окружения")
        raise ValueError("ENCRYPTION_SALT must be set in environment variables")
    salt = salt.encode()
    logger.debug("Генерация ключа шифрования с использованием PBKDF2")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    logger.debug("Ключ шифрования успешно сгенерирован")
    return key


def encrypt_private_key(private_key: str) -> str:
    """
    Шифрует приватный ключ с использованием Fernet.
    :param private_key: исходный приватный ключ (WIF)
    :return: зашифрованная строка (base64)
    """
    if not private_key:
        logger.warning("Попытка шифрования пустого ключа")
        raise ValueError("Приватный ключ не может быть пустым")
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(private_key.encode())
        logger.debug("Приватный ключ успешно зашифрован")
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Ошибка при шифровании приватного ключа: {e}", exc_info=True)
        raise


def decrypt_private_key(encrypted_key: str) -> str:
    """
    Дешифрует приватный ключ.
    :param encrypted_key: зашифрованная строка (base64)
    :return: исходный приватный ключ (WIF)
    """
    if not encrypted_key:
        logger.warning("Попытка дешифрования пустого ключа")
        raise ValueError("Зашифрованный ключ пуст")
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_key.encode())
        logger.debug("Приватный ключ успешно расшифрован")
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Ошибка при дешифровании приватного ключа: {e}", exc_info=True)
        raise ValueError(f"Ошибка расшифровки ключа: {e}")