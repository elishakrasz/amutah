import uuid
from datetime import datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.audit import writer as audit
from app.domain.enums import Role
from app.models.base import UTCDateTime
from app.services.auth import AuthError, LocalDevAuthProvider
from app.services.crypto import FieldCrypto, normalise_national_id
from app.services.storage import InvalidLink, LocalDocumentStore
from app.settings import AuthBackend, Environment, Settings

KEYS = {
    "national_id_hmac_key": "k1" * 16,
    "field_encryption_key": Fernet.generate_key().decode(),
    "signing_key": "k3" * 16,
}

# Synthetic IDs with a valid check digit.
VALID_ID = "000000018"


def test_production_refuses_demo_backends() -> None:
    with pytest.raises(ValidationError, match="SQLite.*dev auth.*local document.*console"):
        Settings(environment=Environment.PRODUCTION, **KEYS)  # type: ignore[arg-type]


def test_production_accepts_azure_backends() -> None:
    s = Settings(
        environment=Environment.PRODUCTION,
        database_url="postgresql+psycopg://x@y/z",
        storage_backend="azure_blob",
        auth_backend=AuthBackend.ENTRA,
        notifier_backend="acs",
        **KEYS,  # type: ignore[arg-type]
    )
    assert not s.is_sqlite


def test_national_id_normalisation() -> None:
    assert normalise_national_id("18") == VALID_ID
    assert normalise_national_id("00000001-8") == VALID_ID
    with pytest.raises(ValueError, match="check digit"):
        normalise_national_id("000000019")
    with pytest.raises(ValueError):
        normalise_national_id("1234567890")


def test_national_id_hash_is_keyed_and_stable() -> None:
    a = FieldCrypto(Settings(**KEYS))  # type: ignore[arg-type]
    b = FieldCrypto(Settings(**{**KEYS, "national_id_hmac_key": "other" * 8}))  # type: ignore[arg-type]
    assert a.national_id_hash("18") == a.national_id_hash(VALID_ID)
    assert a.national_id_hash(VALID_ID) != b.national_id_hash(VALID_ID)
    assert VALID_ID not in a.national_id_hash(VALID_ID)


def test_field_encryption_round_trip() -> None:
    c = FieldCrypto(Settings(**KEYS))  # type: ignore[arg-type]
    token = c.encrypt("IL62 0108 0000 0009 9999 999")
    assert "0108" not in token
    assert c.decrypt(token) == "IL62 0108 0000 0009 9999 999"


def test_local_store_links(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path, b"secret", "http://localhost:8000")
    obj = store.put(b"%PDF-1.4 synthetic", "application/pdf")
    assert store.read(obj.key) == b"%PDF-1.4 synthetic"
    token = store.sign(obj.key, ttl_seconds=60, now=1000)
    assert store.verify(token, now=1059) == obj.key
    with pytest.raises(InvalidLink, match="expired"):
        store.verify(token, now=1061)
    with pytest.raises(InvalidLink):
        store.verify(token[:-2] + "AA", now=1000)
    other = LocalDocumentStore(tmp_path, b"different", "http://x")
    with pytest.raises(InvalidLink, match="signature"):
        other.verify(token, now=1000)
    assert obj.key not in store.download_url(obj.key, 60)


def test_local_store_rejects_non_uuid_keys(tmp_path: Path) -> None:
    store = LocalDocumentStore(tmp_path, b"secret", "http://x")
    with pytest.raises(ValueError):
        store.read("../../etc/passwd")


def test_dev_tokens() -> None:
    p = LocalDevAuthProvider("k" * 32)
    uid = uuid.uuid4()
    principal = p.authenticate(p.issue(uid, Role.TREASURER, "T"))
    assert principal.user_id == uid
    assert principal.role is Role.TREASURER
    with pytest.raises(AuthError):
        LocalDevAuthProvider("other" * 8).authenticate(p.issue(uid, Role.TREASURER, "T"))
    with pytest.raises(AuthError):
        p.authenticate("garbage")


def test_audit_refuses_national_id() -> None:
    with pytest.raises(ValueError, match="national ID"):
        audit.record(None, audit.SYSTEM, "x", "y", detail={"national_id": "1"})  # type: ignore[arg-type]


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), None)  # type: ignore[arg-type]


def test_short_secrets_are_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(**{**KEYS, "signing_key": "short"})  # type: ignore[arg-type]
