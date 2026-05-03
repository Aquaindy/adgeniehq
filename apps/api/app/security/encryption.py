from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import AdVantaError


class EncryptionNotConfiguredError(AdVantaError):
    status_code = 500
    code = "encryption_not_configured"


class TokenDecryptionError(AdVantaError):
    status_code = 500
    code = "token_decryption_failed"


def _fernet() -> Fernet:
    key = settings.encryption_key.strip() if settings.encryption_key else ""
    if not key:
        raise EncryptionNotConfiguredError(
            "ENCRYPTION_KEY is not set. Generate one with "
            "`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`."
        )
    return Fernet(key.encode("utf-8"))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenDecryptionError(
            "Could not decrypt stored token (key changed or value corrupted)."
        ) from exc
