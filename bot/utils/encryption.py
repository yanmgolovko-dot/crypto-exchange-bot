# bot/utils/encryption.py
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from bot.config.settings import config

def get_encryption_key() -> bytes:
    """Получение ключа шифрования из конфигурации с использованием соли из ENV.
    Соль обязательна! Если не задана – выбрасывается исключение.
    """
    password = config.ENCRYPTION_KEY.encode()
    salt = os.getenv('ENCRYPTION_SALT')
    if not salt:
        raise ValueError("ENCRYPTION_SALT must be set in environment variables")
    salt = salt.encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_private_key(private_key: str) -> str:
    if not private_key:
        raise ValueError("Приватный ключ не может быть пустым")
    key = get_encryption_key()
    f = Fernet(key)
    encrypted = f.encrypt(private_key.encode())
    return encrypted.decode()

def decrypt_private_key(encrypted_key: str) -> str:
    if not encrypted_key:
        raise ValueError("Зашифрованный ключ пуст")
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_key.encode())
        return decrypted.decode()
    except Exception as e:
        # Больше никакого fallback! Если не удалось расшифровать – ошибка.
        raise ValueError(f"Ошибка расшифровки ключа: {e}")