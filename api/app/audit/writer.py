"""Audit events are added to the caller's session so they commit or roll back
together with the change they describe."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import ActorType
from app.models import AuditEvent


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: uuid.UUID | None
    role: str | None
    ip: str | None = None


SYSTEM = Actor(type=ActorType.SYSTEM, id=None, role=None)


def record(
    session: Session,
    actor: Actor,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    case_id: uuid.UUID | None = None,
    purpose: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    if detail and any(k in detail for k in ("national_id", "national_id_raw", "otp_code")):
        raise ValueError("refusing to write a national ID or OTP into the audit log")
    event = AuditEvent(
        actor_type=actor.type,
        actor_id=actor.id,
        role=actor.role,
        action=action,
        entity=entity,
        entity_id=entity_id,
        case_id=case_id,
        purpose=purpose,
        ip=actor.ip,
        detail=detail,
        created_by=actor.id if actor.type is ActorType.STAFF else None,
    )
    session.add(event)
    return event
