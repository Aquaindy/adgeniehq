"""RFC-6238 TOTP implementation backed by stdlib only.

We don't pull in `pyotp` because the spec is small and the stdlib gives us
everything we need (`hmac` + `hashlib` + `secrets`). Same reasoning as the
multi-arm-bandit / two-proportion z-test code.

Default parameters match Google Authenticator / 1Password / Authy:
- 30-second time step
- 6-digit code
- HMAC-SHA1 (the RFC default; switching to SHA256 breaks scanned QR codes)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_DIGITS = 6
_INTERVAL_SECONDS = 30


def generate_secret() -> str:
    """20 random bytes (160 bits) base32-encoded — RFC-4648 compatible."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def current_code(secret: str, *, at: int | None = None) -> str:
    """Return the 6-digit TOTP code for the current 30-second window."""
    counter = int((at if at is not None else time.time()) // _INTERVAL_SECONDS)
    return _hotp(secret, counter)


def verify_code(secret: str, candidate: str, *, at: int | None = None) -> bool:
    """Constant-time verify with a ±1-step window so a code typed at the very
    end of the previous window or the start of the next is still accepted."""
    if not candidate or not candidate.isdigit() or len(candidate) != _DIGITS:
        return False
    counter = int((at if at is not None else time.time()) // _INTERVAL_SECONDS)
    for offset in (-1, 0, 1):
        if hmac.compare_digest(_hotp(secret, counter + offset), candidate):
            return True
    return False


def provisioning_uri(secret: str, *, account_email: str, issuer: str) -> str:
    """Return an `otpauth://` URI suitable for QR-coding by a client."""
    issuer_q = quote(issuer)
    label_q = quote(f"{issuer}:{account_email}")
    return (
        f"otpauth://totp/{label_q}?secret={secret}"
        f"&issuer={issuer_q}&algorithm=SHA1&digits={_DIGITS}&period={_INTERVAL_SECONDS}"
    )


def _hotp(secret: str, counter: int) -> str:
    """RFC-4226 HOTP — the building block TOTP wraps."""
    # Repad base32 input to a multiple of 8 chars (encoders strip padding).
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = truncated % (10 ** _DIGITS)
    return str(code).zfill(_DIGITS)
