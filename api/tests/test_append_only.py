import pytest
from sqlalchemy import Engine, delete, inspect, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.audit import writer as audit
from app.domain.enums import CaseStatus, DecisionOutcome, PaymentMethod, Role
from app.models import (
    AidCase,
    AuditEvent,
    ConfigVersion,
    Decision,
    Payment,
    append_only_tables,
)
from tests import factories


def _trigger_tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            rows = conn.execute(text("SELECT tbl_name FROM sqlite_master WHERE type='trigger'"))
        else:
            rows = conn.execute(
                text(
                    "SELECT DISTINCT event_object_table FROM information_schema.triggers "
                    "WHERE trigger_schema = current_schema()"
                )
            )
        return {r[0] for r in rows}


def test_every_append_only_model_has_triggers(migrated_engine: Engine) -> None:
    assert set(append_only_tables()) <= _trigger_tables(migrated_engine)


def test_no_append_only_table_has_updated_at(migrated_engine: Engine) -> None:
    insp = inspect(migrated_engine)
    for table in append_only_tables():
        assert "updated_at" not in {c["name"] for c in insp.get_columns(table)}, table


def _assert_blocked(session: Session, stmt: object) -> None:
    with pytest.raises(DBAPIError, match="append-only|only workflow columns|never deleted"):
        session.execute(stmt)  # type: ignore[call-overload]
        session.flush()
    session.rollback()


def _seed_decision(session: Session) -> tuple[ConfigVersion, AidCase, Decision, Payment]:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    d = Decision(
        case_id=c.id,
        outcome=DecisionOutcome.APPROVE_FULL,
        amount_approved=120_000,
        config_version_id=cfg.id,
    )
    session.add(d)
    session.flush()
    p = Payment(decision_id=d.id, vendor="Landlord", amount=120_000, method=PaymentMethod.VOUCHER)
    session.add(p)
    audit.record(session, audit.SYSTEM, "test", "decision", d.id, c.id)
    session.commit()
    return cfg, c, d, p


def test_append_only_rows_reject_update_and_delete(session: Session) -> None:
    cfg, _c, d, p = _seed_decision(session)
    _assert_blocked(session, update(Decision).values(amount_approved=1).where(Decision.id == d.id))
    _assert_blocked(session, delete(Decision).where(Decision.id == d.id))
    _assert_blocked(session, update(Payment).values(amount=1).where(Payment.id == p.id))
    _assert_blocked(session, delete(Payment))
    _assert_blocked(
        session, update(ConfigVersion).values(version=2).where(ConfigVersion.id == cfg.id)
    )
    _assert_blocked(session, update(AuditEvent).values(action="tampered"))
    _assert_blocked(session, delete(AuditEvent))
    assert session.get(Decision, d.id) is not None


def test_case_workflow_columns_can_change(session: Session) -> None:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    coordinator = factories.staff(session, Role.COORDINATOR)
    session.commit()
    session.execute(
        update(AidCase)
        .where(AidCase.id == c.id)
        .values(status=CaseStatus.INTAKE_REVIEW, assigned_coordinator_id=coordinator.id)
    )
    # Retention may null personal free text.
    session.execute(update(AidCase).where(AidCase.id == c.id).values(description=None))
    session.commit()
    session.refresh(c)
    assert c.status is CaseStatus.INTAKE_REVIEW
    assert c.description is None


def test_case_facts_are_immutable(session: Session) -> None:
    cfg = factories.config(session)
    c = factories.case(session, cfg)
    session.commit()
    _assert_blocked(session, update(AidCase).where(AidCase.id == c.id).values(amount_requested=1))
    _assert_blocked(session, update(AidCase).where(AidCase.id == c.id).values(description="edited"))
    _assert_blocked(session, delete(AidCase).where(AidCase.id == c.id))


def test_score_total_must_equal_sum(session: Session) -> None:
    from app.models import Score

    cfg = factories.config(session)
    c = factories.case(session, cfg)
    member = factories.staff(session, Role.COMMITTEE_MEMBER)
    session.add(
        Score(
            case_id=c.id,
            committee_member_id=member.id,
            need=3,
            urgency=3,
            impact=3,
            alternatives=3,
            vulnerability=1,
            total=12,
            config_version_id=cfg.id,
        )
    )
    with pytest.raises(DBAPIError):
        session.flush()


def test_enum_values_are_checked_by_the_database(session: Session) -> None:
    with pytest.raises(DBAPIError):
        session.execute(
            text(
                "INSERT INTO audit_event (id, created_at, actor_type, action, entity) "
                "VALUES (:id, :ts, 'bogus', 'x', 'y')"
            ),
            {"id": "00000000-0000-0000-0000-000000000001", "ts": "2026-01-01T00:00:00+00:00"},
        )
