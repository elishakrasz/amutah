"""Demo-only endpoints: role picker login and local document downloads.
Mounted only when the local dev auth backend is selected."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import writer as audit
from app.db import get_session
from app.deps import get_auth_provider, get_document_store
from app.domain.enums import ActorType, Role
from app.models import Document, StaffUser
from app.services.auth import AuthProvider, LocalDevAuthProvider
from app.services.storage import DocumentStore, InvalidLink, LocalDocumentStore

router = APIRouter(prefix="/dev", tags=["dev"])


class StaffOption(BaseModel):
    id: uuid.UUID
    display_name: str
    roles: list[Role]


class DevLogin(BaseModel):
    user_id: uuid.UUID
    role: Role


class DevToken(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    role: Role
    display_name: str


@router.get("/staff", response_model=list[StaffOption])
def list_staff(session: Annotated[Session, Depends(get_session)]) -> list[StaffOption]:
    users = session.scalars(
        select(StaffUser).where(StaffUser.active.is_(True)).order_by(StaffUser.display_name)
    )
    return [StaffOption(id=u.id, display_name=u.display_name, roles=u.roles) for u in users]


@router.post("/login", response_model=DevToken)
def dev_login(
    body: DevLogin,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> DevToken:
    assert isinstance(auth, LocalDevAuthProvider)
    user = session.get(StaffUser, body.user_id)
    if user is None or not user.active or body.role.value not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user does not hold that role")
    actor = audit.Actor(
        ActorType.STAFF, user.id, body.role.value, request.client.host if request.client else None
    )
    audit.record(session, actor, "login", "staff_user", user.id, purpose="dev role picker")
    session.commit()
    token = auth.issue(user.id, body.role, user.display_name)
    return DevToken(access_token=token, role=body.role, display_name=user.display_name)


@router.get("/files/{token}")
def download(
    token: str,
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[DocumentStore, Depends(get_document_store)],
) -> Response:
    assert isinstance(store, LocalDocumentStore)
    try:
        key = store.verify(token)
    except InvalidLink as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from exc
    doc = session.scalars(select(Document).where(Document.storage_key == key)).one_or_none()
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return Response(
        store.read(key),
        media_type=doc.content_type,
        headers={"Cache-Control": "no-store", "Content-Disposition": "attachment"},
    )
