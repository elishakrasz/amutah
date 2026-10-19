"""Seed the demo database with synthetic data only. Never real applicants.

Phase 1 seeds config version 1 and staff users. Synthetic cases arrive in phase 6.
Run: uv run python -m app.scripts.seed_demo
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import writer as audit
from app.db import get_engine
from app.domain.enums import Role
from app.models import ConfigVersion, StaffUser
from app.scripts.demo_config import CONFIG_V1

STAFF: list[tuple[str, str, list[Role]]] = [
    ("רכזת דמו", "coordinator@demo.invalid", [Role.COORDINATOR]),
    ("יו״ר ועדה דמו", "chair@demo.invalid", [Role.COMMITTEE_CHAIR, Role.COMMITTEE_MEMBER]),
    ("חבר ועדה א", "committee1@demo.invalid", [Role.COMMITTEE_MEMBER]),
    ("חברת ועדה ב", "committee2@demo.invalid", [Role.COMMITTEE_MEMBER]),
    ("חבר ועדה ג", "committee3@demo.invalid", [Role.COMMITTEE_MEMBER]),
    ("גזברית דמו", "treasurer@demo.invalid", [Role.TREASURER]),
    ("חבר ועד דמו", "board@demo.invalid", [Role.BOARD_MEMBER]),
    ("מבקר דמו", "auditor@demo.invalid", [Role.AUDITOR]),
    ("מנהל מערכת דמו", "admin@demo.invalid", [Role.ADMIN]),
]


def seed(session: Session) -> None:
    if session.scalars(select(StaffUser).limit(1)).first() is not None:
        print("already seeded; skipping")
        return
    users = {}
    for name, email, roles in STAFF:
        u = StaffUser(display_name=name, email=email, roles=[r.value for r in roles])
        session.add(u)
        users[email] = u
    session.flush()
    board = users["board@demo.invalid"]
    cfg = ConfigVersion(
        version=1,
        body=CONFIG_V1,
        approved_by=[str(board.id)],
        board_resolution="DEMO resolution 1",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        created_by=board.id,
    )
    session.add(cfg)
    session.flush()
    audit.record(session, audit.SYSTEM, "seed", "config_version", cfg.id, purpose="demo seed")
    session.commit()
    print(f"seeded {len(users)} staff users and config version 1")


if __name__ == "__main__":
    with Session(get_engine()) as s:
        seed(s)
