from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import current_principal
from app.services.auth import Principal
from app.settings import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok", "environment": get_settings().environment.value}


@router.get("/whoami")
def whoami(principal: Annotated[Principal, Depends(current_principal)]) -> dict[str, str]:
    return {
        "user_id": str(principal.user_id),
        "role": principal.role.value,
        "display_name": principal.display_name,
    }
