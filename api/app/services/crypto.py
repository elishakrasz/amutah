"""National-ID hashing and personal-field encryption.

Lookup hashes are HMAC-SHA256 with a secret key: Israeli IDs have ~10^9 values,
so an unkeyed hash is reversible by enumeration.
"""

import hashlib
import hmac

from cryptography.fernet import Fernet

from app.settings import Settings


def normalise_national_id(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits or len(digits) > 9:
        raise ValueError("national ID must be 1-9 digits")
    padded = digits.zfill(9)
    if not is_valid_israeli_id(padded):
        raise ValueError("national ID check digit is invalid")
    return padded


def is_valid_israeli_id(nine_digits: str) -> bool:
    total = 0
    for i, ch in enumerate(nine_digits):
        n = int(ch) * (1 if i % 2 == 0 else 2)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


class FieldCrypto:
    def __init__(self, settings: Settings) -> None:
        self._hmac_key = settings.national_id_hmac_key.get_secret_value().encode()
        self._fernet = Fernet(settings.field_encryption_key.get_secret_value().encode())

    def national_id_hash(self, raw: str) -> str:
        normalised = normalise_national_id(raw)
        return hmac.new(self._hmac_key, normalised.encode(), hashlib.sha256).hexdigest()

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
