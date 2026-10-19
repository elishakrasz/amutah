import uuid
from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.domain.enums import (
    AllocationStatus,
    Category,
    NeedConfirmMethod,
    PaymentEventKind,
    PaymentMethod,
)
from app.models._types import str_enum
from app.models.base import Base, MutableMixin


class Payment(Base):
    """An approved payment instruction. The system never moves money.

    Status is not a column: it is derived from the latest PaymentEvent
    (none = approved), which keeps this table strictly append-only. Facts that
    arrive later (AP-6 need confirmation, AP-14 voucher issue and redemption)
    are PaymentEvent rows too.
    """

    __tablename__ = "payment"
    __append_only__ = True
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # AP-15: one live payment per allocation per month, even if the job runs twice.
        Index(
            "uq_payment_allocation_month",
            "allocation_id",
            "allocation_month",
            unique=True,
            sqlite_where=text("supersedes_id IS NULL AND allocation_id IS NOT NULL"),
            postgresql_where=text("supersedes_id IS NULL AND allocation_id IS NOT NULL"),
        ),
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decision.id"), index=True)
    vendor: Mapped[str] = mapped_column(String(200))
    vendor_bank_details_enc: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int] = mapped_column(BigInteger)  # agorot
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "payment_method"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payment.id"))
    allocation_id: Mapped[uuid.UUID | None] = mapped_column(  # AP-15
        Uuid, ForeignKey("allocation.id"), index=True
    )
    allocation_month: Mapped[date | None] = mapped_column(Date)  # first day of month


class PaymentBatch(Base):
    __tablename__ = "payment_batch"
    __append_only__ = True

    file_sha256: Mapped[str] = mapped_column(String(64))
    payment_count: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(BigInteger)  # agorot
    # generated_by is created_by


class PaymentEvent(Base):
    __tablename__ = "payment_event"
    __append_only__ = True

    payment_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("payment.id"), index=True)
    kind: Mapped[PaymentEventKind] = mapped_column(str_enum(PaymentEventKind, "payment_event"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payment_batch.id"))
    bank_reference: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    need_confirmed_method: Mapped[NeedConfirmMethod | None] = mapped_column(  # AP-6
        str_enum(NeedConfirmMethod, "need_confirmed_method")
    )
    # AP-14: keyed hash of the voucher code; the code itself is never stored.
    voucher_reference_hash: Mapped[str | None] = mapped_column(String(64))


class PaymentBatchExecution(Base):
    """Second-person confirmation that the bank executed a batch."""

    __tablename__ = "payment_batch_execution"
    __append_only__ = True

    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("payment_batch.id"), unique=True)
    bank_reference: Mapped[str] = mapped_column(String(128))
    # confirmed_by is created_by; must differ from the batch's created_by


class Allocation(MutableMixin, Base):
    """AP-15: standing monthly allocation for an infant. A scheduled job turns
    each active month into one Payment; status changes are audited."""

    __tablename__ = "allocation"
    __table_args__ = (
        CheckConstraint("monthly_amount > 0", name="amount_positive"),
        CheckConstraint("end_month >= start_month", name="months_ordered"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aid_case.id"), index=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("decision.id"))
    household_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("household.id"), index=True)
    child_birth_month: Mapped[date] = mapped_column(Date)  # first of month; no name
    category: Mapped[Category] = mapped_column(str_enum(Category, "category"))
    monthly_amount: Mapped[int] = mapped_column(BigInteger)  # agorot
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "method"))
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date] = mapped_column(Date)
    config_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("config_version.id"))
    status: Mapped[AllocationStatus] = mapped_column(
        str_enum(AllocationStatus, "allocation_status")
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("allocation.id"))


class VoucherStock(Base):
    """AP-14: vouchers bought by the treasurer. Issued counts come from
    PaymentEvent(voucher_issued), so stock reconciles against issues."""

    __tablename__ = "voucher_stock"
    __append_only__ = True
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("face_value > 0", name="face_value_positive"),
    )

    vendor: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    face_value: Mapped[int] = mapped_column(BigInteger)  # agorot per voucher
    total_cost: Mapped[int] = mapped_column(BigInteger)  # agorot actually paid
    purchase_reference: Mapped[str] = mapped_column(String(128))
