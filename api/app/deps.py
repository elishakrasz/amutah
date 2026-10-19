from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from app.audit.writer import Actor
from app.domain.enums import ActorType, Role
from app.services.auth import AuthError, AuthProvider, Principal, make_auth_provider
from app.services.notify import Notifier, make_notifier
from app.services.storage import DocumentStore, make_document_store
from app.settings import get_settings


@lru_cache
def get_auth_provider() -> AuthProvider:
    return make_auth_provider(get_settings())


@lru_cache
def get_document_store() -> DocumentStore:
    return make_document_store(get_settings())


@lru_cache
def get_notifier() -> Notifier:
    return make_notifier(get_settings())


def current_principal(
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        return auth.authenticate(authorization[7:])
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    allowed = frozenset(roles)

    def check(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "role not permitted")
        return principal

    return check


def staff_actor(principal: Principal, request: Request) -> Actor:
    return Actor(
        type=ActorType.STAFF,
        id=principal.user_id,
        role=principal.role.value,
        ip=request.client.host if request.client else None,
    )
