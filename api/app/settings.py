"""The one place that knows which environment we are in.

Every backend choice (database, storage, auth, notifications) is selected here.
Nothing else in the code branches on environment.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEMO = "demo"
    TEST = "test"
    PRODUCTION = "production"


class StorageBackend(StrEnum):
    LOCAL = "local"
    AZURE_BLOB = "azure_blob"


class AuthBackend(StrEnum):
    LOCAL_DEV = "local_dev"
    ENTRA = "entra"


class NotifierBackend(StrEnum):
    CONSOLE = "console"
    ACS = "acs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMUTAH_", env_file=".env", extra="ignore")

    environment: Environment = Environment.DEMO

    database_url: str = "sqlite:///./amutah_demo.db"

    storage_backend: StorageBackend = StorageBackend.LOCAL
    local_storage_dir: Path = Path("./var/documents")
    download_link_ttl_seconds: int = 900

    auth_backend: AuthBackend = AuthBackend.LOCAL_DEV
    notifier_backend: NotifierBackend = NotifierBackend.CONSOLE

    # Secrets. Demo values come from .env; production values come from Key Vault.
    # HMAC key for national-ID lookup hashes. A plain hash of a 9-digit ID is
    # brute-forceable in seconds, so lookup hashes are always keyed.
    national_id_hmac_key: SecretStr
    # Fernet key (urlsafe base64, 32 bytes) for encrypting personal fields for display.
    field_encryption_key: SecretStr
    # Signs dev session tokens and local document download links.
    signing_key: SecretStr

    public_base_url: str = "http://localhost:8000"

    @field_validator("national_id_hmac_key", "signing_key")
    @classmethod
    def _long_enough(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            problems = []
            if self.database_url.startswith("sqlite"):
                problems.append("SQLite is not allowed in production")
            if self.auth_backend is AuthBackend.LOCAL_DEV:
                problems.append("local dev auth is not allowed in production")
            if self.storage_backend is StorageBackend.LOCAL:
                problems.append("local document storage is not allowed in production")
            if self.notifier_backend is NotifierBackend.CONSOLE:
                problems.append("console notifier is not allowed in production")
            if self.download_link_ttl_seconds > 900:
                problems.append("document links must expire within 15 minutes")
            if problems:
                raise ValueError("; ".join(problems))
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # secrets come from the environment
