"""Print fresh demo secrets in .env format."""

import secrets

from cryptography.fernet import Fernet

if __name__ == "__main__":
    print(f"AMUTAH_NATIONAL_ID_HMAC_KEY={secrets.token_urlsafe(32)}")
    print(f"AMUTAH_FIELD_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    print(f"AMUTAH_SIGNING_KEY={secrets.token_urlsafe(32)}")
