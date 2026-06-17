from datetime import datetime

from sqlalchemy import BigInteger, String, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, primary_key=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)

    __table_args__ = (
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_operation", "operation"),
        Index("idx_audit_created", "created_at"),
    )


class UserSetting(Base, TimestampMixin):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(64), nullable=False)
    setting_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "setting_key", name="uq_user_settings_user_key"),
        Index("idx_user_settings_user", "user_id"),
    )
