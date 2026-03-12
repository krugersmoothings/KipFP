import enum
import uuid
from datetime import date

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Integer,
    Boolean,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountType(str, enum.Enum):
    income = "income"
    cogs = "cogs"
    opex = "opex"
    depreciation = "depreciation"
    interest = "interest"
    tax = "tax"
    asset = "asset"
    liability = "liability"
    equity = "equity"


class Statement(str, enum.Enum):
    is_ = "is"
    bs = "bs"
    cf = "cf"


class NormalBalance(str, enum.Enum):
    debit = "debit"
    credit = "credit"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[AccountType | None] = mapped_column(
        Enum(AccountType, name="account_type")
    )
    statement: Mapped[Statement | None] = mapped_column(
        Enum(Statement, name="statement", values_callable=lambda e: [m.value for m in e])
    )
    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_subtotal: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal_formula: Mapped[dict | None] = mapped_column(JSONB)
    is_elimination: Mapped[bool] = mapped_column(Boolean, default=False)
    normal_balance: Mapped[NormalBalance | None] = mapped_column(
        Enum(NormalBalance, name="normal_balance")
    )


class AccountMapping(Base):
    __tablename__ = "account_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    source_account_code: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    source_account_name: Mapped[str | None] = mapped_column(String(200))
    target_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    multiplier: Mapped[float] = mapped_column(
        Numeric(5, 4), default=1.0
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
