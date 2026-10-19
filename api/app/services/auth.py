"""Staff authentication behind an interface.

Demo: a role picker issues a signed short-lived token for a seeded staff user.
Production: Entra ID bearer tokens with app roles (build phase 8).
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.domain.enums import Role
from app.settings import AuthBackend, Settings


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    role: Role  # the role the user is acting in for this session
    display_name: str


class AuthError(Exception):
    pass


class AuthProvider(ABC):
    @abstractmethod
    def authenticate(self, bearer_token: str) -> Principal: ...


class LocalDevAuthProvider(AuthProvider):
    ISSUER = "amutah-local-dev"
    TTL = timedelta(hours=8)

    def __init__(self, signing_key: str) -> None:
        self._key = signing_key

    def issue(self, user_id: uuid.UUID, role: Role, display_name: str) -> str:
        now = datetime.now(UTC)
        claims = {
            "iss": self.ISSUER,
            "sub": str(user_id),
            "role": role.value,
            "name": display_name,
            "iat": now,
            "exp": now + self.TTL,
        }
        return jwt.encode(claims, self._key, algorithm="HS256")

    def authenticate(self, bearer_token: str) -> Principal:
        try:
            claims = jwt.decode(bearer_token, self._key, algorithms=["HS256"], issuer=self.ISSUER)
            return Principal(
                user_id=uuid.UUID(claims["sub"]),
                role=Role(claims["role"]),
                display_name=str(claims["name"]),
            )
        except (jwt.PyJWTError, KeyError, ValueError) as exc:
            raise AuthError("invalid token") from exc


def make_auth_provider(settings: Settings) -> AuthProvider:
    if settings.auth_backend is AuthBackend.LOCAL_DEV:
        return LocalDevAuthProvider(settings.signing_key.get_secret_value())
    raise NotImplementedError("EntraAuthProvider arrives in build phase 8")
