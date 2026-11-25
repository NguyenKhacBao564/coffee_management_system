from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, utcnow


class GoodsItem(Base):
    __tablename__ = "goods_items"
    __table_args__ = (UniqueConstraint("facility_id", "name", name="uq_goods_items_facility_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class GoodsTransaction(Base):
    __tablename__ = "goods_transactions"
    __table_args__ = (UniqueConstraint("facility_id", "idempotency_key", name="uq_goods_tx_idempotency"), CheckConstraint("weight_kg > 0", name="ck_goods_transactions_positive_weight"), CheckConstraint("direction IN ('import','export')", name="ck_goods_transactions_direction"), CheckConstraint("status IN ('draft','pending','confirmed','cancelled')", name="ck_goods_transactions_status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), nullable=False, index=True)
    goods_item_id: Mapped[int] = mapped_column(ForeignKey("goods_items.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    before_result_id: Mapped[int] = mapped_column(ForeignKey("weigh_results.id"), nullable=False)
    after_result_id: Mapped[int] = mapped_column(ForeignKey("weigh_results.id"), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    needs_review: Mapped[bool] = mapped_column(default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    return_reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    replacement_for_id: Mapped[int | None] = mapped_column(ForeignKey("goods_transactions.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
