"""case status withdrawn

Applicants can withdraw before a decision (AP-5 intake call outcome
'withdrawn', or at any point before decision). Adds the value to the three
status CHECK constraints.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

from app.migration_ddl import enum_check_sql, sqlite_append_only, sqlite_case_guard

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES_0003 = (
    "submitted", "intake_review", "ineligible", "eligible", "awaiting_documents",
    "verification", "scoring", "decision_pending", "approved", "partial", "conditional",
    "referred", "declined", "under_appeal", "emergency_review", "ratification_pending",
    "payment_approved", "in_batch", "paid", "follow_up", "closed",
)  # fmt: skip
STATUSES_0004 = (*STATUSES_0003, "withdrawn")

# (table, constraint name suffix, column)
COLUMNS = (
    ("aid_case", "case_status", "status"),
    ("case_transition", "from_status", "from_status"),
    ("case_transition", "to_status", "to_status"),
)

# Frozen as of 0003; both tables are rebuilt on SQLite, so their triggers go.
CASE_IMMUTABLE = (
    "id", "created_at", "created_by", "case_number", "applicant_id", "referrer_id",
    "category", "amount_requested", "payment_periods", "urgency", "config_version_id",
    "referral_unverified",
)  # fmt: skip
CASE_NULLABLE_ONLY = ("vendor_name", "vendor_contact", "description")


def _set(statuses: tuple[str, ...]) -> None:
    for table in ("aid_case", "case_transition"):
        with op.batch_alter_table(table) as batch_op:
            for t, suffix, column in COLUMNS:
                if t == table:
                    batch_op.drop_constraint(op.f(f"ck_{t}_{suffix}"), type_="check")
                    batch_op.create_check_constraint(suffix, enum_check_sql(column, statuses))
    if op.get_bind().dialect.name == "sqlite":
        sqlite_append_only(op.execute, ("case_transition",))
        sqlite_case_guard(op.execute, CASE_IMMUTABLE, CASE_NULLABLE_ONLY)


def upgrade() -> None:
    _set(STATUSES_0004)


def downgrade() -> None:
    """Fails if any case is withdrawn."""
    _set(STATUSES_0003)
