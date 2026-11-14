import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TokenStatus(str, enum.Enum):
    WAITING = "waiting"
    HELD = "held"
    CALLED = "called"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    avg_service_seconds: Mapped[int] = mapped_column(Integer, default=600)


class Queue(Base):
    __tablename__ = "queues"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    public_code: Mapped[str] = mapped_column(String(32), unique=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class Counter(Base):
    __tablename__ = "counters"
    id: Mapped[int] = mapped_column(primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("queues.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("queue_id", "number", name="uq_token_queue_number"),
        Index("ix_tokens_queue_status", "queue_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("queues.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    public_code: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[TokenStatus] = mapped_column(Enum(TokenStatus, native_enum=False, length=20), default=TokenStatus.WAITING)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QueueEvent(Base):
    """Append-only history of every state change, used for analytics and audits."""
    __tablename__ = "queue_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("queues.id", ondelete="CASCADE"), index=True)
    token_id: Mapped[int] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    counter_id: Mapped[int | None] = mapped_column(ForeignKey("counters.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
