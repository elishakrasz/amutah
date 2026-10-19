"""Minimal valid rows for persistence tests. Synthetic data only."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.enums import CaseStatus, Category, Role
from app.models import AidCase, Applicant, ConfigVersion, Household, StaffUser


def staff(session: Session, role: Role = Role.COORDINATOR, email: str | None = None) -> StaffUser:
    u = StaffUser(
        display_name=f"Test {role.value}",
        email=email or f"{role.value}-{datetime.now(UTC).timestamp()}@test.invalid",
        roles=[role.value],
    )
    session.add(u)
    session.flush()
    return u


def config(session: Session, version: int = 1) -> ConfigVersion:
    c = ConfigVersion(
        version=version,
        body={"cooling_off_days": 180},
        approved_by=[],
        board_resolution="test",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(c)
    session.flush()
    return c


def case(session: Session, cfg: ConfigVersion, number: str = "2026-0001") -> AidCase:
    hh = Household()
    session.add(hh)
    session.flush()
    a = Applicant(
        national_id_hash="h" * 64,
        household_id=hh.id,
        name="Synthetic Person",
        household_adults=1,
        household_children=2,
        consent_at=datetime.now(UTC),
        consent_version="2026-1",
    )
    session.add(a)
    session.flush()
    c = AidCase(
        case_number=number,
        applicant_id=a.id,
        category=Category.RENT,
        amount_requested=120_000,
        description="synthetic",
        config_version_id=cfg.id,
        status=CaseStatus.SUBMITTED,
    )
    session.add(c)
    session.flush()
    return c
