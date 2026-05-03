"""2FA service.

Lifecycle:
1. `start_setup(user)` — generates a fresh secret, encrypts and stores it,
   but does NOT flip `two_factor_enabled`. Returns the plaintext secret +
   provisioning URI so the client can render a QR code.
2. `confirm_setup(user, code)` — verifies a TOTP code and flips
   `two_factor_enabled=True`. Also generates 8 recovery codes (one-time use,
   hashed at rest) and returns the plaintext list once.
3. `verify_login_code(user, code)` — called during login; accepts either a
   live TOTP code or one of the unused recovery codes (which is then
   consumed).
4. `disable(user, code)` — verifies a code, then clears the secret + flag.

The encryption key is the same Fernet key used elsewhere in the app.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.models.user import User
from app.security.encryption import decrypt, encrypt
from app.security.totp import (
    current_code,
    generate_secret,
    provisioning_uri,
    verify_code,
)


_RECOVERY_CODE_COUNT: Final = 8
# Recovery codes are short (10 chars) but high-entropy (~50 bits with our
# alphabet) — that's plenty for an offline backup that the user prints once.
_RECOVERY_ALPHABET: Final = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ambiguous chars dropped


class TwoFactorAlreadyEnabledError(AdVantaError):
    status_code = 409
    code = "two_factor_already_enabled"


class TwoFactorNotEnabledError(AdVantaError):
    status_code = 409
    code = "two_factor_not_enabled"


class TwoFactorInvalidCodeError(AdVantaError):
    status_code = 401
    code = "two_factor_invalid_code"


def start_setup(db: Session, *, user: User) -> dict:
    """Generate a fresh secret. If the user already had setup-in-progress
    (enabled=False but secret stored), the previous secret is overwritten."""
    if user.two_factor_enabled:
        raise TwoFactorAlreadyEnabledError("2FA is already enabled.")

    secret = generate_secret()
    user.two_factor_secret_encrypted = encrypt(secret)
    user.two_factor_recovery_hashes = None
    db.commit()

    issuer = settings.app_name or "AdVanta AI"
    uri = provisioning_uri(secret, account_email=user.email, issuer=issuer)
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "issuer": issuer,
    }


def confirm_setup(db: Session, *, user: User, code: str) -> dict:
    """Verify a code, flip the flag, return one-time recovery codes."""
    if user.two_factor_enabled:
        raise TwoFactorAlreadyEnabledError("2FA is already enabled.")
    if not user.two_factor_secret_encrypted:
        raise TwoFactorNotEnabledError("Run /2fa/setup first.")

    secret = decrypt(user.two_factor_secret_encrypted)
    if not verify_code(secret, code):
        raise TwoFactorInvalidCodeError("Invalid 2FA code.")

    recovery_codes = [_generate_recovery_code() for _ in range(_RECOVERY_CODE_COUNT)]
    user.two_factor_recovery_hashes = [_hash_code(c) for c in recovery_codes]
    user.two_factor_enabled = True
    db.commit()

    return {"recovery_codes": recovery_codes}


def disable(db: Session, *, user: User, code: str) -> None:
    """Verify a code (TOTP or recovery), then turn 2FA off."""
    if not user.two_factor_enabled:
        raise TwoFactorNotEnabledError("2FA is not enabled.")

    if not _verify_any(db, user=user, code=code):
        raise TwoFactorInvalidCodeError("Invalid 2FA code.")

    user.two_factor_enabled = False
    user.two_factor_secret_encrypted = None
    user.two_factor_recovery_hashes = None
    db.commit()


def verify_login_code(db: Session, *, user: User, code: str) -> bool:
    """True if the code matches a live TOTP or an unused recovery code.
    Recovery codes are consumed on success."""
    if not user.two_factor_enabled:
        # Defense in depth: refuse to accept a code on a user who hasn't
        # enabled 2FA.
        return False
    return _verify_any(db, user=user, code=code)


def _verify_any(db: Session, *, user: User, code: str) -> bool:
    code = (code or "").strip().upper()
    if not code:
        return False

    # 1) TOTP path — only meaningful when a secret is stored.
    if user.two_factor_secret_encrypted:
        secret = decrypt(user.two_factor_secret_encrypted)
        if verify_code(secret, code):
            return True

    # 2) Recovery-code path — code is consumed atomically.
    candidates = list(user.two_factor_recovery_hashes or [])
    candidate_hash = _hash_code(code)
    if candidate_hash in candidates:
        candidates.remove(candidate_hash)
        user.two_factor_recovery_hashes = candidates
        db.commit()
        return True

    return False


def _generate_recovery_code() -> str:
    return "-".join(
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(5))
        for _ in range(2)
    )


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def get_current_otp_for_test(user: User) -> str:
    """Test-only helper: returns the current TOTP for a user with 2FA stored."""
    if not user.two_factor_secret_encrypted:
        raise TwoFactorNotEnabledError("No secret stored.")
    return current_code(decrypt(user.two_factor_secret_encrypted))
