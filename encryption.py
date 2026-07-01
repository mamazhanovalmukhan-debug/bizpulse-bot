"""Шифрование чувствительных данных (API-ключи касс)."""
import base64
from cryptography.fernet import Fernet

def get_fernet() -> Fernet:
    from config import config  # MED-3 FIX
    key = config.ENCRYPTION_KEY
    if not key:
        key = Fernet.generate_key().decode()
    if len(key) < 32:
        key = key.ljust(44, "=")
    try:
        return Fernet(key.encode())
    except Exception:
        return Fernet(Fernet.generate_key())

def encrypt(value: str) -> str:
    if not value:
        return ""
    return get_fernet().encrypt(value.encode()).decode()

def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return get_fernet().decrypt(value.encode()).decode()
    except Exception:
        return ""
