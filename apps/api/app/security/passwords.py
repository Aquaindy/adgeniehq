import base64
import hashlib

import bcrypt

_BCRYPT_MAX_BYTES = 72


def _prepare(plain: str) -> bytes:
    """bcrypt silently truncates inputs above 72 bytes. Pre-hash long passwords
    with SHA-256 + base64 (44 bytes) so the full input still influences the hash."""
    raw = plain.encode("utf-8")
    if len(raw) <= _BCRYPT_MAX_BYTES:
        return raw
    digest = hashlib.sha256(raw).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("utf-8"))
    except ValueError:
        return False
