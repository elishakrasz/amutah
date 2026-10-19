"""append-only triggers

Append-only tables reject UPDATE and DELETE (and TRUNCATE on PostgreSQL) at the
database level. aid_case accepts updates only to its workflow columns, and to
NULL on personal free-text columns (for the retention job).

Lists are frozen here on purpose: a later migration that adds an append-only
table adds its own triggers. tests/test_append_only.py fails if the model
metadata and the database disagree.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY = (
    "appeal",
    "appeal_decision",
    "audit_event",
    "case_transition",
    "chair_approval",
    "config_version",
    "decision",
    "decision_approver",
    "eligibility_check",
    "follow_up",
    "payment",
    "payment_batch",
    "payment_batch_execution",
    "payment_event",
    "recusal",
    "score",
    "tier_assignment",
    "verification",
)

CASE_IMMUTABLE = (
    "id",
    "created_at",
    "created_by",
    "case_number",
    "applicant_id",
    "referrer_id",
    "category",
    "amount_requested",
    "payment_periods",
    "urgency",
    "config_version_id",
)
CASE_NULLABLE_ONLY = ("vendor_name", "vendor_contact", "description")


def _sqlite_upgrade() -> None:
    for t in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only table: {t}'); END"
        )
        op.execute(
            f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} "
            f"BEGIN SELECT RAISE(ABORT, 'append-only table: {t}'); END"
        )
    changed = [f"NEW.{c} IS NOT OLD.{c}" for c in CASE_IMMUTABLE] + [
        f"(NEW.{c} IS NOT OLD.{c} AND NEW.{c} IS NOT NULL)" for c in CASE_NULLABLE_ONLY
    ]
    op.execute(
        "CREATE TRIGGER aid_case_guard_update BEFORE UPDATE ON aid_case "
        f"WHEN {' OR '.join(changed)} "
        "BEGIN SELECT RAISE(ABORT, 'aid_case: only workflow columns may change'); END"
    )
    op.execute(
        "CREATE TRIGGER aid_case_no_delete BEFORE DELETE ON aid_case "
        "BEGIN SELECT RAISE(ABORT, 'aid_case rows are never deleted'); END"
    )


def _sqlite_downgrade() -> None:
    for t in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_update")
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_delete")
    op.execute("DROP TRIGGER IF EXISTS aid_case_guard_update")
    op.execute("DROP TRIGGER IF EXISTS aid_case_no_delete")


def _pg_upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'append-only table: %', TG_TABLE_NAME
                USING ERRCODE = 'restrict_violation';
        END $$
        """
    )
    for t in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {t}_no_mutation BEFORE UPDATE OR DELETE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
        )
        op.execute(
            f"CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t} "
            "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
        )
    changed = [f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in CASE_IMMUTABLE] + [
        f"(NEW.{c} IS DISTINCT FROM OLD.{c} AND NEW.{c} IS NOT NULL)" for c in CASE_NULLABLE_ONLY
    ]
    op.execute(
        f"""
        CREATE FUNCTION aid_case_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'aid_case rows are never deleted'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF {" OR ".join(changed)} THEN
                RAISE EXCEPTION 'aid_case: only workflow columns may change'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER aid_case_guard BEFORE UPDATE OR DELETE ON aid_case "
        "FOR EACH ROW EXECUTE FUNCTION aid_case_guard()"
    )
    op.execute(
        "CREATE TRIGGER aid_case_no_truncate BEFORE TRUNCATE ON aid_case "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()"
    )


def _pg_downgrade() -> None:
    for t in APPEND_ONLY:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_mutation ON {t}")
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_truncate ON {t}")
    op.execute("DROP TRIGGER IF EXISTS aid_case_guard ON aid_case")
    op.execute("DROP TRIGGER IF EXISTS aid_case_no_truncate ON aid_case")
    op.execute("DROP FUNCTION IF EXISTS aid_case_guard()")
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation()")


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        _sqlite_upgrade()
    elif dialect == "postgresql":
        _pg_upgrade()
    else:
        raise RuntimeError(f"no append-only trigger DDL for dialect {dialect}")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        _sqlite_downgrade()
    elif dialect == "postgresql":
        _pg_downgrade()
