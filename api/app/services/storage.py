"""Document storage behind an interface. Storage keys never leave the server;
callers get short-lived download links, and every issue is audited by the caller."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.settings import Settings, StorageBackend


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size_bytes: int


class InvalidLink(Exception):
    pass


class DocumentStore(ABC):
    @abstractmethod
    def put(self, data: bytes, content_type: str) -> StoredObject: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def download_url(self, key: str, ttl_seconds: int) -> str: ...


class LocalDocumentStore(DocumentStore):
    """Files in a local folder; links are HMAC-signed tokens with an expiry."""

    def __init__(self, root: Path, signing_key: bytes, base_url: str) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._key = signing_key
        self._base_url = base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        # Keys are server-generated UUIDs; reject anything else outright.
        uuid.UUID(key)
        return self._root / key

    def put(self, data: bytes, content_type: str) -> StoredObject:
        key = str(uuid.uuid4())
        self._path(key).write_bytes(data)
        return StoredObject(key=key, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def sign(self, key: str, ttl_seconds: int, now: float | None = None) -> str:
        payload = json.dumps({"k": key, "exp": int((now or time.time()) + ttl_seconds)}).encode()
        sig = hmac.new(self._key, payload, hashlib.sha256).digest()
        return (
            base64.urlsafe_b64encode(payload).decode().rstrip("=")
            + "."
            + base64.urlsafe_b64encode(sig).decode().rstrip("=")
        )

    def verify(self, token: str, now: float | None = None) -> str:
        try:
            p64, s64 = token.split(".")
            payload = base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4))
            sig = base64.urlsafe_b64decode(s64 + "=" * (-len(s64) % 4))
        except ValueError as exc:
            raise InvalidLink("malformed") from exc
        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise InvalidLink("bad signature")
        body = json.loads(payload)
        if body["exp"] < (now or time.time()):
            raise InvalidLink("expired")
        return str(body["k"])

    def download_url(self, key: str, ttl_seconds: int) -> str:
        return f"{self._base_url}/api/v1/dev/files/{self.sign(key, ttl_seconds)}"


def make_document_store(settings: Settings) -> DocumentStore:
    if settings.storage_backend is StorageBackend.LOCAL:
        return LocalDocumentStore(
            settings.local_storage_dir,
            settings.signing_key.get_secret_value().encode(),
            settings.public_base_url,
        )
    raise NotImplementedError("AzureBlobDocumentStore arrives in build phase 8")
